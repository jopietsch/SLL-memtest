import importlib.util
import sys

from conftest import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location(
    'preflight', REPO_ROOT / 'scripts/preflight.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def props(slots):
    """udevadm properties for (channel, locator, serial or None, mts) slots."""
    out = {'ID_BIOS_VERSION': '1804'}
    for i, (channel, locator, serial, mts) in enumerate(slots):
        key = 'MEMORY_DEVICE_{0}_'.format(i)
        out[key + 'LOCATOR'] = locator
        out[key + 'BANK_LOCATOR'] = 'P0 CHANNEL ' + channel
        if serial:
            out[key + 'SIZE'] = str(32 << 30)
            out[key + 'SERIAL_NUMBER'] = serial
            out[key + 'CONFIGURED_SPEED_MTS'] = str(mts)
    return out


def failed(results):
    return [name for name, ok, _ in results if not ok]


def test_installed_dimms_skips_empty_slots():
    p = props([('A', 'DIMM 0', None, 0), ('A', 'DIMM 1', '13000000', 3600),
               ('B', 'DIMM 0', None, 0), ('B', 'DIMM 1', '19000000', 3600)])
    dimms = preflight.installed_dimms(p)
    assert [(d['channel'], d['locator'], d['serial']) for d in dimms] == [
        ('A', 'DIMM 1', '13000000'), ('B', 'DIMM 1', '19000000')]


def test_a_correct_pair_passes():
    p = props([('A', 'DIMM 1', '13000000', 3600), ('B', 'DIMM 1', '19000000', 3600)])
    results = preflight.check(preflight.installed_dimms(p), p, 2,
                              ['19000000', '13000000'], 3600)
    assert failed(results) == []


def test_a_pair_on_one_channel_trained_to_5600_fails():
    p = props([('A', 'DIMM 0', '24000000', 5600), ('A', 'DIMM 1', '13000000', 5600)])
    results = preflight.check(preflight.installed_dimms(p), p, 2,
                              ['13000000', '19000000'], 3600)
    assert failed(results) == ['one per channel', 'serials', 'configured speed']


def test_a_changed_bios_fails():
    p = props([('A', 'DIMM 1', '13000000', 3600)])
    p['ID_BIOS_VERSION'] = '1901'
    results = preflight.check(preflight.installed_dimms(p), p, 1, [], 3600)
    assert failed(results) == ['bios version']
