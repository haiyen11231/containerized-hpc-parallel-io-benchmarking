# Strong scaling — inter-node

**Total** workload is held constant while rank count grows, so per-rank work shrinks. Answers: *does adding nodes actually make a fixed job finish faster, and does the container degrade differently than native?*

| Nodes | Ranks | `DIM_1` (particles/rank) | MiB/rank/timestep | Per repetition |
|---|---|---|---|---|
| 1 | 128 | 1 048 576 | 32 | 20 GiB |
| 2 | 256 | 524 288 | 16 | 20 GiB |
| 4 | 512 | 262 144 | 8 | 20 GiB |
| 8 | 1024 | 131 072 | 4 | 20 GiB |

`TOTAL_PARTICLES = 128 M` (134 217 728) × 32 B = 4 GiB per timestep, × 5
timesteps = **20 GiB per repetition at every tier**. 10 repetitions per job.

`DIM_1` is computed in the PBS script as `TOTAL_PARTICLES / NP`, not fixed in
the template — that is the whole difference from weak scaling. A guard aborts
the job if the division is not exact, since silent truncation would let the
total drift between tiers and quietly invalidate the comparison.

The 1-node point is deliberately identical to weak scaling's 1-node point,
giving the two experiments a shared anchor.

## What to expect

Perfect strong scaling would halve the runtime each time nodes double. It won't:
as `DIM_1` shrinks, each rank writes less per call, so fixed per-operation costs
(HDF5 metadata, MPI-IO coordination, Lustre MDT round-trips) take a growing
share. The *shape* of that falloff is the result — and whether the container's
curve falls off faster is the native-vs-container question.

This is the h5bench counterpart to IOR's strong-scaling run, where FPP degraded
faster than shared-file, pointing at Lustre MDS contention. Worth checking
whether HDF5's own metadata handling reproduces or changes that story.

## Shared conventions

Access pattern fixed at `CONTIG`/`CONTIG`; `READ_OPTION=FULL`; write and read in
one config so the read finds the file the write just produced; Lustre striping
`-c 4 -S 1m`; hybrid launch model (host `mpirun` + per-rank `apptainer exec`).

The same caveats as weak scaling apply — see `../weak_scaling/README.md` for
read-cache inflation, the binary-units-labelled-as-decimal trap, and why CSVs
land under `payload/<variant>/n<N>/<uuid>/`.
