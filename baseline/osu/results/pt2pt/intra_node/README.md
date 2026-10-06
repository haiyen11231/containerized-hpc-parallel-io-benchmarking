# Results — OSU pt2pt, intra-node

Two ranks on the same node, communicating through shared memory with no network involved. 10 repetitions per configuration, all 4 jobs `Exit_status=0`, 40/40 result files, no failures.

**The container penalty is small and bounded — 1.0–1.9×, versus 2–12× inter-node.** Above 32 KB the bandwidth comparison reverses sign, but the container's bandwidth there is too unstable to support a speedup claim; section 4 explains why the instability is the finding.

For how the experiment is set up and what each flag means, see [`../../../scripts/pt2pt/intra_node/README.md`](../../../scripts/pt2pt/intra_node/README.md).

---

## 1. Headline numbers

| message size | native latency | container latency | ratio |
|---|---|---|---|
| 1 B | 0.15 µs | 0.17 µs | 1.15× |
| 8 KB | 0.71 µs | 1.02 µs | **1.44×** (worst) |
| 256 KB | 15.42 µs | 12.76 µs | 0.83× |
| 4 MB | 197.31 µs | 227.61 µs | 1.15× |

| message size | native bandwidth | container bandwidth | container slower by |
|---|---|---|---|
| 64 B | 1248 MB/s | 672 MB/s | 1.86× |
| 256 B | 3385 MB/s | 1773 MB/s | **1.91×** (worst) |
| 2 KB | 16730 MB/s | 11287 MB/s | 1.48× |
| 4 MB | 21104 MB/s | 27373 MB/s | 0.77× (container higher) |

Sub-microsecond latency on both sides at small messages confirms both are genuinely using a shared-memory path — neither fell back to anything slower.

## 2. Small messages: the container is consistently slower, as predicted

Every bandwidth point from 1 B to 4 KB shows the container **1.38–1.91× slower**, all statistically resolvable, with low variance on both sides (native CV 1.5–10.9%, container 0.7–8.2%). This is the most solid result in the study.

It is the expected cost of the container's transport:

| | native | container |
|---|---|---|
| transport | UCX shared memory | vader (apt OpenMPI has no UCX) |
| single-copy | CMA, kernel-assisted | **disabled** — `btl_vader_single_copy_mechanism none` |

Apptainer's user namespace breaks OpenMPI's CMA path, so the container copies twice — sender into a shared buffer, receiver out of it — where native copies once. At small messages this per-message overhead dominates and the penalty shows cleanly.

The latency penalty peaks at **1.44× around 4–16 KB**: messages large enough that copying cost matters, too small to amortise it. Latency is 1.15–1.30× slower across essentially the whole small-message range, every point resolvable.

## 3. The 32 KB anomaly belongs to native, not the container

| size | native MB/s | native CV | container MB/s | container CV |
|---|---|---|---|---|
| 16 KB | 16483 | 35.8% | 17266 | 33.6% |
| **32 KB** | **9126** | 1.4% | 18887 | 41.7% |
| 64 KB | 14862 | 2.4% | 20335 | 39.8% |
| 4 MB | 21104 | 2.2% | 27373 | 19.2% |

Native drops to **55% of its 16 KB value at 32 KB**, then climbs back — with a *low* CV of 1.4%, so it is a stable, repeatable property of the native path rather than noise. The container shows no such dip; its curve rises monotonically through the region.

This is UCX switching from its eager protocol to rendezvous at the 32 KB threshold. Rendezvous exchanges control messages and then uses CMA (`process_vm_readv`) for a single kernel-assisted copy — more efficient for very large transfers, but carrying setup cost not yet amortised right at the crossover. The container never pays it because, with CMA disabled, it has one path and copies through shared memory throughout.

So the `0.483` slowdown factor at 32 KB — the largest apparent "container win" — is **native's protocol-switch artefact, not a container advantage**, and must be described that way.

## 4. Large messages: the finding is instability, not a container win

Above 32 KB the container's mean bandwidth exceeds native's at every size (0.73–0.86 slowdown factor, i.e. 16–37% higher). But look at the spread:

| size | native CV | container CV | resolvable at 95%? |
|---|---|---|---|
| 64 KB | 2.4% | **39.8%** | no |
| 128 KB | 2.5% | **39.9%** | no |
| 256 KB | 9.8% | **41.4%** | no |
| 512 KB | 3.1% | **35.5%** | no |
| 1 MB | 3.7% | 20.6% | yes |
| 4 MB | 2.2% | 19.2% | yes |

The container's coefficient of variation sits at **19–42%** against native's 2–10%. A Welch t-test cannot separate the 64 KB–512 KB points from native at all. Its bandwidth is swinging by a third to a half between otherwise identical repetitions on the same node — the signature of alternating between code paths rather than steadily outperforming.

**The defensible statement is:** above 32 KB the container's intra-node bandwidth is *unstable*, with a mean that happens to sit above native's but a spread far too wide to claim a speedup. The 1 MB and 4 MB points do clear significance, but on 19–20% variance against native's 2–4%, so even those should be reported as "higher mean, far less consistent" rather than as a clean win.

The stable, reportable findings are the small-message results in section 2 and the native protocol switch in section 3.

Resolving the mechanism would need `--report-bindings` plus a native comparison with `btl_vader_single_copy_mechanism cma` forced, to establish whether the swing is core placement or protocol selection. That is a Phase 2 profiling question, not a baseline one.

## 5. Why these numbers are trustworthy

**Allocation verified.** All 4 jobs: `ncpus=2`, `place=excl`, `walltime=00:30:00`, `Exit_status=0`, 40/40 result files, no `FATAL`/`FAILED` in any log. `ncpus` matches `mpiprocs`, the convention used by IOR and h5bench throughout this project.

**Exclusivity confirmed empirically, not assumed.** A probe job submitted as `ncpus=2:place=excl` reported `state = job-exclusive` with only its own job on the node. The small `ncpus` request does not weaken isolation — `place=excl` provides it, and `pbsnodes` shows one vnode per host on this cluster, so `place=excl` is equivalent to `place=exclhost` here.

**Rank placement is deterministic.** `--map-by core --bind-to core` pins ranks to cores 0 and 1 identically in both variants, so the comparison is not confounded by one variant landing on a different core complex.

**Node caveat.** Native latency, native bw and container bw all ran on `x1002c7s1b1n1`; container latency ran on `x1001c2s1b1n0`. Given the latency gap is only 1.0–1.4×, node-to-node variation matters more here than inter-node, where the gap was 2–12×. The bandwidth comparison is the cleaner of the two.

## 6. What this means for the project

Intra-node is the control for the inter-node experiment. Removing the network shows that **containerisation itself costs little** — 1.0–1.9× at worst, sub-microsecond latency preserved. The 2–12× penalty in [`../inter_node/README.md`](../inter_node/README.md) is therefore attributable to the network transport specifically, not to Apptainer's isolation, process launch, or library loading.

That is a sharper root-cause statement than either study could make alone, and it points Phase 3's optimisation effort at the MPI/UCX stack rather than at container configuration in general.
