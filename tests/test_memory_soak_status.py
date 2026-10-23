import datetime
import importlib.util
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    'memory_soak_status', SCRIPTS / 'memory_soak_status.py')
status_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status_mod)

STARTED = datetime.datetime(2026, 10, 22, 18, 30, 40)


def make_run(tmp_path, events=(), summary=None):
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'config.json').write_text(json.dumps(
        {'started': STARTED.isoformat(), 'hours': 24.0}))
    (run / 'events.jsonl').write_text(
        ''.join(json.dumps(e) + '\n' for e in events) + '{"kind": "heart')
    (run / 'temps.csv').write_text(
        'time,dimm-1-0050,k10temp\n'
        '2026-10-22T18:31:00,30.0,50.0\n'
        '2026-10-22T18:32:00,36.5,58.0\n'
        '2026-10-22T18:33:00,35.0,57.0\n')
    if summary:
        (run / 'summary.json').write_text(json.dumps(summary))
    return run


def beat(minutes):
    return {'kind': 'heartbeat', 'passes': {'reader': 7},
            'time': (STARTED + datetime.timedelta(minutes=minutes)).isoformat()}


def report(run, minutes, pids=(1234,), traps=()):
    return status_mod.status(
        run, now=STARTED + datetime.timedelta(minutes=minutes),
        traps=lambda since: list(traps), pids=lambda d: list(pids))


def test_a_clean_running_soak(tmp_path):
    r = report(make_run(tmp_path, [beat(5), beat(10)]), 12)
    assert r['state'] == 'RUNNING, clean so far'
    assert r['reader_rounds'] == 7
    assert r['temps_peak'] == {'dimm-1-0050': 36.5, 'k10temp': 58.0}
    assert status_mod.exit_code(r) == 0


def test_corruption_is_reported_with_its_lanes(tmp_path):
    flip = {'kind': 'page-cache', 'time': '2026-10-22T19:00:00',
            'lanes': {'lane2.bit7': 3}}
    r = report(make_run(tmp_path, [beat(5), flip, flip]), 40)
    assert r['state'] == 'CORRUPTION FOUND'
    assert r['lanes'] == {'lane2.bit7': 6}
    assert r['first_corruption'] == '2026-10-22T19:00:00'
    assert status_mod.exit_code(r) == 1


def test_a_kernel_trap_fails_the_run(tmp_path):
    r = report(make_run(tmp_path, [beat(5)]), 8,
               traps=['traps: bgpd[1] general protection fault'])
    assert r['state'] == 'KERNEL TRAP'
    assert status_mod.exit_code(r) == 1


def test_a_dead_soak_without_summary(tmp_path):
    r = report(make_run(tmp_path, [beat(5)]), 8, pids=())
    assert r['state'] == 'DIED (no summary)'
    assert status_mod.exit_code(r) == 3


def test_a_stale_heartbeat(tmp_path):
    r = report(make_run(tmp_path, [beat(5)]), 25)
    assert r['state'] == 'STALLED (no heartbeat)'
    assert status_mod.exit_code(r) == 3


def test_a_finished_soak_uses_its_summary(tmp_path):
    run = make_run(tmp_path, [beat(5)],
                   summary={'completed': True, 'kernel_traps': []})
    r = report(run, 2000, pids=())
    assert r['state'] == 'PASSED'
    assert status_mod.exit_code(r) == 0


def test_running_pids_matches_the_out_directory(tmp_path):
    proc = tmp_path / 'proc'
    run = tmp_path / 'run'
    run.mkdir()
    for pid, argv in (('10', ['python3', 'memory_soak.py', '--out', str(run)]),
                      ('11', ['python3', 'memory_soak.py', '--out', '/other']),
                      ('12', ['bash', '-c', 'memory_soak.py --out ' + str(run)]),
                      ('self', ['ignored'])):
        (proc / pid).mkdir(parents=True)
        (proc / pid / 'cmdline').write_bytes(
            b'\0'.join(a.encode() for a in argv) + b'\0')
    assert status_mod.running_pids(run, proc) == [10]
