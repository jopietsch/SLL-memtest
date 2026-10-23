# SL-memtest

Memory-integrity testing for the Second Looks Lab hosts. Host `9950` flips
bits in RAM under load while Memtest86+ passes; this repository holds the
search for the cause: the plan and its record ([plan.md](plan.md)), the soak
and status scripts (`scripts/`), their tests (`tests/`), and each soak's
results (`results/<host>/<run>/`, with `SHA256SUMS`).

Check every soak on a host:

    python3 scripts/memory_soak_status.py

Run the tests with `python3 -m pytest` (pytest only; no other dependencies).
