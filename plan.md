# Memory integrity plan: host `9950`

Created 2026-10-23 from step 2 of the second-looks-lab infrastructure plan
([historical record at lab cd2d9e9](https://github.com/jopietsch/second-looks-lab/blob/cd2d9e98e159b4467a6e8fc7ba26f28fba1ca6c7/docs/infrastructure-cleanup-plan.md#2-memory-integrity-on-host-9950-blocks-measurement-there)). Status: fault reproduced 2026-10-23; DIMM isolation next.
This plan blocks all BGP measurement on `9950` (operator decision,
2026-10-22) until its acceptance passes.

## Finding

Found 2026-10-22 during the lab's disk cleanup: the page-cache copy of the
MRT input `bview.20260808.0000` differed from a fresh decompression of its
verified `.gz` in 24 bytes, each one flipped bit `0x80`, in clusters about
16 KB apart near file offsets 265 MB, 1277 MB and 1630 MB. A read that
bypassed the page cache (`dd iflag=direct`) matched the recorded SHA-256
`ab7a99d3…`, so the disk copy was intact and the corruption happened in RAM
after the file was read. The kernel logged no machine check; the host has no
ECC reporting (no EDAC memory controller). The 2026-10 validation's `bgpd` and
`rustybgpd` general protection faults, and OpenBGPD's two failed runs, may
have the same cause and are not attributed to the targets.

After an earlier corruption finding the week before, the operator ran
Memtest86+ 8.00 for 15 h 16 min: 5 passes, 0 errors, all 32 threads in
parallel, DDR5-3600 CL 30-30-30-58, CPU at 49–52 °C (operator's photo).

Every flip whose offset was listed (20 of 24) sits at byte offset 2 modulo 4
and is bit 7: bit 7 of byte lane 2 of a 32-bit DDR5 subchannel, in both
directions. The soak of 2026-10-23 then found bit 7 on byte lane 1 (record).

## Host settings

Read 2026-10-22 without root via `udevadm info -q property -p
/sys/class/dmi/id`: ASUS PRIME X870-P WIFI, BIOS 1804 (2026-09-15), Ryzen 9
9950X3D2; four Timetec `TIMETEC-U32G-5600` 32 GB single-rank DDR5 DIMMs, two
per channel, rated 5600 MT/s. The board trained them to 3600 on its own; the
operator changed nothing. Precision Boost Overdrive `Auto`, memory-controller
voltage 1.136 V (operator's photo). EXPO not in use.

DIMMs by slot (`sudo dmidecode -t memory`, 2026-10-23,
`results/9950/host/`); all report 1.1 V, single rank, configured 3600:

| Channel | Locator | Serial |
|---|---|---|
| A | DIMM 0 | 24000000 |
| A | DIMM 1 | 13000000 |
| B | DIMM 0 | 23000000 |
| B | DIMM 1 | 19000000 |

Label each stick with its serial before moving any; the firmware reports these
serials, which look like placeholders, so a physical label is the reliable ID.

## Tools

- `scripts/memory_soak.py`: memory workers on every core write, invert and
  verify page-aligned patterns; a reader evicts a large file from the page
  cache and checks its hash cold and warm, comparing with a direct read on a
  mismatch; DIMM (`spd5118`), CPU and NVMe temperatures every 5 s; kernel
  traps from `journalctl -k`. Each corrupted byte is reported as
  `lane<offset mod 4>.bit<n>`. Needs no root. Refuses while `bgperf_`
  containers run. Exit 0 clean, 1 corruption or trap, 2 refused, 143 stopped.
- `scripts/memory_soak_status.py`: reports every run under `~/memory-soak`.
  Exit 1 on corruption or a kernel trap, 3 if a run died or stalled.
- `scripts/memory_hash_monitor.py` and
  [docs/qualification-procedure.md](docs/qualification-procedure.md): the
  buffered-read monitor and qualification checklist written on the
  development host (lab `d45afad`); see that page's note.
- `scripts/preflight.py`: before each run, checks the installed DIMMs
  (count, channel, serial, configured speed), BIOS version, RAM, and that the
  host is idle; BIOS-only settings are checked from photos (runbook).
- Tests: `python3 -m pytest` (needs only pytest).

Run detached so it survives the terminal:

    setsid nohup python3 scripts/memory_soak.py --hours 24 \
        --file ~/bgperf-inputs/mrt/bview.20260808.0000 \
        --out ~/memory-soak/<date>-<config> > ~/memory-soak/<date>-<config>.log 2>&1 &

Each run's directory, log and source revision are copied to
`results/9950/<run>/` with a `SHA256SUMS`.

## Isolation

Step by step, with the operator's and the agent's parts and the expected BIOS
values: [docs/dimm-isolation-runbook.md](docs/dimm-isolation-runbook.md).

PBO and Curve Optimizer off for the whole search, and memory set manually to
3600 with the timings and voltage above, so a two-DIMM layout does not train to
5600 and change the load on the controller. Record each DIMM's slot and serial
(table above) before moving any.

1. One DIMM per channel in the board's two-DIMM slots (the manual names them;
   usually A2 and B2), reseating each:
   pair A, 24 h with `--memory-gb 48`; then pair B.
2. If one pair fails: each of its DIMMs alone, 24 h each.
3. Move the failing DIMM into a slot that passed. Error follows the DIMM: RMA
   it. Error stays with the slot: board or CPU.
4. If neither pair fails: two DIMMs per channel at this speed is the fault.
   Run two DIMMs, or four at a lower speed, and soak that.

A clean run must be the full 24 h: the baseline ran 10 h clean before its
first error.

## Accept

24 hours of the soak with no corruption and no kernel trap, at settings
recorded here. Any setting change alters timing, so the host then needs a new
baseline (the lab's post-separation validation step 3 cell) before its
numbers are compared with earlier ones.

## Record

- **2026-10-22:** corruption found and the cached MRT input replaced from a
  direct disk read (lab infrastructure plan, step 0 record).
- **2026-10-23, baseline: fault reproduced**, lab `48a2070` scripts,
  `results/9950/20261022-baseline-4dimm/`. All four DIMMs at the settings
  above, 32 workers over 60.6 GB, started 2026-10-22 18:30:40, stopped by the
  operator at 14.5 h. After 10 h clean, three memory workers saw corruption:
  04:33:02 (worker 4) and 05:53:15 (workers 14 and 19); none in the 604
  page-cache reads and no kernel trap. Each event is two bytes 24 or 40 bytes
  apart, both bit 7 at offset 1 modulo 4 (`lane1.bit7`), flipped in both
  directions. DIMMs were 31–38 °C and the CPU 57–58 °C at the time, as for the
  whole run, so heat is not needed; nor is disk or network DMA. Bit 7 again
  but on byte lane 1, not the lane 2 of 2026-10-22, which fits a weak DIMM or
  marginal signalling better than one broken line.
- **2026-10-23:** operator recorded the DIMM slots and serials
  (`results/9950/host/dmidecode-memory-2026-10-23.txt`). Moved in the lab's
  memory-qualification procedure and buffered hash monitor (lab `584f1cb`), so
  all memory work lives here.
- **2026-10-23, pair-A precheck: stopped before soak**, runbook/preflight
  revision `ceda623` (runbook introduced in `201b97a`). Linux preflight for
  `20261023-pair-A` passed: two DIMMs, A/DIMM 1 serial `13000000` and
  B/DIMM 1 serial `19000000`, both configured 3600 MT/s; BIOS 1804,
  59.5 GiB visible, no measurement or other soak, input present, new run name.
  Operator confirmed these are the sticks labelled A2/B2, installed in A2/B2:
  firmware DIMM 1 therefore maps to physical slot 2 on both channels.
  Pair-B is the remaining `24000000` and `23000000`, originally A1/B1.
  Inspected all six photos in `~/memory-soak/run-1.bios/`: IMG_0219 shows
  manually selected DDR5-3600 and Ai Overclock Tuner Auto (no EXPO profile
  selected); IMG_0220 shows manual tCL/tRCD WR/tRCD RD/tRP/tRAS
  30/30/30/30/58; IMG_0221/0222 show DRAM VDD and VDDQ 1.10000 V.
  CPU VDDIO / MC Voltage is Auto with a 1.136 V reading, rather than the
  required manual setting if supported. PBO Disabled and Curve Optimizer
  off/none are not visible; no EZ Mode slot summary was supplied. Earlier
  live BIOS frequency readings show 5600 before saving; Linux now reports
  configured 3600. No soak started: need photos of PBO and Curve Optimizer,
  MC voltage manually set to 1.136 V if supported (otherwise document the
  limitation), and the saved/rebooted EZ Mode summary. Re-run preflight and
  photo checks before starting pair-A. Evidence copied to
  `results/9950/20261023-pair-A-precheck/`, compared against each source with
  `cmp`, and verified with `SHA256SUMS`; originals left in place. Validation:
  25 tests passed using the existing `second_looks/.pixi/envs/default/bin/python`
  environment; system `python3` has no pytest installed.
