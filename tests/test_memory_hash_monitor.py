"""Corruption and interruption must never become successful completion."""
import hashlib
import importlib.util

import pytest

from conftest import REPO_ROOT


@pytest.fixture
def monitor():
    spec = importlib.util.spec_from_file_location(
        'memory_hash_monitor', REPO_ROOT / 'scripts/memory_hash_monitor.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repeated_buffered_reads_complete(monitor, tmp_path):
    source = tmp_path / 'input'
    source.write_bytes(b'known data')
    expected = hashlib.sha256(b'known data').hexdigest()
    events = []
    ticks = iter([0, 1, 2, 3, 3])
    assert monitor.monitor(source, expected, 3, events.append, lambda: False,
                           clock=lambda: next(ticks)) == 0
    assert events[-1]['status'] == 'completed'
    assert events[-1]['reads'] == 3


def test_first_mismatch_stops_even_at_deadline(monitor, tmp_path):
    source = tmp_path / 'input'
    source.write_bytes(b'changed')
    events = []
    ticks = iter([0, 10, 10])
    assert monitor.monitor(source, '0' * 64, 10, events.append, lambda: False,
                           clock=lambda: next(ticks)) == 1
    assert events[-1]['status'] == 'mismatch'
    assert events[-1]['reads'] == 1


def test_interruption_during_read_is_not_completion(monitor, tmp_path):
    events = []
    stopped = [False]

    def digest(path):
        stopped[0] = True
        return 'a' * 64

    assert monitor.monitor(tmp_path, 'a' * 64, 1, events.append,
                           lambda: stopped[0], clock=lambda: 0,
                           digest=digest) == 143
    assert events[-1]['status'] == 'interrupted'


def test_read_error_is_recorded(monitor, tmp_path):
    events = []
    assert monitor.monitor(tmp_path / 'missing', 'a' * 64, 1, events.append,
                           lambda: False) == 1
    assert events[-1]['status'] == 'read_error'


def test_existing_evidence_is_not_overwritten(monitor, tmp_path):
    source = tmp_path / 'input'
    source.write_bytes(b'input')
    output = tmp_path / 'evidence.jsonl'
    output.write_text('preserved')
    with pytest.raises(FileExistsError):
        monitor.main(['--input', str(source), '--sha256', 'a' * 64,
                      '--seconds', '1', '--output', str(output)])
    assert output.read_text() == 'preserved'
