# OSU collectives — intra-node scaling

Allreduce and Alltoall across **8 → 128 ranks, all on one node**. Every message goes through shared memory; no network is involved. Two scaling studies in parallel subdirectories:

```
weak_scaling/     message size per peer fixed at 64 KiB
strong_scaling/   total problem fixed at 8 MiB, split across ranks
```

40 jobs per study-pair (2 modes × 2 variants × 2 benchmarks × 5 rank counts), 10 repetitions each.

---

## 1. Why rank count is the scaling variable here

pt2pt is always two ranks, so its only axis is message size. A **collective's cost is intrinsically a function of P** — Allreduce needs `O(log P)` communication rounds, Alltoall moves `O(P)` traffic per rank — so you cannot characterize one without varying the rank count.

That is why this study differs in shape from h5bench's and IOR's intra-node studies, which fix concurrency and sweep an I/O configuration instead. For those, rank count is not the interesting variable; here it is the only one that matters.

## 2. The two kernels

| | Allreduce | Alltoall |
|---|---|---|
| pattern | all ranks contribute, all receive the result | every rank sends **distinct** data to every peer |
| traffic per rank | `O(S)` — flat in P | `S × P` — grows with P |
| bound by | per-message overhead, `log P` rounds | copy bandwidth and message count |
| a gap here means | the transport's fixed per-message cost is higher | the transport's bulk copy path is slower |

Running both is what makes the result diagnostic rather than descriptive: the container turns out to be *faster* on one and much slower on the other, which localizes its handicap to message **count** rather than bytes moved.

## 3. Weak vs strong — and a warning about Alltoall

| | weak | strong |
|---|---|---|
| held fixed | 64 KiB per peer | 8 MiB total |
| per-rank message | constant | shrinks 1024 → 64 KiB |

**For Allreduce these labels mean what you expect.** Per-rank traffic is `O(S)`, so fixed-S really is constant work per rank (weak), and `T/P` really does shrink it (strong).

**For Alltoall they are effectively inverted, and this must be stated when reporting.** Per-rank traffic is `S × P`, so:

| at NP | weak per-rank | strong per-rank |
|---|---|---|
| 8 | 0.5 MiB | 8 MiB |
| 128 | **8 MiB** | **8 MiB** |

Under *weak* scaling Alltoall's per-rank work **grows 16×** across the sweep — it is "fixed message size per peer", not "fixed work". Under *strong* scaling it is pinned at exactly 8 MiB, so a perfectly scaling implementation would be **flat**, and any rise is pure coordination overhead. That makes strong-scaling Alltoall the sharper of the two experiments.

## 4. A built-in consistency check

At NP=128 the strong-scaling message size works out to `8 MiB / 128 = 65536` bytes — **identical to the weak-scaling size**. The two independent sets of 20 jobs must therefore agree at that point, and they do, to within 0.3%. That is a free validation that both studies are measuring the same thing.

## 5. Configuration

```bash
-l select=1:ncpus=${NP}:mpiprocs=${NP}:mem=16gb
#PBS -l place=excl
#PBS -l walltime=00:30:00
BENCH_ARGS=(-f -i 100 -m "${MSG}:${MSG}")
```

| choice | why |
|---|---|
| `ncpus` = `mpiprocs` = NP | project convention — declare the cores you launch on. `place=excl` provides isolation; inflating `ncpus` would only make small-NP jobs harder to schedule (measured: 16 s to start at `ncpus=2`, >25 min at 128) |
| `-m MSG:MSG` | pins **one** message size, so each job emits a single data row — the x-axis is rank count, not message size |
| `-i 100` | fixed iteration count so weak and strong remain comparable; matches OSU's own default at these sizes |
| `-f` | adds MIN/MAX/ITERATIONS. For a collective the **spread across ranks is a load-imbalance measurement**, which an average alone hides |
| `mem=16gb` | worst case is Alltoall at NP=128 weak, ~2 GiB/node |

## 6. Topology the curve crosses

These are dual-socket EPYC 7713 nodes — 8 cores per CCD (shared L3), 64 per socket:

| NP | cores | topology |
|---|---|---|
| 8 | 0–7 | 1 CCD, one shared L3 |
| 16–64 | 0–63 | multiple CCDs, socket 0 only |
| **128** | 0–127 | **both sockets** — inter-socket traffic appears |

So "scaling" here conflates rank count with memory hierarchy. That is unavoidable physics, and both variants cross the same boundaries, so the native/container *ratio* stays clean even where the absolute curve kinks. Each job writes `bindings.txt` (via a `--report-bindings` run outside the timed loop) so this is **provable from the results rather than assumed**.

## 7. Guards

| guard | catches |
|---|---|
| `BENCH`/`NP`/`REPS` unset | job submitted without required variables |
| `case "$BENCH"` with `*)` branch | typo'd benchmark name, before any run starts |
| `test -x` on the binary (inside the `.sif` for the container) | wrong path or missing build |
| `ACTUAL_NODES -ne 1` | PBS spread ranks over more than one node — would make this inter-node |
| **`SLOTS -ne NP`** | `PBS_NODEFILE` has a different rank count than the job's label — would silently corrupt the scaling curve |
| `TOTAL % NP` (strong only) | 8 MiB not divisible by NP, so per-rank size would truncate |
| `rows -lt 1` | run exited 0 but produced no data table |

## 8. Output

```
<mode>_scaling/logs/<job>.out                          PBS output
<mode>_scaling/<variant>/<bench>/np<N>/osu_<bench>_rep<R>.txt
<mode>_scaling/<variant>/<bench>/np<N>/nodes.txt        node used
<mode>_scaling/<variant>/<bench>/np<N>/bindings.txt     rank -> core placement
<mode>_scaling/<variant>/<bench>/np<N>/msgsize_bytes.txt
```

Every path carries mode, variant, benchmark and rank count, so all 40 jobs write to disjoint trees.

## 9. Running it

```bash
cd weak_scaling   && ./submit_native_collective_weak_job.sh   && ./submit_container_collective_weak_job.sh
cd strong_scaling && ./submit_native_collective_strong_job.sh && ./submit_container_collective_strong_job.sh
```

Small-NP jobs schedule almost immediately; the four NP=128 jobs are the slow ones. The whole 40-job set completed in roughly 10–20 minutes when the queue was healthy.

## 10. Results

[`../../../results/collective/intra_node/README.md`](../../../results/collective/intra_node/README.md) — including why the container is ~20% *faster* on Allreduce, 1.7–4.9× slower on Alltoall, and why the NP=64 Allreduce spike is OpenMPI's doing rather than the container's.
