# Working in SL-memtest

Read README.md and plan.md first.

- Record progress and decisions in plan.md, with commit references.
- Do not run a soak while a BGP measurement runs on the same host, or the
  reverse; no BGP measurement on `9950` until plan.md's acceptance passes.
- Copy a run's results into `results/<host>/<run>/` with a `SHA256SUMS`, and
  verify the copy before removing anything under `~/memory-soak`.
- Run the tests before committing. Use conventional commit messages and
  `git -C` for Git commands.
- Do not push or create a remote without explicit authorization.
