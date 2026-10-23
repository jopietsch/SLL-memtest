import importlib.util
import mmap
import multiprocessing
import queue
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'memory_soak.py'
spec = importlib.util.spec_from_file_location('memory_soak', SCRIPT)
soak = importlib.util.module_from_spec(spec)
spec.loader.exec_module(soak)


def test_diff_bytes_reports_offsets_and_values():
    expected = bytes(3 * soak.PAGE)
    actual = bytearray(expected)
    actual[5] = 0x80
    actual[2 * soak.PAGE + 6] = 0x01
    assert soak.diff_bytes(expected, bytes(actual), base=100) == [
        (105, 0, 0x80), (100 + 2 * soak.PAGE + 6, 0, 0x01)]


def test_diff_bytes_stops_at_the_limit():
    assert len(soak.diff_bytes(bytes(64), b'\xff' * 64, limit=3)) == 3


def test_lane_summary_names_the_lane_and_bit():
    # Host 9950's signature: bit 7 at offset 2 modulo 4, in both directions.
    diffs = [(264855634, 0o1, 0o201), (1277075562, 0o304, 0o104), (7, 0, 3)]
    assert soak.lane_summary(diffs) == {
        'lane2.bit7': 2, 'lane3.bit0': 1, 'lane3.bit1': 1}


def test_hwmon_sensors_labels_dimms_by_address(tmp_path):
    for name, hwmon, device in (('spd5118', 'hwmon3', '1-0050'),
                                ('k10temp', 'hwmon1', None),
                                ('amdgpu', 'hwmon2', None)):
        d = tmp_path / hwmon
        d.mkdir()
        (d / 'name').write_text(name + '\n')
        (d / 'temp1_input').write_text('25500\n')
        if device:
            (tmp_path / device).mkdir()
            (d / 'device').symlink_to(tmp_path / device)
    sensors = soak.hwmon_sensors(tmp_path)
    assert [label for label, _ in sensors] == ['dimm-1-0050', 'k10temp']
    assert soak.read_temps(sensors) == {'dimm-1-0050': 25.5, 'k10temp': 25.5}


def test_trap_pattern_matches_the_validation_faults():
    assert soak.TRAP.search('kernel: traps: bgpd[736124] general protection fault')
    assert soak.TRAP.search('kernel: mce: [Hardware Error]: CPU 3')
    assert not soak.TRAP.search('kernel: EXT4-fs (nvme0n1p2): mounted')


def test_memory_worker_runs_clean_passes(monkeypatch):
    monkeypatch.setattr(soak, 'CHUNK', 4 << 20)
    monkeypatch.setattr(soak, 'BLOCK', 1 << 20)
    events, stop = queue.Queue(), multiprocessing.Event()
    original_put = events.put

    def put(event):
        original_put(event)
        if event.get('pass') == 2:
            stop.set()
    events.put = put
    soak.memory_worker(0, 8 << 20, 1, 1, events, stop)
    kinds = [events.get_nowait()['kind'] for _ in range(events.qsize())]
    assert kinds == ['progress', 'progress']


def test_memory_worker_reports_and_repairs_a_flip(monkeypatch):
    monkeypatch.setattr(soak, 'CHUNK', 4 << 20)
    monkeypatch.setattr(soak, 'BLOCK', 1 << 20)
    real_mmap = mmap.mmap
    created = []

    class Flipping:
        # The first verify read of chunk 0 sees bit 7 of byte 2 flipped.
        def __init__(self, *a):
            self.mem = real_mmap(*a)
            self.reads = 0
            created.append(self)

        def __setitem__(self, key, value):
            self.mem[key] = value

        def __getitem__(self, key):
            data = self.mem[key]
            self.reads += 1
            if self.reads == 1:
                data = bytearray(data)
                data[2] ^= 0x80
                data = bytes(data)
            return data

    monkeypatch.setattr(soak.mmap, 'mmap', Flipping)
    events, stop = queue.Queue(), multiprocessing.Event()
    original_put = events.put

    def put(event):
        original_put(event)
        if event['kind'] == 'progress':
            stop.set()
    events.put = put
    soak.memory_worker(0, 4 << 20, 1, 1, events, stop)
    first = events.get_nowait()
    assert first['kind'] == 'memory'
    assert first['lanes'] == {'lane2.bit7': 1}
    assert len(first['diffs']) == 1 and first['diffs'][0][0] == 2


def test_file_reader_finds_cached_corruption(tmp_path, monkeypatch):
    path = tmp_path / 'input'
    path.write_bytes(bytes(range(256)) * 64)
    good = soak.hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(soak, 'evict', lambda p: None)
    monkeypatch.setattr(soak, 'cached_hash', lambda p: 'bad')
    monkeypatch.setattr(soak, 'compare_with_disk',
                        lambda p: [(6, 0x06, 0x86)])
    events, stop = queue.Queue(), multiprocessing.Event()
    original_put = events.put

    def put(event):
        original_put(event)
        stop.set()
    events.put = put
    soak.file_reader([path], {path: good}, events, stop)
    event = events.get_nowait()
    assert event['kind'] == 'page-cache' and event['state'] == 'cold'
    assert event['lanes'] == {'lane2.bit7': 1}


def test_direct_and_cached_hash_agree(tmp_path):
    path = tmp_path / 'input'
    path.write_bytes(bytes(range(256)) * 4096)
    assert soak.cached_hash(path) == soak.direct_hash(path)
    assert soak.compare_with_disk(path) == []
