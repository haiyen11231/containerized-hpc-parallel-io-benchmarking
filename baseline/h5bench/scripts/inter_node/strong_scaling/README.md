# Strong scaling — inter-node

TOTAL problem size is held **constant** while node count grows, so per-rank
workload shrinks proportionally. Answers: *does adding more nodes actually
speed up a fixed-size job, and does that speedup hold up the same way for
native and container?* The companion to `../weak_scaling/`, which instead
grows the total problem size in lockstep with node count.

## n8 removed (2026-10-25) — same unresolved issue as weak_scaling

`native_strong_8n` and `container_strong_8n` both failed on walltime on
2026-10-25 (1-2 of 10 reps completed in `02:30:00`, per-rep times of
~5900-6200s). While not as extreme as `weak_scaling`'s n8 (~9 MB/s, ~100x
slower than the old design), it's the same 2D `CONTIG`/`CONTIG` write
pattern at the same rank count (512) across the same 8 nodes — plausibly the
same underlying cause. **n8 is removed from `NODE_COUNTS` in both submit
scripts until `../weak_scaling/README.md`'s n8 investigation resolves it**,
rather than just re-budgeting a much larger walltime for a possibly-broken
measurement.

## Redesigned 2026-10-25 — now matches intra_node's total exactly, not a half-scale copy

Previously `DIM_2=1024` (not intra_node's `2048`) gave a half-scale 40 GB
total, a deliberate smoke-test reduction. Aligned now with the same
redesign applied to `../weak_scaling/` (see its README for the full
rationale): `DIM_2` is `2048`, so the fixed total is **80 GB** — the same
total intra_node's own job writes, and the same n1 total weak_scaling now
uses. `DIM_1` still halves every time node count doubles, holding
`ranks * DIM_1 * DIM_2` constant — i.e. the total dataset stays fixed at
every tier (that's what makes it strong scaling, unlike weak scaling where
it grows) — only now that fixed total is 80 GB instead of 40 GB.
**`REPS` is also now `5`** (was 10), matching weak_scaling's halving for the
same reason: per-rep size doubled, so halving reps keeps roughly the same
aggregate bytes moved per tier (old: 40 GB x10 = 400 GB; new: 80 GB x5 =
400 GB — this is why `02:30:00` stays sufficient, see below).

| Nodes | Ranks | DIM_1 | Per repetition | Stripe count |
|---|---|---|---|---|
| 1 | 64 | 2048 | 80 GB | 4 |
| 2 | 128 | 1024 | 80 GB | 8 |
| 4 | 256 | 512 | 80 GB | 16 |

`DIM_1=$((2048 / NODE_COUNT))` — clean integer division since node counts
are powers of two dividing 2048 exactly. `DIM_2` stays fixed at 2048 (only
`DIM_1`, `NP`, and `STRIPE_COUNT` change with `NODE_COUNT`).

**n1 can stall in queue** even though its job is small — `q2` (n1's queue)
has been hitting a dynamic per-user running-job throttle (`max_run =
[u:PBS_GENERIC=0]`, observed live via `qstat -Qf q2`) unrelated to this
job's size or walltime; `q4` (n2/n4) hasn't shown this. If n1 sits
in `Q` with `"User has reached queue q2 running job limit"`, that's this
throttle, not a script problem — it's time-varying (fairshare-style), so
wait and recheck `qstat -Qf q2 | grep max_run` rather than resubmitting.

Stripe count now scales as `NODE_COUNT * 4` (4/8/16), the same formula and
anchor as `weak_scaling` (intra_node's own `stripe-count=4` at the
equivalent 64-rank/80GB size) — previously this used `NODE_COUNT * 2`,
which was inconsistent with both intra_node's baseline and weak_scaling's
own anchor. The original rationale for scaling it at all was "more total
bytes need more OSTs" — that doesn't strictly apply here since total bytes
are fixed, but rank count (concurrent writers hitting Lustre at once) still
doubles each tier, which is its own reason to spread the stripe wider. As
with weak scaling, verify the `lfs getstripe` output actually shows what was
requested — Aspire 2A's `/scratch` has only 17+ OSTs (see `CLAUDE.md`).

Access pattern is fixed at `CONTIG`/`CONTIG`, same reasoning as
`weak_scaling`: access-pattern effects are isolated separately, in
`../../intra_node/write/`.

## Write only

Same reasoning as `weak_scaling`: a read in the same config would be served
from page cache rather than Lustre.

## Toolchain and launch model

Identical to `../weak_scaling/`: native uses the `build_hdf5_1107` driver
against a locally-built HDF5 1.10.7; container's `MPI_CONFIG` is exactly
`../../intra_node/write/contig_contig`'s container config (`--mca pml ucx -x
UCX_TLS=^cma`, no cross-node-specific flags added — UCX picks its own
transport/device). See `../weak_scaling/README.md` for the full rationale on
both.

## REPS and walltime are fixed in the .pbs file, not passed at submission

Both `.pbs` files hardcode `REPS=5` (was 10) and carry their own
`#PBS -l walltime=02:30:00` header. The previous 40GB/10-rep design
completed `native_strong_1n/2n/4n` and `container_strong_1n/2n/4n` cleanly
within this budget (roughly 1h29m-2h07m across the three tiers); the new
80GB/5-rep design moves the same aggregate bytes per tier (80GB x5 = 400GB,
same as 40GB x10), so `02:30:00` should still hold comfortably, though this
hasn't been re-measured at the new size yet. (n8 needed far more and is
removed — see the n8 section above.) This clears `q2`/`q4`'s `>2h` minimum,
so n1/n2/n4 route to their normal production queue rather than `qdev`.

## Node placement: scatter:excl (restored 2026-10-25)

`place=scatter:excl`, matching `weak_scaling`'s restored exclusive
allocation — see `../weak_scaling/README.md`'s "Node placement" section for
the full rationale (`CLAUDE.md` requires exclusive allocation to prevent
other users' jobs sharing a node from contaminating the comparison) and the
known tradeoff (exclusive multi-node allocations can stall in queue with
`"Insufficient amount of resource: node_pool"`).

## Running it

```bash
./submit_native_strong_job.sh
./submit_container_strong_job.sh
```

Same serial job-chaining as `weak_scaling` (`-W depend=afterok:<prev job
id>`): each node-count tier only starts once the previous one finishes
successfully, so concurrent writes don't contend for the same OSTs. Don't
run the native and container chains at the same time for the same reason.

The chain runs `4,2,1` — now that n8 is removed, n4 is the largest remaining
tier, so it still runs first for the same reason this ordering originally
existed: the chain halts on the first failure, so running the
most resource-constrained tier first secures that data point before risking
a failure on an easier one, rather than losing it to an upstream failure on
n1/n2.

### Independent variant

`submit_native_strong_job_independent.sh` / `submit_container_strong_job_independent.sh`
submit all three tiers at once with no `-W depend=afterok` chaining — same
rationale and tradeoff as `../weak_scaling/README.md`'s "Independent
variant" section: use this when the per-user running-job throttle (`max_run`)
is the actual bottleneck rather than Lustre contention, since a serial chain
gains nothing against a throttle that blocks the *first* job regardless of
dependency state.

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
