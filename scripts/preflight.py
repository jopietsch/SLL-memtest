#!/usr/bin/env python3
"""Check that the host is set up as a soak run expects, before starting it.

    python3 scripts/preflight.py --run 20261023-pair-A --dimms 2 \
        --serials 13000000,19000000

Reads, without root, what Linux can see: the installed DIMMs (channel, slot
locator, serial, configured speed) from SMBIOS via udevadm, the BIOS version,
RAM size, running bgperf_ containers and soaks, and the input file. Settings
Linux cannot see (PBO, Curve Optimizer, timings, voltages) need the BIOS photos
named in docs/dimm-isolation-runbook.md. Writes ~/memory-soak/<run>.preflight.json
and exits 0 when every check passes, 1 otherwise.
"""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory_soak import measurement_running, mem_total  # noqa: E402
from memory_soak_status import running_pids  # noqa: E402

ROOT = Path.home() / 'memory-soak'
INPUT = Path.home() / 'bgperf-inputs/mrt/bview.20260808.0000'
BIOS = '1804'


def dmi_properties():
    out = subprocess.run(['udevadm', 'info', '-q', 'property', '-p',
                          '/sys/class/dmi/id'],
                         capture_output=True, text=True, check=True).stdout
    return dict(line.split('=', 1) for line in out.splitlines() if '=' in line)


def installed_dimms(props):
    """One dict per populated slot, in SMBIOS order."""
    dimms, i = [], 0
    while 'MEMORY_DEVICE_{0}_LOCATOR'.format(i) in props:
        get = lambda key: props.get('MEMORY_DEVICE_{0}_{1}'.format(i, key))
        size = get('SIZE')
        if size and size.isdigit() and int(size) > 0:
            dimms.append({
                'channel': (get('BANK_LOCATOR') or '').split()[-1],
                'locator': get('LOCATOR'),
                'serial': get('SERIAL_NUMBER'),
                'size_gb': int(size) >> 30,
                'configured_mts': int(get('CONFIGURED_SPEED_MTS') or 0)})
        i += 1
    return dimms


def check(dimms, props, expect_dimms, serials, speed, bios=BIOS):
    """[(name, ok, detail)] for the DIMM and firmware facts."""
    results = []
    results.append(('dimm count', len(dimms) == expect_dimms,
                    '{0} installed, expected {1}'.format(len(dimms), expect_dimms)))
    channels = sorted(d['channel'] for d in dimms)
    if expect_dimms == 2:
        results.append(('one per channel', channels == ['A', 'B'],
                        'channels {0}'.format(channels)))
    if serials:
        found = sorted(d['serial'] for d in dimms)
        results.append(('serials', found == sorted(serials),
                        'found {0}, expected {1}'.format(found, sorted(serials))))
    slow = ['{0}/{1} {2}'.format(d['channel'], d['locator'], d['configured_mts'])
            for d in dimms if d['configured_mts'] != speed]
    results.append(('configured speed', not slow,
                    'all {0} MT/s'.format(speed) if not slow
                    else 'not {0}: {1}'.format(speed, slow)))
    version = props.get('ID_BIOS_VERSION') or props.get('BIOS_VERSION')
    if version is None:
        try:
            version = Path('/sys/class/dmi/id/bios_version').read_text().strip()
        except OSError:
            version = 'unknown'
    results.append(('bios version', version == bios,
                    '{0}, expected {1}'.format(version, bios)))
    return results


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--run', required=True, help='run name, e.g. 20261023-pair-A')
    p.add_argument('--dimms', type=int, required=True, help='DIMMs expected')
    p.add_argument('--serials', default='',
                   help='comma-separated serials expected, if known')
    p.add_argument('--speed', type=int, default=3600, help='configured MT/s')
    p.add_argument('--input', type=Path, default=INPUT)
    args = p.parse_args(argv)
    serials = [s for s in args.serials.split(',') if s]

    props = dmi_properties()
    dimms = installed_dimms(props)
    results = check(dimms, props, args.dimms, serials, args.speed)
    ram_gb = mem_total() / (1 << 30)
    results.append(('ram visible', ram_gb > args.dimms * 32 * 0.9,
                    '{0:.1f} GiB'.format(ram_gb)))
    results.append(('no measurement', not measurement_running(),
                    'no bgperf_ containers' if not measurement_running()
                    else 'bgperf_ containers are running'))
    soaks = [pid for d in ROOT.glob('*') if d.is_dir() for pid in running_pids(d)]
    results.append(('no other soak', not soaks, 'running pids {0}'.format(soaks)))
    out = ROOT / args.run
    results.append(('new run name', not out.exists(), str(out)))
    results.append(('input present', args.input.is_file(), str(args.input)))

    for name, ok, detail in results:
        print('{0:5} {1:18} {2}'.format('ok' if ok else 'FAIL', name, detail))
    print('DIMMs: ' + ', '.join('{channel}/{locator} serial {serial} '
                                '{configured_mts} MT/s'.format(**d) for d in dimms))
    passed = all(ok for _, ok, _ in results)
    print('PREFLIGHT ' + ('PASSED' if passed else 'FAILED'))
    ROOT.mkdir(exist_ok=True)
    record = {'run': args.run,
              'time': datetime.datetime.now().isoformat(timespec='seconds'),
              'passed': passed, 'dimms': dimms,
              'checks': [{'name': n, 'ok': ok, 'detail': d} for n, ok, d in results]}
    (ROOT / (args.run + '.preflight.json')).write_text(json.dumps(record, indent=2) + '\n')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
