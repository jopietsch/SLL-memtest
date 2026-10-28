# Memory integrity plan: host `9950`

Created 2026-10-23 from step 2 of the second-looks-lab infrastructure plan
([historical record at lab cd2d9e9](https://github.com/jopietsch/second-looks-lab/blob/cd2d9e98e159b4467a6e8fc7ba26f28fba1ca6c7/docs/infrastructure-cleanup-plan.md#2-memory-integrity-on-host-9950-blocks-measurement-there)). Status: pair-A and pair-B each passed 24 h (2026-10-24, 2026-10-26); four-DIMM recheck next.
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
4. If neither pair fails: reinstall all four in their original slots, each
   reseated, at the isolation settings, and soak 24 h with `--memory-gb 96`
   (run `four-dimm` in the runbook). Both pairs passing does not by itself
   blame two DIMMs per channel: the failing baseline also differed in seating,
   in using slots A1/B1, and in PBO Auto and MC voltage Auto.
   - Passes: keep 128 GB at these settings. Reseating or the setting changes
     fixed it; this run cannot tell which. Rerun the lab's measurement
     baseline before comparing BGP numbers.
   - Fails: two DIMMs per channel on this board and CPU is the fault. Try
     more MC voltage or a lower speed before replacing anything; 2 x 64 GB
     DIMMs would give 128 GB at one per channel.

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
- **2026-10-25, pair-B soak started**, source/runbook revision `218d3ce`,
  run `20261025-pair-B`. Preflight re-run after the 17:30 PDT boot passed:
  A2 (A/DIMM 1) serial `24000000`, B2 (B/DIMM 1) serial `23000000`, both
  3600 MT/s, BIOS 1804, 59.5 GiB visible, no measurement or other soak, input
  present, new run name. Inspected all seven photos in
  `~/memory-soak/run-2.bios/` (not the runbook's `<run>.bios/` path):
  IMG_0243 EZ Mode shows BIOS 1804, 65536 MB at DDR5-3600, A2/B2 populated and
  A1/B1 empty; IMG_0238 manual DDR5-3600 with Ai Overclock Tuner Auto (no
  EXPO); IMG_0239 tCL/tRCD WR/tRCD RD/tRP/tRAS 30/30/30/30/58 on both
  channels; IMG_0240/0241 DRAM VDD/VDDQ 1.10000 V and manual MC 1.14000 V
  (live reading 1.168 V, against pair-A's 1.136/1.120 V readings: telemetry,
  same setpoint); IMG_0242 PBO Disable. **Curve Optimizer is not shown in any
  pair-B photo**, so it is unverified for this run; the operator could not
  find the setting and directed the soak to start anyway (deviation from the
  runbook's unknown-value stop). It was Auto for pair-A (IMG_0226) and has no
  off choice. Detached PID 7584, 32 workers over 48 GiB, 24 h from
  2026-10-25 17:36:12 PDT; expected end 2026-10-26 17:36 PDT. No BGP
  measurement, builds or other load while it runs. After completion, archive
  per the runbook and decide the next step from plan.md's isolation steps:
  pair-B failing while pair-A passed points to step 2 (pair-B singles); both
  passing points to step 4. Status confirmed RUNNING after first heartbeat
  at 17:41:12 PDT: all 32 workers 10–11 passes, reader 3 reads, zero
  corruption or kernel traps; peaks DIMMs 36/33.75 °C, CPU 56.1 °C, NVMe
  43.85 °C. Startup verification only, not a qualification pass.
  Validation: 25 tests passed before starting.
- **2026-10-26, pair-B PASSED**, source revision `218d3ce`, startup record
  `e2561d9`, results `results/9950/20261025-pair-B/`. Completed the full
  24.0 h, 2026-10-25 17:36:12 to 2026-10-26 17:36:12 PDT, with 32 workers
  over 48 GiB, 3,062–3,112 passes per worker and 926 page-cache reader rounds.
  Zero corruption events (no lane/bit events), zero kernel traps. Peak
  temperatures: DIMMs 40.25/37.25 °C, CPU 59.125 °C, NVMe 44.85 °C, about
  1 °C above pair-A, warmest in the afternoon. DIMMs: A2 serial `24000000`,
  B2 serial `23000000`. Settings as for pair-A by photo (`bios/`, copied from
  `~/memory-soak/run-2.bios/`), except Curve Optimizer, not photographed for
  this run (see the start record). Copied run files, log, revision,
  preflight and photos; every copy checked with `cmp` and `SHA256SUMS`
  verified. Originals retained under `~/memory-soak`.
  All four DIMMs have now passed 24 h, in pairs, in slots A2/B2. Isolation
  step 4 originally concluded from this that two DIMMs per channel was the
  fault; operator decision 2026-10-26: the failing baseline also differed in
  seating, slots A1/B1 and PBO/MC voltage, and the host needs all 128 GB, so
  revised step 4 to a four-DIMM recheck at the isolation settings (24 h).
  No DIMM is implicated; no replacement planned. Next: reinstall all four in
  their original slots (A1 `24000000`, A2 `13000000`, B1 `23000000`,
  B2 `19000000`), reseated; keep the isolation BIOS settings and photograph
  them, including Curve Optimizer if it can be found (F9 search
  "CURVE OPTIMIZER", as IMG_0226); save, reboot, then run `four-dimm` per
  the runbook. Validation: 25 tests passed.
- **2026-10-26, four-DIMM start failed before workers ran**, source/runbook
  revision `705199e`, attempted run `20261026-four-dimm`. Linux preflight
  passed: A1 `24000000`, A2 `13000000`, B1 `23000000`, B2 `19000000`,
  all configured 3600 MT/s, BIOS 1804, 121.2 GiB visible, no measurement
  or other soak, input present, new run name. Inspected all three photos in
  `~/memory-soak/four-dimms.bios/`: IMG_0250 confirms all four slots,
  131072 MB at DDR5-3600 and BIOS 1804; IMG_0252 confirms manual primary
  timings 30/30/30/30/58 on both channels; IMG_0253 shows Curve Optimizer
  Auto. Manual frequency selection, DRAM VDD/VDDQ, manual MC setpoint,
  EXPO selection and PBO state are not shown. Initially stopped for missing
  photo evidence; operator then confirmed nothing had changed and explicitly
  directed proceeding on the prior isolation settings (manual DDR5-3600,
  DRAM VDD/VDDQ 1.10 V, manual MC 1.140 V, EXPO unused, PBO Disabled).
  These settings are accepted by operator confirmation, not independently
  verified in the current photos; deviation from the runbook's unknown-value
  stop is authorized for this attempt.
  Preflight was rerun successfully and 25 tests passed before launch.
  The direct input hash matched `ab7a99d3…`. The attempted 24 h, 96 GiB,
  32-worker run failed at 19:03 PDT before any memory worker started:
  Python 3.14's multiprocessing forkserver `listener.bind` raised
  `PermissionError: [Errno 1] Operation not permitted` in this session's
  restricted execution environment. No soak is running and no qualification
  result was obtained; this is a launcher failure, not a memory-test failure.
  Evidence retained under `~/memory-soak/20261026-four-dimm*`:
  preflight, BIOS-check/operator confirmation, startup record, source revision,
  log and partial run directory (`config.json` only); photos remain in
  `four-dimms.bios/`. Next: launch from a host terminal that permits the
  worker startup, using a fresh run name (suggested
  `20261026-four-dimm-retry`), fresh preflight, the same settings and the
  runbook's 24 h / 96 GiB command; confirm RUNNING and a first heartbeat.
  A host-terminal retry subsequently wrote config.json at 19:11:16 PDT,
  preflight, revision, events.jsonl and temperature samples under
  `~/memory-soak/20261026-four-dimm-retry*`. At the first check there was
  no heartbeat yet. The agent's restricted process view could not see a
  matching PID, so its status script reported DIED; host-terminal status
  and the first heartbeat are still needed to establish liveness.
  BGP measurements remain deferred.
- **2026-10-27, four-DIMM retry FAILED**, source revision `705199e`, run
  `20261026-four-dimm-retry`. Host-terminal startup was verified by the
  operator's status output: PID 8806, RUNNING, with a 19:21:16 heartbeat.
  Ran 2026-10-26 19:11:16 to 2026-10-27 06:42:05 PDT, 11.514 h,
  32 workers over 96 GiB, then operator sent SIGTERM after corruption.
  Final summary: 2 memory corruption events, 14 `lane1.bit7` flips,
  zero kernel traps, 484 reader rounds, 717-731 passes per memory worker.
  First event 02:13:55 (about 7.04 h), worker 1, 10 flipped bytes; second
  05:16:37, worker 7, 4 flipped bytes. No page-cache corruption was reported.
  Peak temperatures: DIMMs 38.75/38.5/36.75/33.5 C, CPU 58.75 C,
  NVMe 43.85 C. All four serials were in their original slots at 3600 MT/s;
  settings are supported by current photos and the operator's unchanged-
  settings confirmation recorded above. Current settings and reseating did
  not resolve the four-DIMM fault. Both pairs passed in A2/B2; this points
  toward a four-DIMM/slot-path problem but does not isolate the DIMMs,
  motherboard or CPU, or independently qualify A1/B1 with one DIMM per channel.
  Results, log, revision, preflight, current BIOS photos and settings evidence
  archived in `results/9950/20261026-four-dimm-retry/`; the failed sandbox
  launch evidence is in `results/9950/20261026-four-dimm-startup-failure/`.
  Every repository copy was byte-compared with its staged source and all
  SHA256SUMS verified. Originals retained under `~/memory-soak`.
  Recommended next experiment (not started): keep all four DIMMs and change
  only manual DRAM frequency to DDR5-3200 if offered by the BIOS. Keep manual
  timings, DRAM VDD/VDDQ, MC voltage, PBO and Curve Optimizer unchanged.
  Photograph the selected frequency, save/reboot, and run fresh preflight
  with `--speed 3200` before a fresh 24 h / 96 GiB soak. The runbook's
  fixed-3600 setting applies to the completed isolation comparison; this
  proposed mitigation experiment must explicitly record its lower speed.
  If 3200 is not offered, record the available lower frequency choices first.
  BGP measurements remain blocked until a complete clean qualification run.
  Archive/record validation: 25 tests passed before committing.
- **2026-10-28, four-DIMM at DDR5-3200 FAILED**, source revision `37e8b1f`,
  run `20261027-four-dimm-3200`. Only change from `20261026-four-dimm-retry`:
  manual DRAM frequency DDR5-3600 -> DDR5-3200. Preflight (`--dimms 4
  --speed 3200`) passed: A1 `24000000`, A2 `13000000`, B1 `23000000`,
  B2 `19000000`, all configured 3200 MT/s, BIOS 1804, 121.2 GiB visible.
  Confirmed by photo (IMG_0255-0261): Memory Frequency DDR5-3200MHz set
  manually and running 3200 MHz; Ai Overclock Tuner Auto (no EXPO/XMP
  profile); primary timings 30/30/30/30/58 on both channels; DRAM VDD/VDDQ
  1.10 V; manual MC 1.140 V (live 1.168 V is telemetry); all four slots,
  131072 MB. PBO Disabled and Curve Optimizer Auto were not photographed;
  the operator confirmed them unchanged from the previous run.
  Launched from the agent sandbox (forkserver worker startup worked this
  time), PID 9503, 32 workers over 96 GiB; first heartbeat 12:59:01.
  Ran 2026-10-27 12:54:01 to 2026-10-28 08:55:44 PDT, 20.029 h, then stopped
  with SIGTERM at the operator's request after corruption.
  Final summary: 2 memory corruption events, 32 `lane1.bit7` flips, zero
  kernel traps, 769 reader rounds, 1119-1127 passes per memory worker.
  First event 03:14:46 (about 14.35 h), worker 25, 16 flipped bytes; second
  05:38:47 (about 16.75 h), worker 15, 16 flipped bytes. Every flipped byte
  differs by exactly 0x80, the same signature as at 3600 MT/s.
  No page-cache corruption was reported.
  Peak temperatures: DIMMs 39.25/39.25/37.75/34.25 C, CPU 57.6 C,
  NVMe 43.85 C. A single 47.75 C `dimm-1-0053` sample at 06:14:46, with 32.0 C
  on either side 5 s apart and after both events, is treated as a sensor glitch.
  Lowering the frequency to 3200 delayed the first error (14.35 h vs 7.04 h)
  but did not remove the four-DIMM fault; it is not a mitigation.
  Results, log, revision, preflight, BIOS photos and settings evidence
  archived in `results/9950/20261027-four-dimm-3200/`; every copy
  byte-compared with its source and SHA256SUMS verified. Originals retained
  under `~/memory-soak`. Next run not yet chosen; it should come from the
  isolation steps (e.g. singles/swap to qualify A1/B1 one DIMM per channel).
  BGP measurements remain blocked until a complete clean qualification run.
  Archive/record validation: 25 tests passed before committing.
- **2026-10-28, next run planned: four-DIMM with raised memory voltages**,
  run name `20261028-four-dimm-1v25`. Operator needs all 128 GB, and memory
  prices make a 2 x 64 GB kit a last resort, so try isolation step 4's "more
  MC voltage" before asking the seller for a remedy. All four DIMMs in their
  original slots, as for `20261026-four-dimm-retry`, with frequency back to
  manual DDR5-3600 and three changes only: DRAM VDD 1.10 -> 1.25 V,
  DRAM VDDQ 1.10 -> 1.25 V, CPU VDDIO / MC 1.140 -> 1.25 V. Timings
  30/30/30/30/58, Ai Overclock Tuner Auto (no EXPO), PBO Disabled and Curve
  Optimizer Auto unchanged. Operator: set these, photograph the voltage page,
  frequency page, PBO page and Curve Optimizer page (all four this time), save,
  reboot, copy photos to `~/memory-soak/run-5.bios/`. Agent: preflight
  `--dimms 4 --serials 24000000,13000000,23000000,19000000 --speed 3600`,
  check every photo against these values, then the runbook's 24 h / 96 GiB
  soak. The 3600 run first failed at 7.04 h, so a failure is likely visible
  overnight. Passes: keep 128 GB at these voltages; rerun the lab measurement
  baseline. Fails: stop testing these four sticks and pursue a seller remedy;
  a pair in A1/B1 would only tell board from DIMM for a warranty claim.
  A summary for the seller of all runs so far is in the operator's Claude doc
  "Memory errors with four DIMMs: test summary".
- **2026-10-28, four-DIMM 1.25 V soak started**, source revision `b6f4ad5`,
  run `20261028-four-dimm-1v25`. Preflight (`--dimms 4 --serials
  24000000,13000000,23000000,19000000 --speed 3600`) passed: A1 `24000000`,
  A2 `13000000`, B1 `23000000`, B2 `19000000`, all configured 3600 MT/s,
  BIOS 1804, 121.2 GiB visible, no measurement or other soak, input present.
  Confirmed by photo (`~/memory-soak/run-5.bios/`, IMG_0262-0269, no 0267):
  Memory Frequency DDR5-3600MHz manual, Ai Overclock Tuner Auto (no EXPO);
  CPU VDDIO / MC 1.25000 V, DRAM VDD 1.25000 V, DRAM VDDQ 1.25000 V;
  timings 30/30/30/30/58 on both channels; PBO Disabled; Curve Optimizer
  Auto (F9 search); EZ Mode BIOS 1804, all four slots, 131072 MB. The photos'
  live readings (3200 MHz, MC 1.168 V) are from the boot before the save;
  the BIOS clock is UTC (16:55-16:59 = 09:55-09:59 PDT). All four planned
  settings verified by photo, with no operator-only confirmation this time.
  Launched from the agent sandbox, PID 12131, 24 h, 32 workers over 96 GiB;
  started 10:10:50 PDT, first heartbeat 10:15:51, status RUNNING and clean.
  Expected end 2026-10-29 10:10 PDT. Evidence in
  `~/memory-soak/20261028-four-dimm-1v25*` (preflight, bios-check, revision).
