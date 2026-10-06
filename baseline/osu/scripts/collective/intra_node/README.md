# OSU collective — intra-node

All **128 ranks on one node**, running `osu_allreduce` and `osu_alltoall`. Every rank shares memory with every other, so no network is involved — this measures the intra-node MPI transport at full node concurrency.

Compare with `../../pt2pt/intra_node/`, which uses the same shared-memory path but only **two** ranks.

---

## 1. Why collectives after pt2pt

pt2pt answers "how fast is one message between two ranks". That is the right first question, but no real application is two ranks exchanging one message. Applications call **collectives** — every rank participating in one coordinated operation — and a collective's cost is not simply the pt2pt latency times the number of ranks.

Two things only appear once more than two ranks take part:

- **Algorithmic structure.** MPI implements a collective as a tree, a ring, or a pairwise exchange. The number of steps and their shape determine the cost, and different MPI builds choose different algorithms.
- **Concurrency.** 128 ranks hitting shared memory at once contend for memory bandwidth and cache in a way two ranks never do.

That second point is the important one for this project, and it is why this case study exists.

## 2. The two kernels, and why this specific pair

They were chosen because their cost scales differently with rank count — one is latency-bound, the other bandwidth-bound. A gap that appears in one but not the other tells you *which* part of the transport is responsible.

### `osu_allreduce` — latency-dominated

Every rank contributes a buffer; every rank receives the combined result.

```
      rank 0  ─┐
      rank 1  ─┤
        …      ├──  reduce  ──→  result  ──→  broadcast back to all 128
      rank 127─┘
```

Traffic per rank is **O(message size)** — it does not grow with P. Cost is dominated by the **number of communication steps**, roughly `log2(128) = 7` rounds. Small messages therefore expose per-message overhead, which is exactly where a weaker transport hurts.

This is the single most important collective in HPC: it sits inside every iterative solver's convergence check, every dot product, and every synchronous gradient averaging step in distributed training.

### `osu_alltoall` — bandwidth-dominated

Every rank sends a **distinct** buffer to every other rank. This is the heaviest standard collective.

```
rank 0   sends a different chunk to each of 128 ranks
rank 1   sends a different chunk to each of 128 ranks
  …                     (128 x 128 distinct transfers)
rank 127 sends a different chunk to each of 128 ranks
```

Traffic per rank is **message size × P** — it grows linearly with rank count. At 128 ranks a 1 MB message means 128 MB out and 128 MB in *per rank*, roughly 32 GB moved across the node per iteration.

This is the pattern behind FFTs, matrix transposes, and particle redistribution — and it is the worst case for any transport.

### What the pair buys you

| | Allreduce | Alltoall |
|---|---|---|
| traffic per rank | O(msg) | O(msg × P) |
| bound by | per-message overhead | memory/copy bandwidth |
| a gap here means | the transport's fixed cost per message is higher | the transport's bulk copy path is slower |

If the container is slower on Alltoall but not Allreduce, the copy mechanism is the culprit. If it is slower on Allreduce at small sizes, the per-message overhead is. Running only one of the two would leave that ambiguous.

## 3. The expected result, and why this case study matters most for the container

The container's MPI differs from native in two ways here:

| | native | container |
|---|---|---|
| transport | **UCX shared memory** | **vader** (apt OpenMPI has no UCX) |
| single-copy | CMA — one copy, kernel-assisted | **disabled** — `btl_vader_single_copy_mechanism none` |

That second row is the one to watch. Apptainer's user namespace breaks OpenMPI's CMA path, so the container must fall back to a **two-copy** shared-memory transfer: sender copies into a shared buffer, receiver copies out, instead of the kernel moving it once directly.

In pt2pt that penalty is paid by two ranks. **Here it is paid by all 128 simultaneously**, and Alltoall makes every rank do it to every other rank. If the CMA fallback has a measurable cost anywhere in this project, this is where it will show.

That makes this case study the direct intra-node counterpart to the inter-node UCX-vs-TCP story — mechanism #1, measured where the container's handicap is structural rather than incidental.

## 4. Per-benchmark arguments

The two kernels cannot share one setting, because at the same message size Alltoall moves P times more data.

| | arguments | why |
|---|---|---|
| `allreduce` | `-f` | full default sweep; traffic does not grow with P, so it is cheap |
| `alltoall` | `-f -m 1:262144 -i 100` | capped at 256 KB and 100 iterations |

**Why Alltoall is capped:** at the 1 MB default and 128 ranks, a single iteration moves ~32 GB across the node. Left uncapped the job would not fit a 30-minute walltime, and the container — doing two copies instead of one — would be the one to time out, which would lose the very measurement the study is for. 256 KB is already far past the latency-to-bandwidth crossover, so the shape of the curve is preserved. `-i 100` fixes the iteration count so runtime is predictable rather than size-dependent.

The cap is **identical in both scripts**. If it were not, the two variants would be measuring different workloads.

**Why `-f`:** it prints MIN, MAX and ITERATIONS alongside the average. For a collective the spread between MIN and MAX across ranks is itself a result — it exposes load imbalance and stragglers that an average alone hides. This costs nothing and is worth having in the thesis.

## 5. Rank placement

```bash
-l select=1:ncpus=128:mpiprocs=128:mem=64gb   # all 128 ranks, one node
-l place=excl                                  # no other job on the hardware
--map-by core --bind-to core                   # ranks pinned to cores 0..127
```

Note `mpiprocs=128`, not `2` as in pt2pt — a collective needs every rank, so the full node is genuinely used rather than merely reserved.

Pinning matters more here than in pt2pt. These are dual-socket EPYC 7713 nodes, so collective cost depends heavily on how ranks map onto core complexes and NUMA domains. Without `--bind-to core` the OS could migrate ranks mid-run and the repetitions would not be comparable — nor would native be comparable to container.

## 6. Guards

| guard | catches |
|---|---|
| `: "${BENCH:?…}"`, `: "${REPS:?…}"` | job submitted without required variables |
| `case "$BENCH"` with a `*)` branch | a typo in the benchmark name, before any run starts |
| `test -x` on the binary (inside the `.sif` for the container) | wrong path or missing build |
| `ACTUAL_NODES -ne 1` | PBS spread the ranks over more than one node, which would make this an inter-node measurement |
| `grep -cE '^[0-9]'` on the output | a run that exits 0 but prints no data table |

## 7. Output

```
logs/osu_<variant>_collective_intra_<bench>.out   PBS job output
<variant>/<bench>/osu_<bench>_rep<N>.txt          one OSU table per repetition
<variant>/<bench>/nodes.txt                       the node used
```

Every path carries both the variant and the benchmark, so the four jobs write to disjoint trees and cannot overwrite one another. This directory is separate from `../../pt2pt/`, so the two studies cannot mix either.

`REPS=10`, matching pt2pt, h5bench and IOR.

**On a rerun:** `.txt` files and `logs/*.out` are overwritten. Wipe `native/`, `container/` and `logs/*.out` first, after copying anything worth keeping.

## 8. Running it

```bash
./submit_native_collective_intra_job.sh       # 2 jobs (allreduce, alltoall)
./submit_container_collective_intra_job.sh    # 2 jobs
REPS=1 ./submit_native_collective_intra_job.sh   # smoke test
```

### Choosing the queue

Walltime is **not** fixed in the `.pbs` files — it is passed by the submit script, because PBS routes on ncpus *and* walltime:

```bash
./submit_native_collective_intra_job.sh                  # 00:30:00 -> qdev
WALLTIME=02:30:00 ./submit_native_collective_intra_job.sh  # -> q4
```

| | qdev | q4 |
|---|---|---|
| walltime | ≤ 02:00:00 | > 02:00:01 |
| capacity | **256 ncpus cluster-wide, shared by all users** | far larger |

The default is `00:30:00` (qdev) since 30 minutes is ample for these runs, but note the trade-off: qdev's 256-ncpu cap is **cluster-wide**, so a 128-ncpu job takes half of it and at most two can run anywhere at once. If qdev's queue is long, `WALLTIME=02:30:00` routes to q4 instead. Check with `qstat -Q` before deciding.
