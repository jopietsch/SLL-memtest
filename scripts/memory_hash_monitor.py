#!/usr/bin/env python3
"""Repeated buffered reads against an independently established SHA-256.

This monitors one symptom of memory corruption; it does not qualify hardware.
Run alongside a separately supervised load, following docs/qualification-procedure.md.
"""

import argparse
import hashlib
import json
import math
import signal
import socket
import time
from datetime import datetime, timezone
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def monitor(path, expected, seconds, emit, stopped, *, clock=time.monotonic,
            digest=sha256):
    start = clock()
    reads = 0
    emit({'event': 'start', 'hostname': socket.gethostname(),
          'input': str(path), 'expected_sha256': expected,
          'requested_seconds': seconds,
          'started_utc': datetime.now(timezone.utc).isoformat()})
    try:
        while True:
            if stopped():
                status, code = 'interrupted', 143
                break
            observed = digest(path)
            reads += 1
            elapsed = clock() - start
            emit({'event': 'read', 'iteration': reads,
                  'elapsed_seconds': elapsed, 'sha256': observed})
            if observed != expected:
                status, code = 'mismatch', 1
                break
            if stopped():
                status, code = 'interrupted', 143
                break
            if elapsed >= seconds:
                status, code = 'completed', 0
                break
    except OSError as exc:
        emit({'event': 'error', 'error': str(exc)})
        status, code = 'read_error', 1
    emit({'event': 'finish', 'status': status, 'reads': reads,
          'elapsed_seconds': clock() - start})
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--sha256', required=True,
                        help='Known hash from preserved provenance, not this cache')
    parser.add_argument('--seconds', required=True, type=float)
    parser.add_argument('--output', required=True, type=Path,
                        help='New JSONL file; existing files are refused')
    args = parser.parse_args(argv)
    expected = args.sha256.lower()
    if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
        parser.error('--sha256 must be a complete SHA-256 hex digest')
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error('--seconds must be finite and positive')
    if not args.input.is_file():
        parser.error('--input must be an existing regular file')
    interrupted = False

    def stop(signum, frame):
        nonlocal interrupted
        interrupted = True

    previous = {sig: signal.signal(sig, stop)
                for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        with args.output.open('x', encoding='utf-8') as output:
            def emit(event):
                output.write(json.dumps(event, allow_nan=False) + '\n')
                output.flush()

            return monitor(args.input.resolve(), expected, args.seconds, emit,
                           lambda: interrupted)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    raise SystemExit(main())
