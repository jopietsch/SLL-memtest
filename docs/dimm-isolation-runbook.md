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
| Memory controller voltage | 1.136 V (as before), set manually if the board allows |
| EXPO / XMP | Disabled |
| Precision Boost Overdrive | Disabled (not Auto) |
| Curve Optimizer | Off / none |

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
   operator to confirm they are the sticks labelled A2 and B2.
3. Read every photo in `~/memory-soak/<run>.bios/` and compare each setting
   with the table above. A value not visible in any photo is unknown, not
   assumed; ask for a new photo.
4. Report both results to the operator. Any FAIL, mismatch or unknown value
   stops here: say what to change, and the operator fixes it and reboots.

## Agent: starting the soak

From the repository root, only after every check passes:

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
