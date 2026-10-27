# Weak scaling — inter-node

Per-rank workload is held **constant** while node count grows, so total data
volume grows proportionally. Answers: *does the native/container gap widen
as the job gets bigger?* — the cross-node counterpart to
`../../intra_node/write/`, which asks the same question for rank count
packed onto a single node.

## Redesigned 2026-10-25 — now reuses intra_node's config exactly, not a scaled-down copy

The first design (`DIM_1=512`, `DIM_2=1024`, a deliberate 1/8-scale
reduction from intra_node, 10 reps) produced results too noisy to draw any
conclusion from — `native_weak_4n`'s observed rate had a 95% CI spanning
0.03-0.93 GB/s across its 10 reps (per-rep time ranged 27-200s for identical
work), and that same design's n8 tier additionally showed an unexplained
~100x slowdown (see git history for that investigation) that was never
resolved. Rather than keep tuning walltime around noise, this version drops
the scaled-down sizing entirely:

- **`DIM_1`/`DIM_2` are now `2048`/`2048`** in `h5bench_config.json.template`
  — identical to `../../intra_node/write/contig_contig`. The n1 tier of this
  study and that intra_node job are now the *same* per-rank configuration;
  only the launch path (this study's `.pbs` vs. that one) differs.
- **`REPS=5`**, not 10 — halved to keep total wall-clock reasonable now that
  per-rank size (and so per-rep time) is 8x larger than the old design.
- **Only `n1`/`n2`/`n4`** — n8 stays excluded (see git history: it showed a
  severe, unresolved slowdown in the old design and was never re-validated).
- **Stripe count is now `NODE_COUNT * 4`** (4/8/16), anchored to
  intra_node's own fixed `stripe-count=4` at the equivalent 64-rank/80GB
  size, rather than the old formula's arbitrary `NODE_COUNT * 2` (which gave
  a *lower* stripe count than intra_node uses for the same per-node size at
  n1 — an inconsistency in the old design).
- **All prior results (both variants, all tiers) were deleted** before this
  redesign — they're not comparable to the new sizing and kept causing
  confusion sitting alongside it.

The only two parameters that change with `NODE_COUNT` are `NP` (ranks) and
`STRIPE_COUNT` — `DIM_1`/`DIM_2` never do, by construction of weak scaling.

| Nodes | Ranks | Per repetition | Stripe count |
|---|---|---|---|
| 1 | 64 | 80 GB | 4 |
| 2 | 128 | 160 GB | 8 |
| 4 | 256 | 320 GB | 16 |

2048×2048 = 4,194,304 particles/rank, at 32 bytes/particle = 128 MiB/rank/
timestep × 10 timesteps = 1.25 GiB/rank total (fixed at every tier, matching
intra_node's own per-rank total exactly).

**n1 can stall in queue** even though its job is small — `q2` (n1's queue)
has been hitting a dynamic per-user running-job throttle (`max_run =
[u:PBS_GENERIC=0]`, observed live via `qstat -Qf q2`) unrelated to this
job's size or walltime; `q4` (n2/n4) hasn't shown this. If n1 sits
in `Q` with `"User has reached queue q2 running job limit"`, that's this
throttle, not a script problem — it's time-varying (fairshare-style), so
wait and recheck `qstat -Qf q2 | grep max_run` rather than resubmitting.

Access pattern is fixed at `CONTIG`/`CONTIG` so scaling behavior is not
confounded with access-pattern effects — those are isolated in
`../../intra_node/write/`.

## Write only

A read in the same config would be served from page cache (the file was
just written, on the same nodes, milliseconds earlier) rather than Lustre,
especially at these data volumes.

## Toolchain

Native uses the same driver build as `intra_node/write` — `build_hdf5_1107`
against a locally-built HDF5 1.10.7 (`module load intel/2022.0.2;
openmpi/4.1.2-hpe`, with the HDF5 lib on `LD_LIBRARY_PATH`). Container
driver/SIF/binary paths match `intra_node`'s container write job, plus the
cross-node-only additions below.

## Launch model

Same hybrid model as `../../intra_node/`: host `mpirun` fans ranks out via
PBS, each rank enters the container through `apptainer exec`. Required here:
the container's generic OpenMPI has no PBS `tm` support and cannot spawn
ranks on remote nodes. See `../../intra_node/README.md` for the full
rationale.

**Container MPI_CONFIG is identical to `../../intra_node/`'s** —
`--mca pml ucx -x UCX_TLS=^cma`, no manual BTL/interface wiring added for
cross-node. Caveat: with no explicit interface pin, UCX picks its own
transport/device — this hasn't been independently verified to be routing
over Slingshot rather than falling back to a slower path.

## REPS and walltime are fixed in the .pbs file, not passed at submission

Both `h5bench_native_weak.pbs` and `h5bench_container_weak.pbs` hardcode
`REPS=5` and `#PBS -l walltime=02:30:00`. `02:30:00` is generous rather than
tightly measured: intra_node's own n1-equivalent job (identical per-rank
config, 64 ranks, 80 GB) completes 10 reps in ~9 minutes total
(51-60s/rep), so even n4 at 4x the ranks/data and only 5 reps has wide
margin inside `02:30:00` unless bandwidth degrades badly at scale — which is
exactly the open question this redesign exists to answer cleanly.
`02:30:00` also clears `q2`/`q4`'s `>2h` minimum, so n1/n2/n4 route to their
normal production queue rather than `qdev`.

## Node placement: back to scatter:excl (2026-10-25)

`place=scatter:excl`, restored as of this redesign — per `CLAUDE.md`,
exclusive allocation (`place=excl` for single-node, `scatter:excl` for
multi-node) is required to prevent other users' jobs sharing a node from
contaminating a native-vs-container comparison on this shared,
`sharing=default_shared` cluster. An earlier version of this study had
dropped `excl` because exclusive multi-node allocations were stalling in
queue (`"Insufficient amount of resource: node_pool"`) at the 4/8-node
tiers — if that recurs here (job sits in `Q` rather than starting), that's
the known tradeoff resurfacing, not a new script problem. Since n8 is gone
and node counts now top out at 4, exclusive allocation is more likely to
clear than it was before.

## Running it

```bash
./submit_native_weak_job.sh
./submit_container_weak_job.sh
```

Each submit script loops `NODE_COUNTS=(1 2 4)` and **chains the three jobs
serially** (`-W depend=afterok:<prev job id>`): the n2 job only starts once
n1 finishes successfully, and so on. This is deliberate — running these
tiers concurrently means multiple concurrent writes competing for the same
OSTs, which contaminates every tier's bandwidth measurement with cross-job
contention. Running the native and container submit scripts themselves at
the same time still does the same thing to each other, so don't launch both
chains together.

### Independent variant

`submit_native_weak_job_independent.sh` / `submit_container_weak_job_independent.sh`
submit all three tiers at once with no `-W depend=afterok` chaining. Use this
instead when the bottleneck is the per-user running-job throttle (`max_run`,
seen as `qstat`'s `"User has reached queue <q> running job limit"` —
check the live value with `qstat -Qf <queue> | grep max_run`) rather than
Lustre contention: a serial chain gains nothing against that throttle (a
held job still can't run until its dependency clears *and* the throttle
allows it), so whichever tier happens to clear first still has to wait its
turn. The tradeoff: no guaranteed single-tier-at-a-time on Lustre anymore —
if the throttle clears for multiple tiers simultaneously, their writes can
run concurrently and contend for the same OSTs. Prefer the dependent version
once scheduling isn't the bottleneck.

## Units

h5bench switches between `MB/s` and `GB/s` depending on magnitude, and both
are **binary** despite the labels (`1004.800 MB/s` = 1004.8 MiB/s; 1 "GB" =
1024 "MB"). Any analysis script must normalize using the unit column —
averaging the bare numbers produces nonsense.

## Where results land

The driver rewrites `CSV_FILE` to `<directory>/<uuid>/<csv>`
(`src/h5bench.py:370`), so CSVs appear under `payload/<variant>/n<N>/<uuid>/`
rather than in the report directory. The `write_repN.csv` naming preserves
the repetition index, since the UUIDs are random and carry no ordering.

`<variant>/n<N>/` holds the generated `config_repN.json` and
`driver_repN.log` (container only) for each repetition.
