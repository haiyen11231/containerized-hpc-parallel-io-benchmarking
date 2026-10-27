# IOR — inter-node, weak scaling

Node count is the scaling variable: **1, 2, 4, 8 nodes at 64 ranks per
node** (64 → 512 ranks) — 64 ranks/node matches `../../intra_node/`'s rank
count, not a full physical node's 128. Per-rank work is held constant, so
the total problem grows with the node count.

## Rebuilt to match ../../intra_node/'s combo and network setup

This study previously swept the full 2×2 (API × model) factorial per node
count — 16 jobs per variant. It's now reduced to the same two combos as
`../../intra_node/`, for the same reason that redesign gave: a prior full
sweep is what established which combos matter, so re-sweeping everything at
every scale doesn't add information over just comparing the two most
different combos directly.

| dimension | value |
|---|---|
| **nodes** | 1, 2, 4, 8 (the scaling variable) |
| **Combo A** | `MPIIO` + `shared` |
| **Combo B** | `POSIX` + `fpp` |

4 node counts × 2 combos = **8 jobs per variant** (was 16).

## Network setup now matches intra_node

**Native** MPI_CONFIG was already identical to intra_node's (`--mca btl
^openib --mca pml ucx --mca orte_base_help_aggregate 0 --mca
opal_common_ucx_opal_mem_hooks 1 -x UCX_LOG_LEVEL=ERROR`) — no change needed
there.

**Container** MPI_CONFIG changed from the old inter-node-specific approach
(`--mca btl vader,tcp,self --mca btl_tcp_if_include hsn0 --mca
oob_tcp_if_include hsn0`, used when this container's OpenMPI was assumed to
have no UCX) to intra_node's `--mca pml ucx -x UCX_TLS=^cma` — exactly the
same flags, no manual BTL/interface wiring.

**Two unresolved caveats carried over from this change, not yet verified:**
1. `ior-backup`'s own README documented this exact container image as having
   *no* UCX ("no UCX in the apt build"). If that still holds, this `mpirun`
   may fail outright at startup — a successful run is itself evidence the
   old finding doesn't (or no longer) apply to this SIF.
2. Unlike the old `hsn0`-pinned approach, there's no explicit interface pin
   here — UCX picks its own transport/device. Verify on the first real run
   (job log, or `-x UCX_LOG_LEVEL=INFO`) that cross-node traffic actually
   routes over Slingshot rather than silently falling back to a slower path.

## Also carried over from the intra_node redesign

- **`-w` (write-only)** added to the IOR invocation. Without it, IOR runs
  write and read back-to-back in one job, and the read is served from this
  node's page cache (not Lustre) since the file was written milliseconds
  earlier — confirmed directly in `../../intra_node/` as a ~50× inflation.
  Same mechanism applies here.
- **Dead `DIRECT_IO_FLAG` commented-out block removed** (was never enabled,
  labeled "not sure about MPIIO bypass" in the original design).

## Stripe count and rank count now also match intra_node

- **Stripe count now scales with node count: `STRIPE_COUNT=$((NODE_COUNT *
  4))`** → 4/8/16/32 for 1/2/4/8 nodes, not a flat `4` (which itself had
  replaced this study's original flat `8`). More nodes writing concurrently
  need more OSTs in the stripe, or one OST becomes the bottleneck regardless
  of how many nodes are pushing data at it — same rationale and formula
  already used in h5bench's weak-scaling study. **Verify the `lfs getstripe`
  output right after `setstripe`, especially at n=8 (32)** — Aspire 2A's
  `/scratch` has only 17+ OSTs (see `CLAUDE.md`), and Lustre silently clamps
  a request above what's actually available rather than erroring.
- **Ranks/node changed `128` → `64`**, matching `../../intra_node/`'s rank
  count (`select=...:ncpus=64:mpiprocs=64`, `--map-by ppr:64:node`). This
  also changes total data per node at fixed `B=128m`/rank: **8 GiB/node**
  (was 16 GiB/node at 128 ranks), so totals across the sweep are now 8/16/32/64
  GiB for 1/2/4/8 nodes.
- **Walltime (`01:00:00`) was not re-checked against the new, smaller
  per-node total** — if anything it should need *less* time now, so this is
  not expected to be a problem, but it hasn't been re-verified empirically.
  Separately: at 64 ncpus/node, a 1-node job (64 ncpus total) with
  `walltime=01:00:00` is below `q2`'s `>2h` floor and would route to `qdev`
  — same tradeoff already accepted in the h5bench scaling studies.

## Still unchanged from the original inter-node design

- **Transfer size fixed at `4m`**, block size fixed at `128m`/rank — the
  weak-scaling invariant (per-rank work constant). `place=scatter:excl`
  resource shape otherwise unchanged.

## Output

```
logs/<job>.out                                PBS job output
<variant>/<api>/<model>/ior_n<N>.txt          one file per node count
```

## Running it

```bash
./submit_native_weak_job.sh       # 8 jobs
./submit_container_weak_job.sh    # 8 jobs
```

8 nodes × 64 = 512 ncpus routes to `q5`.
