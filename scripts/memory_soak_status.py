#!/usr/bin/env python3
"""Report whether any memory soak has found corruption.

    python3 scripts/memory_soak_status.py            # every run in ~/memory-soak
    python3 scripts/memory_soak_status.py RUN_DIR    # one run

Reads only what memory_soak.py writes and the process table, so it is safe to
run at any time. For each run: whether it is still running, how far along it
is, corruption events with their lane.bit signature, kernel traps since it
started, and current and peak temperatures. Exit 0 when every run is clean and
healthy, 1 when any found corruption or a kernel trap, 3 when a run stopped
without a summary or its heartbeat is stale.
"""
import argparse
import csv
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory_soak import kernel_traps  # noqa: E402

DEFAULT_ROOT = Path.home() / 'memory-soak'
STALE_S = 15 * 60  # three missed heartbeats


def running_pids(run_dir, proc=Path('/proc')):
    """PIDs of memory_soak.py main processes writing to run_dir."""
    pids = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = (entry / 'cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        argv = [a.decode(errors='replace') for a in argv if a]
        if not any(a.endswith('memory_soak.py') for a in argv):
            continue
        if '--out' in argv:
            out = argv[argv.index('--out') + 1:argv.index('--out') + 2]
            if out and Path(out[0]).resolve() == run_dir.resolve():
                pids.append(int(entry.name))
    return sorted(pids)


def read_events(run_dir):
    corruption, heartbeat = [], None
    path = run_dir / 'events.jsonl'
    if not path.exists():
        return corruption, heartbeat
    for line in path.read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue  # a line still being written
        if event.get('kind') == 'heartbeat':
            heartbeat = event
        elif event.get('kind') != 'progress':
            corruption.append(event)
    return corruption, heartbeat


def lanes_of(events):
    lanes = {}
    for event in events:
        for key, n in event.get('lanes', {}).items():
            lanes[key] = lanes.get(key, 0) + n
    return dict(sorted(lanes.items(), key=lambda kv: -kv[1]))


def read_temps(run_dir):
    """(latest row, peak per sensor) from temps.csv."""
    path = run_dir / 'temps.csv'
    if not path.exists():
        return None, {}
    latest, peak = None, {}
    with open(path) as f:
        for row in csv.DictReader(f):
            latest = row
            for key, value in row.items():
                if key == 'time' or not value:
                    continue
                try:
                    peak[key] = max(peak.get(key, float('-inf')), float(value))
                except ValueError:
                    pass
    return latest, peak


def status(run_dir, now=None, traps=kernel_traps, pids=running_pids):
    now = now or datetime.datetime.now()
    config = json.loads((run_dir / 'config.json').read_text())
    started = datetime.datetime.fromisoformat(config['started'])
    summary_path = run_dir / 'summary.json'
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
    corruption, heartbeat = read_events(run_dir)
    live = pids(run_dir)
    found_traps = summary['kernel_traps'] if summary else traps(started.timestamp())
    last_beat = (datetime.datetime.fromisoformat(heartbeat['time'])
                 if heartbeat else started)
    if corruption or found_traps:
        state = 'CORRUPTION FOUND' if corruption else 'KERNEL TRAP'
    elif summary:
        state = 'PASSED' if summary.get('completed') else 'STOPPED EARLY (clean so far)'
    elif not live:
        state = 'DIED (no summary)'
    elif (now - last_beat).total_seconds() > STALE_S:
        state = 'STALLED (no heartbeat)'
    else:
        state = 'RUNNING, clean so far'
    latest, peak = read_temps(run_dir)
    return {'run': str(run_dir), 'state': state, 'pids': live,
            'started': config['started'], 'hours': config['hours'],
            'elapsed_h': round((now - started).total_seconds() / 3600, 2),
            'last_heartbeat': heartbeat['time'] if heartbeat else None,
            'reader_rounds': (heartbeat or {}).get('passes', {}).get('reader'),
            'corruption_events': len(corruption), 'lanes': lanes_of(corruption),
            'first_corruption': corruption[0].get('time') if corruption else None,
            'kernel_traps': found_traps, 'temps_now': latest, 'temps_peak': peak}


def exit_code(report):
    if report['corruption_events'] or report['kernel_traps']:
        return 1
    if report['state'].startswith(('DIED', 'STALLED')):
        return 3
    return 0


def print_report(r):
    print('{0}\n  {1}'.format(r['run'], r['state']))
    print('  started {0}, {1} of {2} h{3}'.format(
        r['started'], r['elapsed_h'], r['hours'],
        ', pid {0}'.format(r['pids'][0]) if r['pids'] else ''))
    print('  last heartbeat {0}, file read {1} times'.format(
        r['last_heartbeat'] or 'none yet', r['reader_rounds'] or 0))
    print('  corruption events: {0}{1}'.format(
        r['corruption_events'],
        ' (first {0}) {1}'.format(r['first_corruption'], r['lanes'])
        if r['corruption_events'] else ''))
    print('  kernel traps: {0}'.format(len(r['kernel_traps'])))
    for line in r['kernel_traps'][:5]:
        print('    ' + line)
    if r['temps_now']:
        print('  temps now/peak C: ' + ', '.join(
            '{0} {1}/{2:g}'.format(k, v, r['temps_peak'].get(k, 0))
            for k, v in r['temps_now'].items() if k != 'time'))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('runs', nargs='*', type=Path,
                   help='run directories; default every run under ~/memory-soak')
    p.add_argument('--json', action='store_true', help='print JSON instead')
    args = p.parse_args(argv)
    runs = args.runs or sorted(d for d in DEFAULT_ROOT.glob('*')
                               if (d / 'config.json').exists())
    if not runs:
        print('no memory soak runs found under {0}'.format(DEFAULT_ROOT))
        return 3
    reports = [status(r) for r in runs]
    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for r in reports:
            print_report(r)
    return max(exit_code(r) for r in reports)


if __name__ == '__main__':
    sys.exit(main())
