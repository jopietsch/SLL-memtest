# Memory-integrity qualification

Moved 2026-10-23 from second-looks-lab `bgp/docs/memory-integrity.md` (lab
`584f1cb`), written on the development host before the baseline soak
reproduced the fault. Its pre-start checklist and evidence rules still apply.
[plan.md](../plan.md) owns the current search: `scripts/memory_soak.py`
provides the load itself, so the `stress-ng` plus hash-monitor method below is
an alternative, not a requirement.

This procedure owns the memory-qualification requirements for `9950`, which
remains blocked for BGP measurement. The original finding, firmware observations,
memtest correction and diagnostic options are preserved in the
[cleanup record at lab cd2d9e9](https://github.com/jopietsch/second-looks-lab/blob/cd2d9e98e159b4467a6e8fc7ba26f28fba1ca6c7/docs/infrastructure-cleanup-plan.md#2-memory-integrity-on-host-9950-blocks-measurement-there).
This document prepares the test; it does not authorize starting it. The operator's
instruction to leave `9950` alone still applies to development sessions. No
current diagnostic run or qualification outcome has been inspected here.

## Before starting on the measurement host

- Arrange a dedicated window with no benchmark, batch driver or other load.
  Inspect running processes, `docker ps`, and the held batch locks; the
  existence of a lock file alone does not indicate a running batch.
- Record the lab revision, host identity, kernel, CPU and memory capacity.
  Save BIOS version and `sudo dmidecode -t memory` output. Record memory
  speed/timings, DIMM layout, EXPO/XMP, PBO and Curve Optimizer from firmware;
  an unavailable value stays unknown, rather than being inferred.
- Use a new attempt directory outside Git on the persistent work filesystem.
  Keep settings, exact commands, stdout/stderr, start/end UTC timestamps,
  stress-tool version, temperature observations and kernel logs there.
- Select the preserved input and its **full** known SHA-256 from `SHA256SUMS`.
  For `9950`, the lab's [input registry](https://github.com/jopietsch/second-looks-lab/blob/main/bgp/docs/input-registry.md) records rrc00 under `~/bgperf-inputs/mrt`.
  Verify the on-disk input independently with a direct read before the load:

  ```sh
  set -o pipefail
  dd if="$INPUT" iflag=direct bs=4M status=progress | sha256sum
  ```

  Compare the result with the preserved full digest and retain command status
  and output. A read error or unsupported direct I/O is a refusal to continue,
  not a verified input. Do not replace the known hash with a hash of the cache.

## Loaded test

Choose and record explicit stress parameters for this host before launch.
The buffered-monitor procedure uses simultaneous all-core CPU load and `stress-ng` VM load
with `--verify`, targeting the roughly 48 GB memory footprint that exposed
the fault. Check the installed stress-ng help for allocation semantics across
workers; keep room for the OS, input cache and monitor. Record the full command,
version, exit status and output. A failed, killed or early-exiting stress
process leaves the test incomplete. No stress tool is installed or launched by
the hash monitor.

While that load remains active, run the monitor with explicit paths and the
preserved full digest (the shell variables below must be supplied):

```sh
python3 scripts/memory_hash_monitor.py \
  --input "$INPUT" --sha256 "$EXPECTED_SHA256" \
  --seconds 86400 --output "$ATTEMPT/page-cache.jsonl"
```

The monitor repeatedly opens and hashes the input through ordinary buffered
reads. It deliberately does not drop caches or request direct I/O: this part
tests the memory-backed read path. It flushes a JSONL record after each read
and stops on the first mismatch or read failure (exit 1). SIGINT/SIGTERM
produces an interrupted result (exit 143) after the current read returns.
An existing output file is refused. A crash or kill without a finish record
is incomplete; use a new directory for the next attempt.

Supervise both processes. Stop the load when the monitor fails or is stopped;
stop the monitor if the load fails. Preserve full kernel logs for the window
with `journalctl -k`, including stderr and exit status, and inspect for traps,
machine checks and OOM events. Lack of journal access is missing evidence.
Do not clear caches, rewrite inputs or change firmware settings mid-attempt.

## Review and next attempt

The monitor's `completed` status means only that buffered hashes agreed for
the requested interval. Acceptance also requires at least 24 uninterrupted
hours of the documented simultaneous load, no kernel trap, and recorded host
settings. An idle run, short smoke, missing logs or stopped load cannot satisfy
the hardware gate. Hash agreement does not prove all RAM is fault-free.

On a mismatch preserve the output, kernel logs, load logs and settings before
trying anything else. Follow the pinned diagnostic record's one-setting-at-a-time
sequence and create a new attempt for every change. Record the reviewed outcome
and its evidence revision alongside this qualification procedure. Any setting
change requires a fresh performance baseline
before comparing new measurements with earlier ones. Evidence transfer remains
a separately authorized action.
