# Weak scaling — intra-node

Per-rank workload is held **constant** while **rank count on a single node**
grows (16/32/64), so total data volume grows proportionally. This is the
intra-node counterpart to `../../inter_node/weak_scaling/`, which asks the
same question but scales node count instead. Built 2026-10-25 because the
inter_node weak/strong scaling results still looked noisy even after
restoring exclusive node placement — this study isolates whether that noise
is a cross-node/network effect (MPI over Slingshot, multi-node Lustre access
patterns) or shows up from rank-count scaling alone, with no network
involved at all (everything stays on one node).

Per-rank config (`DIM_1=2048`, `DIM_2=2048`, `CONTIG`/`CONTIG`, 10
timesteps) is identical to `../write/contig_contig` — the 64-rank tier of
this study **is** that job, just run from here with `REPS=5` instead of 10.

| Ranks | Per repetition | Stripe count |
|---|---|---|
| 16 | 20 GB | 1 |
| 32 | 40 GB | 2 |
| 64 | 80 GB | 4 |

2048x2048 = 4,194,304 particles/rank, at 32 bytes/particle = 128 MiB/rank/
timestep x 10 timesteps = 1.25 GiB/rank total (fixed at every tier — that's
what makes it weak scaling). `STRIPE_COUNT=$((RANKS / 16))`, anchored to
`../write/contig_contig`'s own `stripe-count=4` at the 64-rank/80GB size —
same anchor `../../inter_node/weak_scaling/` uses, just driven by `RANKS`
instead of `NODE_COUNT`.

## Why 16/32/64, not 32/64/128

128 ranks would need SMT (128 physical cores/node per `CLAUDE.md`, so 128
ranks already uses every physical core) — staying at 16/32/64 keeps one
rank per physical core with headroom, and keeps all three tiers in the same
`q2` queue band (`ncpus` 2-64) for simpler, more comparable scheduling.

## Single node throughout — no node-count variable at all

Every tier requests `select=1:ncpus=${RANKS}:mpiprocs=${RANKS}` with
`place=excl` (not `scatter:excl` — there's never more than one node, so
`scatter` doesn't apply). This is the key methodological difference from
`../../inter_node/weak_scaling/`: node count is fixed at 1, only rank count
changes, so any noise seen here can't be attributed to inter-node network
effects or multi-node Lustre access patterns — those are entirely absent.

## Toolchain and launch model

Identical to `../write/contig_contig`: native uses the `build_hdf5_1107`
driver against a locally-built HDF5 1.10.7; container's `MPI_CONFIG` is
`--mca pml ucx -x UCX_TLS=^cma` (no BTL/interface wiring needed — single
node, no cross-node traffic at all). `--map-by ppr:${RANKS}:node` packs all
ranks onto the one node regardless of tier.

## REPS and walltime are fixed in the .pbs file, not passed at submission

Both `.pbs` files hardcode `REPS=5` and `#PBS -l walltime=02:30:00`. The
64-rank tier (80 GB) already runs in ~9 minutes for 10 reps as
`../write/contig_contig` (see that combo's own data) — even with more
reps or at the smaller 16/32-rank tiers, `02:30:00` has very wide margin.
This clears `q2`'s `>2h` minimum, so all tiers route to the normal
production queue rather than `qdev`.

## Running it

```bash
./submit_native_intra_weak_job.sh
./submit_container_intra_weak_job.sh
```

Each submit script loops `RANKS_LIST=(16 32 64)` and chains the three jobs
serially (`-W depend=afterok:<prev job id>`), same rationale as
`../../inter_node/weak_scaling/`: avoid concurrent writes contending for the
same OSTs. Don't run the native and container chains at the same time for
the same reason.

### Independent variant

`submit_native_intra_weak_job_independent.sh` / `submit_container_intra_weak_job_independent.sh`
submit all three tiers at once with no `-W depend=afterok` chaining — same
use case as `../../inter_node/weak_scaling/README.md`'s "Independent
variant" section (the per-user running-job throttle, not Lustre contention,
is the actual bottleneck).

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
