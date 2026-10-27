# DIMM isolation runbook: host `9950`

The step-by-step for [plan.md](../plan.md)'s isolation. The operator does the
hardware and BIOS work; an agent checks it, starts the soak, and records the
result. An agent following this page needs no other instruction than "run the
next isolation step"; it stops and asks whenever a check fails.

## Runs

| Run | DIMMs installed | In slots | Expected serials |
|---|---|---|---|
| `pair-A` | the two that were in A2 and B2 | A2, B2 | read at preflight, then confirmed against the labels |
| `pair-B` | the two that were in A1 and B1 | A2, B2 | the two serials of the four not in `pair-A` |
| singles, swap | decided from the pair results (plan.md) | A2 | named in plan.md before the run |
| `four-dimm` | all four, if both pairs pass (plan.md step 4) | their original slots: A1 `24000000`, A2 `13000000`, B1 `23000000`, B2 `19000000` | all four |

The four serials, by original slot locator (`results/9950/host/`): A/DIMM 0
`24000000`, A/DIMM 1 `13000000`, B/DIMM 0 `23000000`, B/DIMM 1 `19000000`.
Whether firmware's `DIMM 0`/`DIMM 1` is the board's slot 1 or 2 is not known;
`pair-A`'s preflight settles it, and the agent records the mapping in plan.md.

Every run uses the same BIOS settings, so the only change between runs is which
DIMMs are installed.

## Expected BIOS settings

| Setting | Value |
|---|---|
| BIOS version | 1804 (do not update during the search) |
| DRAM frequency | DDR5-3600, set manually (not Auto) |
| Primary timings | 30-30-30-58, set manually |
| DRAM voltage | 1.10 V |
| Memory controller voltage | 1.140 V, set manually (firmware cannot set 1.136 V) |
| EXPO / XMP | Disabled |
| Precision Boost Overdrive | Disabled (not Auto) |
| Curve Optimizer | Auto, with PBO Disabled (firmware offers no off choice) |

Operator confirmed these firmware limitations and that the settings were saved
and rebooted on 2026-10-23 (plan.md record). IMG_0227 shows the manual 1.14000 V
entry; its separate 1.136 V reading is telemetry, not the setpoint. IMG_0226
shows Curve Optimizer Auto and the available choices. Accept these documented
settings for the isolation search and keep them fixed across runs; Auto is the
recorded setting, without claiming an independently verified effective curve.

## Finding the slots

Each slot has its name printed on the board beside it, usually at one end
(`DIMM_A1`, `DIMM_A2`, `DIMM_B1`, `DIMM_B2`); a flashlight helps, and the CPU
cooler can hide it. The layout diagram near the front of the board manual
shows the same. On ASUS AM5 boards the order is normally, from the CPU
outward:

| Position from the CPU | Slot |
|---|---|
| 1st (closest) | A1 |
| 2nd | A2 |
| 3rd | B1 |
| 4th (nearest the board edge) | B2 |

So channel A is the two slots nearest the CPU and channel B the two farther
out; within a channel, "1" is the slot nearer the CPU. Two-DIMM runs use the
2nd and 4th slots. If the board's printing disagrees with this table, the
printing wins.

Linux cannot tell physical slots apart until two DIMMs are out. At `pair-A`'s
preflight, if the two sticks left in the 2nd and 4th slots appear as
`DIMM 1` on channels A and B, firmware's `DIMM 1` is the "2" slot and
`pair-A` is serials `13000000` and `19000000`; if they appear as `DIMM 0`,
the reverse. The agent records the mapping in plan.md.

## Operator: changing the DIMMs

1. Shut down, switch off and unplug. Touch the case metal before handling
   memory.
2. First time only: label all four sticks with their slot (the board prints
   `DIMM_A1`, `DIMM_A2`, `DIMM_B1`, `DIMM_B2` beside each slot) before any
   leave the board.
3. Install the run's two DIMMs (table above) in **A2 and B2**, the slots the
   board manual names for two DIMMs (usually the 2nd and 4th from the CPU;
   check the board's printing). Seat each until both latches click. Keep the
   others labelled and aside.
4. Power on. The first boot after a memory change can show a black screen for
   several minutes while memory trains. Wait.

## Operator: BIOS

1. Press Del at boot, switch to Advanced Mode (F7).
2. Set every value in the table above. With two DIMMs the board will try to
   train to 5600, so the frequency and timings must be set manually.
3. Photograph, with every value readable:
   - the Ai Tweaker page showing DRAM frequency and the voltages;
   - the DRAM timing page showing the primary timings;
   - the Precision Boost Overdrive page (Advanced → AMD Overclocking), and its
     Curve Optimizer page;
   - the EZ Mode summary (DIMM slots, frequency, BIOS version).
4. Save (F10) and boot.
5. Copy the photos to `~/memory-soak/<run>.bios/` on `9950`, then start an
   agent and ask it to run the next isolation step.

## Agent: checks before starting

1. Read plan.md's record to find the next run and its expected serials.
2. Run the preflight (no root needed):

       python3 scripts/preflight.py --run <date>-<run> --dimms 2 [--serials S1,S2]

   It checks DIMM count, one per channel, serials, configured speed 3600,
   BIOS version, visible RAM, no `bgperf_` containers, no other soak, a new
   run name and the input file, and writes `~/memory-soak/<run>.preflight.json`.
   For `pair-A` omit `--serials`, report the two serials found, and ask the
   operator to confirm they are the sticks labelled A2 and B2. For
   `four-dimm` use `--dimms 4 --serials 24000000,13000000,23000000,19000000`
   and check the printed slots match the table: firmware `DIMM 0` is slot 1
   and `DIMM 1` slot 2 (plan.md record).
3. Read every photo in `~/memory-soak/<run>.bios/` and compare each setting
   with the table above. A value not visible in any photo is unknown, not
   assumed; ask for a new photo.
4. Report both results to the operator. Any FAIL, mismatch or unknown value
   stops here: say what to change, and the operator fixes it and reboots.

## Agent: starting the soak

From the repository root, only after every check passes. Two-DIMM runs use
`--memory-gb 48`; `four-dimm` uses `--memory-gb 96` (about 80% of RAM, as
for the pairs; the baseline's default half did reproduce the fault):

    RUN=<date>-<run>
    git -C . rev-parse --short HEAD > ~/memory-soak/$RUN.revision
    setsid nohup python3 scripts/memory_soak.py --hours 24 --memory-gb 48 \
      --file ~/bgperf-inputs/mrt/bview.20260808.0000 \
      --sha256 bview.20260808.0000=ab7a99d366b511daa0fe42ba8c816136da06d2865585e3634ec66f4b5987fa02 \
      --out ~/memory-soak/$RUN > ~/memory-soak/$RUN.log 2>&1 &

Confirm with `python3 scripts/memory_soak_status.py` a few minutes later that
the run shows `RUNNING` and a first heartbeat. Tell the operator the expected
end time. Do not start BGP measurement, builds or other load on `9950` while
it runs.

## Agent: after the run

1. `python3 scripts/memory_soak_status.py ~/memory-soak/$RUN`. A run counts as
   clean only as `PASSED` (the full 24 h): the baseline ran 10 h before its
   first error. On `CORRUPTION FOUND` or `KERNEL TRAP` the run has failed and
   may be stopped early with `kill -TERM <pid>`.
2. Copy into `results/9950/$RUN/`: the run directory's files, `soak.log`,
   `revision`, `preflight.json` and `bios/` (the photos); write `SHA256SUMS`
   there and check each copy against its source with `cmp`.
3. Add a plan.md record: run, DIMMs and serials by slot, settings confirmed
   by photo, hours, events with `lane.bit`, peak temperatures, outcome, and
   the next run per plan.md's isolation steps.
4. Commit; push only with the operator's go-ahead. Leave `~/memory-soak` in
   place.
