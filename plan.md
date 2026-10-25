# Memory integrity plan: host `9950`

Created 2026-10-23 from step 2 of the second-looks-lab infrastructure plan
([historical record at lab cd2d9e9](https://github.com/jopietsch/second-looks-lab/blob/cd2d9e98e159b4467a6e8fc7ba26f28fba1ca6c7/docs/infrastructure-cleanup-plan.md#2-memory-integrity-on-host-9950-blocks-measurement-there)). Status: pair-A passed 24 h on 2026-10-24; pair-B isolation next.
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

PBO Disabled and Curve Optimizer Auto for the whole search (the firmware has
no off choice, operator confirmed 2026-10-23). Set memory manually to 3600
with the timings and DRAM voltage above, and CPU VDDIO / MC Voltage manually
to 1.140 V (firmware cannot set 1.136 V). Keep these settings fixed across
isolation runs, so a two-DIMM layout does not train to 5600 and change the
load on the controller. Record each DIMM's slot and serial (table above)
before moving any. These CPU/MC settings differ from the four-DIMM baseline;
a clean pair alone cannot attribute the original fault solely to DIMM count.

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
- **2026-10-23, pair-A precheck retry: stopped before soak**, revision
  `a6c5622`. Linux preflight again passed for `20261023-pair-A`: A/DIMM 1
  serial `13000000`, B/DIMM 1 serial `19000000`, both 3600 MT/s, BIOS 1804,
  59.5 GiB visible, no measurement or other soak, input present, new run name.
  Inspected all ten photos in `~/memory-soak/run-1.bios/`. New IMG_0225
  confirms Advanced → AMD Overclocking PBO Disable; IMG_0228 confirms BIOS
  1804, 64 GB at DDR5-3600, A2/B2 populated and A1/B1 empty. Earlier photos
  still show manual frequency/timings and DRAM VDD/VDDQ as recorded above.
  IMG_0227 shows a manual CPU VDDIO / MC Voltage entry of **1.14000 V**,
  not the runbook's 1.136 V; the separate +1.136 V reading does not establish
  that setpoint. IMG_0225's monitor reads 1.120 V. IMG_0226 shows Curve
  Optimizer **Auto**, with Auto/All Cores/Per Core/Per CCD choices; this does
  not explicitly confirm off/none. No soak started. Next: set MC voltage to
  1.136 V if supported; if firmware rounds or cannot set it, document that
  limitation before proceeding. Confirm Curve Optimizer off/none (or supply
  evidence that Auto applies no curve with PBO disabled). Save, reboot and
  supply updated photos, then repeat preflight and BIOS checks for pair-A.
  Evidence copied to `results/9950/20261023-pair-A-precheck-2/`; each source
  copy checked with `cmp`, all `SHA256SUMS` verified, originals retained.
  Validation: 25 tests passed using the existing
  `second_looks/.pixi/envs/default/bin/python` environment.
- **2026-10-23, firmware limitations resolved**, following precheck commit
  `d225756`: operator confirmed the BIOS will not accept MC voltage 1.136 V
  and offers no Curve Optimizer off choice, explaining the photographed
  1.14000 V manual setting and Auto. Operator also confirmed F10 save and
  reboot with MC 1.140 V, PBO Disabled and Curve Optimizer Auto. Revised the
  isolation settings and runbook to accept and hold these available settings
  across runs. Curve Optimizer Auto is recorded as such; its effective curve
  is not independently established. No replacement photos needed for these
  already photographed settings. Next: fresh pair-A preflight, then start
  its 24 h soak if all checks pass. Validation: 25 tests passed.
- **2026-10-23, pair-A soak started**, source/runbook revision `c7b12a2`,
  run `20261023-pair-A`. Fresh Linux preflight passed after the operator's
  save/reboot confirmation. A2 (A/DIMM 1) serial `13000000`, B2 (B/DIMM 1)
  serial `19000000`; settings confirmed by the ten photos and documented
  firmware limitations above: manual DDR5-3600, timings 30-30-30-58, DRAM
  VDD/VDDQ 1.10 V, manual MC 1.140 V, no EXPO, PBO Disabled, Curve Optimizer
  Auto, BIOS 1804. Detached PID 8272, 32 workers over 48 GiB, 24 h from
  2026-10-23 13:12:00 PDT; expected end 2026-10-24 13:12 PDT. Direct input
  hash matched `ab7a99d3…`. Preflight, revision and the BIOS photo copy are
  alongside the run under `~/memory-soak`; leave all originals in place.
  Status confirmed RUNNING after first heartbeat at 13:17:01 PDT: all 32
  workers reported 10–11 passes, reader 3 reads, zero corruption or kernel
  traps. Peak temperatures at that check: DIMMs 34.75/32.5 °C, CPU 54.25 °C,
  NVMe 42.85 °C. This is startup verification, not a qualification pass.
  No BGP measurement, builds or other load while it runs. After completion,
  check status, archive and verify the full results and decide the next run
  from the outcome (pair-B if pair-A passes the full 24 h). Validation:
  25 tests passed before starting the soak; no tests run during it.
- **2026-10-24, pair-A PASSED**, source revision `c7b12a2`, startup record
  `c14d176`, results `results/9950/20261023-pair-A/`. Completed the full
  24.0 h, 2026-10-23 13:12:00 to 2026-10-24 13:12:01 PDT, with 32 workers
  over 48 GiB, 3,059–3,072 passes per worker and 934 page-cache reader rounds.
  Zero corruption events (no lane/bit events), zero kernel traps. Peak
  temperatures: DIMMs 39.25/36 °C, CPU 58 °C, NVMe 43.85 °C.
  DIMMs: A2 serial `13000000`, B2 serial `19000000`; BIOS 1804, manual
  DDR5-3600, primary timings 30-30-30-58, DRAM VDD/VDDQ 1.10 V, manual MC
  1.140 V, EXPO unused, PBO Disabled, Curve Optimizer Auto, as confirmed by
  the archived photos and operator's firmware-limit/save/reboot record.
  The status display's 28.08 h is elapsed time since startup at the time of
  checking; `summary.json` confirms the soak itself stopped after 24.0 h.
  Copied all run files, log, revision, preflight and BIOS photos into the
  results directory; every source copy checked with `cmp` and every checksum
  verified with `SHA256SUMS`. Originals retained under `~/memory-soak`.
  Next: shut down and replace pair-A with pair-B, originally labelled A1/B1,
  putting serial `24000000` in A2 and `23000000` in B2; leave A1/B1 empty.
  Keep the same isolation BIOS settings, photograph them, save and reboot;
  run preflight with expected serials `24000000,23000000` before pair-B's
  24 h, 48 GiB soak. Pair-A qualifies only its tested configuration; this
  does not clear other DIMM configurations or establish the original cause.
  BGP measurements remain deferred during the isolation sequence, and a new
  measurement baseline is required at the chosen final settings. Validation:
  25 tests passed after the soak completed.
