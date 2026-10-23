#!/usr/bin/env python3
"""Soak a host's memory under benchmark-like load and report corrupted bytes.

Written for host 9950 (plan.md), whose RAM
flipped bits in a cached MRT file while Memtest86+ passed 15 hours. It runs
what memtest does not, all at once:

- memory workers on every core, each writing a pattern and its inverse into
  page-aligned anonymous memory and verifying it repeatedly;
- a reader that evicts a large file from the page cache, reads it back
  (NVMe DMA into RAM), hashes it cold and again warm, and on a mismatch
  compares it byte by byte with a direct read that bypasses the cache;
- a DIMM, CPU and NVMe temperature log, and a kernel-trap check.

Every corrupted byte is reported with its byte lane (offset modulo 4, the
position in a 32-bit DDR5 subchannel) and flipped bits, so a single bad data
line shows up as one repeated lane.bit. Exit 0 when the soak ran its full time
clean, 1 on any corruption or kernel trap, 2 on refusal, 143 when stopped.
"""
import argparse
import datetime
import hashlib
import json
import mmap
import multiprocessing
import os
import queue
import random
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

CHUNK = 64 << 20
PAGE = 4096
BLOCK = 1 << 20
TRAP = re.compile(r'traps:|segfault|general protection|machine check|mce:|'
                  r'hardware error|edac|corrected error|aer:', re.IGNORECASE)


def diff_bytes(expected, actual, base=0, limit=256):
    """(offset, expected, actual) for each differing byte, page by page."""
    diffs = []
    for start in range(0, len(expected), PAGE):
        e, a = expected[start:start + PAGE], actual[start:start + PAGE]
        if e == a:
            continue
        for i, (x, y) in enumerate(zip(e, a)):
            if x != y:
                diffs.append((base + start + i, x, y))
                if len(diffs) >= limit:
                    return diffs
    return diffs


def lane_summary(diffs):
    """Flip counts keyed `lane<offset % 4>.bit<n>`."""
    counts = {}
    for offset, expected, actual in diffs:
        flipped = expected ^ actual
        for bit in range(8):
            if flipped >> bit & 1:
                key = 'lane{0}.bit{1}'.format(offset % 4, bit)
                counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def memory_worker(index, size, verifies, seed, events, stop):
    # Only the parent handles a stop; Ctrl-C reaches the whole process group.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    block = random.Random(seed + index).randbytes(BLOCK)
    inverse = (int.from_bytes(block) ^ ((1 << (8 * BLOCK)) - 1)).to_bytes(BLOCK)
    patterns = (block * (CHUNK // BLOCK), inverse * (CHUNK // BLOCK))
    size = max(CHUNK, size - size % CHUNK)
    mem = mmap.mmap(-1, size)  # page-aligned, so offset % 4 is the physical lane
    passes = 0
    while not stop.is_set():
        pattern = patterns[passes % 2]
        for offset in range(0, size, CHUNK):
            mem[offset:offset + CHUNK] = pattern
        for _ in range(verifies):
            for offset in range(0, size, CHUNK):
                if stop.is_set():
                    return
                # A slice of an mmap is a bytes copy, compared with memcmp;
                # comparing a memoryview goes item by item, six times slower.
                actual = mem[offset:offset + CHUNK]
                if actual != pattern:
                    diffs = diff_bytes(pattern, actual, offset)
                    events.put({'kind': 'memory', 'worker': index,
                                'pass': passes, 'diffs': diffs,
                                'lanes': lane_summary(diffs)})
                    mem[offset:offset + CHUNK] = pattern
        passes += 1
        events.put({'kind': 'progress', 'worker': index, 'pass': passes,
                    'bytes': size})


def evict(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    finally:
        os.close(fd)


def read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        piece = stream.read(size - len(data))
        if not piece:
            break
        data += piece
    return bytes(data)


def chunks(stream):
    while True:
        piece = read_exact(stream, CHUNK)
        if not piece:
            return
        yield piece


def direct_reader(path):
    return subprocess.Popen(['dd', 'if={0}'.format(path), 'iflag=direct',
                             'bs=16M', 'status=none'], stdout=subprocess.PIPE)


def direct_hash(path):
    digest = hashlib.sha256()
    proc = direct_reader(path)
    for piece in chunks(proc.stdout):
        digest.update(piece)
    if proc.wait() != 0:
        raise OSError('direct read of {0} failed'.format(path))
    return digest.hexdigest()


def cached_hash(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for piece in chunks(f):
            digest.update(piece)
    return digest.hexdigest()


def compare_with_disk(path, limit=256):
    """Differences between the page-cache copy and a direct read."""
    diffs = []
    proc = direct_reader(path)
    with open(path, 'rb') as cached:
        offset = 0
        for disk in chunks(proc.stdout):
            mem = read_exact(cached, len(disk))
            if mem != disk:
                diffs += diff_bytes(disk, mem, offset, limit - len(diffs))
                if len(diffs) >= limit:
                    break
            offset += len(disk)
    proc.kill()
    proc.wait()
    return diffs


def file_reader(paths, expected, events, stop):
    rounds = 0
    while not stop.is_set():
        for path in paths:
            for state in ('cold', 'warm'):
                if stop.is_set():
                    return
                if state == 'cold':
                    evict(path)
                digest = cached_hash(path)
                if digest != expected[path]:
                    diffs = compare_with_disk(path)
                    events.put({'kind': 'page-cache', 'file': str(path),
                                'state': state, 'sha256': digest,
                                'diffs': diffs, 'lanes': lane_summary(diffs)})
                    evict(path)
        rounds += 1
        events.put({'kind': 'progress', 'worker': 'reader', 'pass': rounds})


def hwmon_sensors(root=Path('/sys/class/hwmon')):
    """(label, temp1_input path) for DIMM, CPU and NVMe sensors."""
    sensors = []
    for hwmon in sorted(root.glob('hwmon*')):
        try:
            name = (hwmon / 'name').read_text().strip()
        except OSError:
            continue
        if name not in ('spd5118', 'k10temp', 'nvme'):
            continue
        label = name
        if name == 'spd5118':
            label = 'dimm-' + os.path.basename(os.path.realpath(hwmon / 'device'))
        sensors.append((label, hwmon / 'temp1_input'))
    return sorted(sensors)


def read_temps(sensors):
    temps = {}
    for label, path in sensors:
        try:
            temps[label] = int(path.read_text()) / 1000
        except (OSError, ValueError):
            temps[label] = None
    return temps


def temperature_logger(path, interval, stop):
    sensors = hwmon_sensors()
    with open(path, 'w') as f:
        f.write('time,' + ','.join(label for label, _ in sensors) + '\n')
        while not stop.is_set():
            temps = read_temps(sensors)
            f.write(datetime.datetime.now().isoformat(timespec='seconds') + ','
                    + ','.join('' if temps[l] is None else str(temps[l])
                               for l, _ in sensors) + '\n')
            f.flush()
            stop.wait(interval)


def kernel_traps(since):
    out = subprocess.run(['journalctl', '-k', '--no-pager', '-o', 'short-iso',
                          '--since', '@{0}'.format(int(since))],
                         capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if TRAP.search(line)]


def measurement_running():
    try:
        out = subprocess.run(['docker', 'ps', '-q', '--filter', 'name=bgperf_'],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return bool(out.strip())


def mem_total():
    with open('/proc/meminfo') as f:
        for line in f:
            if line.startswith('MemTotal:'):
                return int(line.split()[1]) * 1024
    raise OSError('no MemTotal in /proc/meminfo')


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--file', action='append', required=True, type=Path,
                   help='large file to cycle through the page cache; repeatable')
    p.add_argument('--sha256', action='append', default=[],
                   help='PATH=HASH the direct read of a --file must match')
    p.add_argument('--out', required=True, type=Path, help='new output directory')
    p.add_argument('--hours', type=float, default=24.0)
    p.add_argument('--memory-gb', type=float,
                   help='memory for the workers; default half of RAM')
    p.add_argument('--workers', type=int, default=os.cpu_count())
    p.add_argument('--verifies', type=int, default=4,
                   help='verify passes per pattern write')
    p.add_argument('--interval', type=float, default=5.0,
                   help='seconds between temperature samples')
    p.add_argument('--seed', type=int, default=20261022)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if measurement_running():
        print('refused: bgperf_ containers are running', file=sys.stderr)
        return 2
    if args.out.exists():
        print('refused: {0} exists'.format(args.out), file=sys.stderr)
        return 2
    args.out.mkdir(parents=True)
    paths = [p.resolve() for p in args.file]
    stated = dict(s.split('=', 1) for s in args.sha256)
    expected = {}
    for path in paths:
        expected[path] = direct_hash(path)
        want = stated.get(str(path)) or stated.get(path.name)
        if want and want != expected[path]:
            print('refused: direct read of {0} is {1}, not {2}'.format(
                path, expected[path], want), file=sys.stderr)
            return 2
    memory = int((args.memory_gb * (1 << 30)) if args.memory_gb
                 else mem_total() // 2)
    started = time.time()
    deadline = started + args.hours * 3600
    config = {'started': datetime.datetime.now().isoformat(timespec='seconds'),
              'hours': args.hours, 'workers': args.workers,
              'memory_bytes': memory, 'verifies': args.verifies,
              'seed': args.seed,
              'files': {str(p): expected[p] for p in paths}}
    (args.out / 'config.json').write_text(json.dumps(config, indent=2) + '\n')

    stop = multiprocessing.Event()
    events = multiprocessing.Queue()
    stopped = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda s, f: (stopped.append(s), stop.set()))
    workers = [multiprocessing.Process(
        target=memory_worker, daemon=True,
        args=(i, memory // args.workers, args.verifies, args.seed, events, stop))
        for i in range(args.workers)]
    for w in workers:
        w.start()
    threads = [threading.Thread(target=file_reader, daemon=True,
                                args=(paths, expected, events, stop)),
               threading.Thread(target=temperature_logger, daemon=True,
                                args=(args.out / 'temps.csv', args.interval, stop))]
    for t in threads:
        t.start()

    failures, traps, progress = [], [], {}
    next_trap_check = started + 600
    next_heartbeat = started + 300
    with open(args.out / 'events.jsonl', 'w') as log:
        while not stop.is_set() and time.time() < deadline:
            try:
                event = events.get(timeout=1)
            except queue.Empty:
                event = None
            if event:
                event['time'] = datetime.datetime.now().isoformat(timespec='seconds')
                if event['kind'] == 'progress':
                    progress[str(event['worker'])] = event['pass']
                else:
                    failures.append(event)
                    print('CORRUPTION {0}: {1}'.format(event['kind'], event['lanes']),
                          flush=True)
                    log.write(json.dumps(event) + '\n')
                    log.flush()
            if time.time() >= next_heartbeat:
                log.write(json.dumps({
                    'kind': 'heartbeat',
                    'time': datetime.datetime.now().isoformat(timespec='seconds'),
                    'passes': progress, 'corruption_events': len(failures)}) + '\n')
                log.flush()
                next_heartbeat = time.time() + 300
            if time.time() >= next_trap_check:
                traps = kernel_traps(started)
                next_trap_check = time.time() + 600
            if any(not w.is_alive() for w in workers) and not stop.is_set():
                failures.append({'kind': 'worker-died',
                                 'time': datetime.datetime.now().isoformat()})
                break
        stop.set()
    for w in workers:
        w.join(timeout=30)
        if w.is_alive():
            w.terminate()
    traps = kernel_traps(started)
    lanes = {}
    for f in failures:
        for key, n in f.get('lanes', {}).items():
            lanes[key] = lanes.get(key, 0) + n
    summary = {'started': config['started'],
               'ended': datetime.datetime.now().isoformat(timespec='seconds'),
               'hours_run': round((time.time() - started) / 3600, 3),
               'completed': not stopped and time.time() >= deadline,
               'corruption_events': len(failures), 'lanes': lanes,
               'kernel_traps': traps, 'passes': progress}
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    if failures or traps:
        return 1
    return 143 if stopped else 0


if __name__ == '__main__':
    sys.exit(main())
