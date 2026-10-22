# IOR — inter-node, weak scaling

Node count is the scaling variable: **1, 2, 4, 8 nodes at 128 ranks per node** (128 → 1024 ranks). Per-rank work is held constant, so the total problem grows with the node count. This matches the convention used by h5bench's inter-node studies.

---

## 1. What it varies

| dimension | values |
|---|---|
| **nodes** | 1, 2, 4, 8 (the scaling variable) |
| **API** | `POSIX`, `MPIIO` |
| **Access model** | `shared`, `fpp` |

16 jobs per variant (4 node counts × 2 APIs × 2 models), 10 IOR iterations each.

## 2. What weak scaling asks here

Per-rank data is fixed, so **aggregate bandwidth should grow linearly with node count** — 8 nodes should deliver 8× the bandwidth of 1 node. It does not, and how far it falls short is the result: that gap is where Lustre stops scaling.

This is the I/O analogue of the OSU collective weak-scaling study, but the bottleneck is different. There the limit was shared-memory or network transport; here it is OST bandwidth, lock contention, and metadata-server load.

## 3. Resources

```bash
-l select=${NODES}:ncpus=128:mpiprocs=128:mem=64gb
#PBS -l place=scatter:excl
```

**`place=scatter:excl` is what makes this inter-node.** Without `scatter`, PBS could pack several chunks onto one host and an "8-node" job would quietly run on fewer, inflating the result. `ncpus` matches `mpiprocs` (project convention) and the full node is genuinely used.

Striping is pinned with `lfs setstripe -c 8 -S 1m` and read back with `lfs getstripe`, identically in both variants — see `../../intra_node/README.md` section 2 for why that matters.

## 4. Output

```
logs/<job>.out                                PBS job output
<variant>/<api>/<model>/ior_n<N>.txt          one file per node count
```

Paths carry variant, API, model and node count, so the 32 jobs cannot collide.

## 5. Running it

```bash
./submit_native_weak_job.sh       # 16 jobs
./submit_container_weak_job.sh    # 16 jobs
```

8 nodes × 128 = 1024 ncpus routes to `q5`.

## 6. Results

[`../../../results/inter_node/weak_scaling/README.md`](../../../results/inter_node/weak_scaling/README.md).
