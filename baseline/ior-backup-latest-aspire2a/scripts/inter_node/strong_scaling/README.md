# IOR — inter-node, strong scaling

Node count is the scaling variable: **1, 2, 4, 8 nodes at 64 ranks per
node** (64 → 512 ranks) — 64 ranks/node matches `../../intra_node/`'s and
`../weak_scaling/`'s rank count, not a full physical node's 128. The
**total problem size is held constant** (64 GiB) and divided among the
ranks, so per-rank work shrinks as nodes are added.

## Rebuilt to match ../../intra_node/'s combo and network setup

Same redesign as `../weak_scaling/`: reduced from the full 2×2 (API × model)
factorial to the same two combos as `../../intra_node/`.

| dimension | value |
|---|---|
| **nodes** | 1, 2, 4, 8 (the scaling variable) |
| **Combo A** | `MPIIO` + `shared` |
| **Combo B** | `POSIX` + `fpp` |

4 node counts × 2 combos = **8 jobs per variant** (was 16).

## Network setup now matches intra_node

Identical change to `../weak_scaling/`: native's MPI_CONFIG already matched
intra_node's and needed no change; container's MPI_CONFIG switched from the
old `vader,tcp,self` + `hsn0`-pinned approach to intra_node's `--mca pml ucx
-x UCX_TLS=^cma`. See `../weak_scaling/README.md`'s "Network setup" section
for the full flag list and the two unresolved caveats (the documented
no-UCX finding for this container image, and the lack of explicit Slingshot
interface pinning under UCX) — both apply identically here.

## Also carried over from the intra_node redesign

- **`-w` (write-only)** added — same cache-inflation reasoning as
  `../weak_scaling/README.md`.
- **Dead `DIRECT_IO_FLAG` commented-out block removed.**

## Stripe count and rank count now also match weak_scaling

- **Stripe count now scales with node count: `STRIPE_COUNT=$((NODE_COUNT *
  2))`** → 2/4/8/16 for 1/2/4/8 nodes, matching `../weak_scaling/`'s current
  formula exactly (replacing this study's original flat `8`). Same
  rationale: more nodes writing concurrently need more OSTs in the stripe.
  **Verify the `lfs getstripe` output, especially at n=8 (16)** — Aspire
  2A's `/scratch` has only 17+ OSTs (see `CLAUDE.md`).
- **Ranks/node changed `128` → `64`**, matching `../../intra_node/`'s and
  `../weak_scaling/`'s rank count. Since total data is fixed at 64 GiB here
  (not grown with ranks, as in weak scaling), halving ranks/node changes the
  per-rank block size at every tier: `B = 64 GiB / NP` now gives
  NODES=1 → **1024m/rank**, 2 → 512m, 4 → 256m, 8 → 128m/rank (was
  512m/256m/128m/64m at 128 ranks/node) — the heaviest per-rank case (n=1) is
  now double what it was.
- **Walltime (`01:00:00`) was not re-checked** against the new per-node
  shape. At 64 ncpus/node, a 1-node job is also now below `q2`'s `>2h` floor
  and would route to `qdev` — same tradeoff `../weak_scaling/` already
  accepted.

## Still unchanged from the original inter-node design

- **Transfer size fixed at `4m`** — the strong-scaling invariant is the
  *block* size shrinking (see above), not transfer size. `place=scatter:excl`
  resource shape otherwise unchanged.

## Weak vs strong — why both

| | weak | strong |
|---|---|---|
| held fixed | per-rank data | **total data** |
| per-rank I/O as nodes grow | constant | **shrinks** |
| ideal aggregate bandwidth | grows 8× | grows 8× |
| what a shortfall means | Lustre cannot absorb more total data | per-rank I/O became too small to be efficient |

## Output

```
logs/<job>.out                                PBS job output
<variant>/<api>/<model>/ior_n<N>.txt          one file per node count
```

## Running it

```bash
./submit_native_strong_job.sh       # 8 jobs
./submit_container_strong_job.sh    # 8 jobs
```

8 nodes × 64 = 512 ncpus routes to `q5`.
