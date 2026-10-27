# Strong scaling — intra-node

TOTAL problem size is held **constant** at 80 GB while **rank count on a
single node** grows (16/32/64), so per-rank workload shrinks proportionally.
This is the intra-node counterpart to `../../inter_node/strong_scaling/`,
which asks the same question but scales node count instead. Built
2026-10-25 for the same reason as `../weak_scaling/`: to check whether the
noise seen in inter_node scaling is a cross-node/network effect or shows up
from rank-count scaling alone, with no network involved (everything stays on
one node). See `../weak_scaling/README.md` for the full rationale.

`DIM_1`(64 ranks)=2048, `DIM_2`=2048 — identical to `../write/contig_contig`
(the 64-rank tier of this study **is** that job, just run from here with
`REPS=5` instead of 10). `DIM_1` shrinks as rank count grows, holding
`RANKS * DIM_1 * DIM_2` constant — i.e. the total dataset stays fixed at
every tier (that's what makes it strong scaling, unlike weak scaling where
it grows).

| Ranks | DIM_1 | Per repetition | Stripe count |
|---|---|---|---|
| 16 | 8192 | 80 GB | 1 |
| 32 | 4096 | 80 GB | 2 |
| 64 | 2048 | 80 GB | 4 |

`DIM_1=$((131072 / RANKS))` — clean integer division since 16/32/64 all
divide 131072 (`= 64 * 2048`) exactly. `DIM_2` stays fixed at 2048.
`STRIPE_COUNT=$((RANKS / 16))`, same anchor and formula as
`../weak_scaling/` and `../../inter_node/strong_scaling/`.

## Why 16/32/64, not 32/64/128

Same reasoning as `../weak_scaling/README.md`: 128 ranks would need every
physical core on the node (128/node per `CLAUDE.md`) with no headroom, and
16/32/64 keeps every tier in the same `q2` queue band for simpler
scheduling.

## Single node throughout — no node-count variable at all

Every tier requests `select=1:ncpus=${RANKS}:mpiprocs=${RANKS}` with
`place=excl` (not `scatter:excl` — never more than one node). Node count is
fixed at 1 for every tier; only rank count changes, so any noise seen here
can't be attributed to inter-node network effects or multi-node Lustre
access patterns.

## Toolchain and launch model

Identical to `../write/contig_contig` and `../weak_scaling/`: native uses
the `build_hdf5_1107` driver; container's `MPI_CONFIG` is `--mca pml ucx -x
UCX_TLS=^cma` (no BTL/interface wiring needed — single node, no cross-node
traffic). `--map-by ppr:${RANKS}:node` packs all ranks onto the one node.

## REPS and walltime are fixed in the .pbs file, not passed at submission

Both `.pbs` files hardcode `REPS=5` and `#PBS -l walltime=02:30:00`. The
64-rank tier (80 GB) already runs in ~9 minutes for 10 reps as
`../write/contig_contig` — `02:30:00` has very wide margin at every tier
here, including the smaller 16/32-rank ones where per-rank work is larger
but still bounded by the same 80 GB total. Clears `q2`'s `>2h` minimum, so
all tiers route to the normal production queue rather than `qdev`.

## Running it

```bash
./submit_native_intra_strong_job.sh
./submit_container_intra_strong_job.sh
```

Each submit script loops `RANKS_LIST=(16 32 64)` ascending and chains the
three jobs serially (`-W depend=afterok:<prev job id>`), same rationale as
`../weak_scaling/`. **Unlike `../../inter_node/strong_scaling/`'s
`4,2,1`-descending order**: that ordering existed to secure the
most-resource-constrained (most nodes) tier first, in case a large
multi-node allocation stalled in queue. That risk doesn't apply here — every
tier reserves exactly one exclusive node regardless of rank count, so
there's no tier that's harder to schedule than another, and ascending order
(matching `../weak_scaling/`) is simpler with no tradeoff.

### Independent variant

`submit_native_intra_strong_job_independent.sh` / `submit_container_intra_strong_job_independent.sh`
submit all three tiers at once with no `-W depend=afterok` chaining — same
use case as `../weak_scaling/README.md`'s "Independent variant" section.

## Units

h5bench switches between `MB/s` and `GB/s` depending on magnitude, and both
are **binary** despite the labels (`1004.800 MB/s` = 1004.8 MiB/s; 1 "GB" =
1024 "MB"). Any analysis script must normalize using the unit column —
averaging the bare numbers produces nonsense.

## Where results land

The driver rewrites `CSV_FILE` to `<directory>/<uuid>/<csv>`
(`src/h5bench.py:370`), so CSVs appear under `payload/<variant>/r<RANKS>/<uuid>/`
rather than in the report directory. The `write_repN.csv` naming preserves
the repetition index, since the UUIDs are random and carry no ordering.

`<variant>/r<RANKS>/` holds the generated `config_repN.json` and
`driver_repN.log` (container only) for each repetition.
