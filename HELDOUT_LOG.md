# Held-out runs

Each held-out split is run exactly once, after the policy and the baseline parser were frozen at commit 8ac2550.

- `replies --split heldout` — started 2026-10-03T19:56:01Z, finished 2026-10-03T19:56:01Z
- `experiment --split test` — started 2026-10-03T19:56:01Z, finished 2026-10-03T20:01:04Z
- `experiment --split shifted` — started 2026-10-03T20:01:04Z, finished 2026-10-03T20:04:05Z
- `experiment --sensitivity --n 3000` — started 2026-10-03T20:04:05Z, finished 2026-10-03T20:09:07Z
- `experiment --ablations --n 4000` — started 2026-10-03T20:09:07Z, finished 2026-10-03T20:10:35Z
