# IOR — inter-node, strong scaling

Node count is the scaling variable: **1, 2, 4, 8 nodes at 128 ranks per node** (128 → 1024 ranks). The **total problem size is held constant** and divided among the ranks, so per-rank work shrinks as nodes are added.

---

## 1. What it varies

| dimension | values |
|---|---|
| **nodes** | 1, 2, 4, 8 (the scaling variable) |
| **API** | `POSIX`, `MPIIO` |
| **Access model** | `shared`, `fpp` |

16 jobs per variant, 10 IOR iterations each.

## 2. Weak vs strong — why both

They fail in different ways, and the contrast is the point.

| | weak | strong |
|---|---|---|
| held fixed | per-rank data | **total data** |
| per-rank I/O as nodes grow | constant | **shrinks** |
| ideal aggregate bandwidth | grows 8× | grows 8× |
| what a shortfall means | Lustre cannot absorb more total data | per-rank I/O became too small to be efficient |

Weak scaling asks whether the filesystem can take more load. Strong scaling asks whether splitting a *fixed* job across more clients still helps — and it stops helping once each rank's writes become too small to amortise open/fsync/lock costs. That transition is the useful measurement.

## 3. Resources

```bash
-l select=${NODES}:ncpus=128:mpiprocs=128:mem=64gb
#PBS -l place=scatter:excl
```

**`place=scatter:excl` is what makes this inter-node.** Without `scatter`, PBS could pack chunks onto one host and an "8-node" job would quietly run on fewer. `ncpus` matches `mpiprocs` (project convention).

Striping pinned with `lfs setstripe -c 8 -S 1m` and verified with `lfs getstripe` in both variants.

## 4. Output

```
logs/<job>.out                                PBS job output
<variant>/<api>/<model>/ior_n<N>.txt          one file per node count
```

## 5. Running it

```bash
./submit_native_strong_job.sh       # 16 jobs
./submit_container_strong_job.sh    # 16 jobs
```

8 nodes × 128 = 1024 ncpus routes to `q5`.

## 6. Results

[`../../../results/inter_node/strong_scaling/README.md`](../../../results/inter_node/strong_scaling/README.md).
