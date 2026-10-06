# Collective-I/O results

Fixed scale: 2 nodes, 256 ranks, 40 GiB per repetition. The 2×2 factorial sweeps HDF5's two collective switches. n=10 per cell.

Setup: `../../../scripts/inter_node/collective_io/README.md`

**This case study produced the only statistically distinguishable native/container difference in the entire h5bench campaign.**

---

## 1. Headline numbers

Write bandwidth, GiB/s, mean ± 95% CI.

| `COLLECTIVE_DATA` | `COLLECTIVE_METADATA` | Native | Container | Ratio | CIs |
|---|---|---|---|---|---|
| NO | NO | 1.516 ± 0.163 | 1.520 ± 0.162 | 1.00 | overlap |
| NO | YES | 1.550 ± 0.103 | 1.518 ± 0.126 | 0.98 | overlap |
| **YES** | **NO** | 1.672 ± 0.048 | **1.804 ± 0.056** | **1.08** | **DISTINCT** |
| **YES** | **YES** | 1.510 ± 0.114 | **1.823 ± 0.058** | **1.21** | **DISTINCT** |

"DISTINCT" means the 95% confidence intervals do not overlap — the difference is not attributable to noise.

## 2. The headline — read it as a difference of differences

The result is **not** "the container is 8–21% faster". It is that **enabling collective I/O helps the two variants by different amounts**:

| gain vs the (NO, NO) baseline | native | container |
|---|---|---|
| `COLLECTIVE_METADATA` alone | +2.2% | −0.1% |
| **`COLLECTIVE_DATA` alone** | **+10.3%** | **+18.7%** |
| both | −0.4% | **+20.0%** |

Collective data aggregation is worth roughly **twice as much to the container as to native**.

### Why that happens

`COLLECTIVE_DATA=YES` enables MPI two-phase I/O: ranks first exchange data among themselves so a few *aggregator* ranks end up holding large contiguous regions, then only those aggregators write. It trades **network communication** for **better disk access patterns**.

The price of that trade differs:

| | MPI transport | effect |
|---|---|---|
| Native | UCX + Slingshot | per-rank path is already fast, so aggregation adds communication for modest gain |
| Container | generic OpenMPI, TCP over `hsn0` | per-rank path is slower, so consolidating into fewer, larger writes pays off more |

The container is not beating native at I/O. It is **recovering more of its own deficit**, because the optimisation targets exactly the weakness it has.

### Why this matters for the thesis

Every other h5bench study found no measurable container penalty — intra-node, weak scaling and strong scaling all produced overlapping confidence intervals. That is a legitimate result but a negative one.

This study is where the container's MPI difference becomes **measurable**, and it converts into a concrete recommendation:

> **Enable `COLLECTIVE_DATA` for containerised HDF5 workloads.** It yields roughly double the benefit it gives a native run, and closes most of the gap created by the container's lack of UCX.

That feeds directly into the Phase 3 optimisation chapter.

## 3. Finding 2 — collective I/O is markedly more reproducible

Relative confidence interval (CI half-width ÷ mean):

| cell | native | container |
|---|---|---|
| data=NO, meta=NO | 10.8% | 10.6% |
| data=NO, meta=YES | 6.6% | 8.3% |
| **data=YES, meta=NO** | **2.8%** | **3.1%** |
| data=YES, meta=YES | 7.5% | **3.2%** |

With collective data enabled, run-to-run variability drops by roughly **3–4×**.

This is a second, independent benefit. Two-phase I/O funnels all writes through a small number of aggregators issuing large aligned requests, which smooths out the per-rank contention that makes independent I/O erratic. For a benchmark that is convenient; for a production workload, predictable completion time is often worth as much as mean throughput.

## 4. Finding 3 — collective *metadata* does almost nothing here

`COLLECTIVE_METADATA` alone changes bandwidth by +2.2% (native) and −0.1% (container) — both well inside the confidence intervals.

That is informative rather than disappointing. The switch consolidates HDF5 metadata operations through one rank instead of all 256 hitting the MDT. Its near-zero effect says **MDT contention is not a bottleneck at this scale and access pattern** — one shared file, 5 timesteps, contiguous layout generates few metadata operations relative to 40 GiB of data.

It would be expected to matter much more with file-per-process or many small datasets. The IOR strong-scaling results pointed at MDT contention under file-per-process; this result is consistent with that, since the shared-file pattern here avoids it.

**Running the full 2×2 is what makes this separable.** A single "collective on/off" switch would have conflated the large data effect with the negligible metadata one.

## 5. Validity checks

| check | result |
|---|---|
| Job exit status | 0 on all 8 |
| CSVs per cell | 10 write + 10 read, all 8 cells |
| `total size` | `40.000 GB`, single value across all 80 runs |
| Collective flags in generated configs | match the submitted cell in both write and read entries |
| Lustre striping | `stripe_count 4, 1 MiB`, verified |
| Path collisions | none — all four cells write to distinct `d<data>_m<meta>` trees |
| Local vs cluster | 160/160 CSVs, 8/8 logs |

The per-cell path scoping matters here: all four cells share `CASE=collective`, so without both flags in the directory name they would have overwritten each other. Verified that `payload/<variant>/dno_mno` … `dyes_myes` are eight distinct trees.

## 6. Reads — excluded

Same page-cache artifact as the scaling studies; in-job reads are not reported as read bandwidth.

Worth recording a correction here: an earlier analysis suggested the collective-read cells looked trustworthy because they had the **tightest confidence intervals in the dataset** (±0.4 on 4.3). Cold-cache measurement showed they were still ~4× inflated.

**A tight confidence interval means *consistent*, not *correct*.** Those reads were consistently cached.

## 7. Caveats

- **Single scale.** 2 nodes only, by design — this study isolates the switches, not scale. Whether the container's advantage grows or shrinks with node count is untested and would be a natural follow-up.
- **One access pattern** (`CONTIG`/`CONTIG`, shared file). The metadata result in §4 is specific to this; file-per-process would likely differ.
- **`btl_vader_single_copy_mechanism none`** is set for the container (Apptainer breaks CMA). That forces a double copy for intra-node transfers and is part of the container's measured behaviour, not a neutral workaround.
- **Absolute values are session-specific** (~15% between sessions). The difference-of-differences in §2 is a within-session ratio and unaffected.

## 8. Statistical power — this study is the well-powered one

Unlike the scaling studies, the key result here clears its detection floor
comfortably:

| cell | native CI | container CI | smallest resolvable | observed effect | |
|---|---|---|---|---|---|
| data=NO, meta=NO | ±10.8% | ±10.6% | ~21% | 0% | n/a |
| data=NO, meta=YES | ±6.6% | ±8.3% | ~17% | −2% | not resolvable |
| **data=YES, meta=NO** | **±2.8%** | **±3.1%** | **~6%** | **+8%** | **DETECTED** |
| **data=YES, meta=YES** | ±7.5% | **±3.2%** | ~11% | **+21%** | **DETECTED** |

The two cells carrying the finding are exactly the two with the tightest confidence intervals — because collective I/O *itself* reduces variance (§3).
The effect is larger than the floor in both, so this is a positive result, not an artefact of low power.

Contrast with weak and strong scaling, where intervals of ±12–32% mean only large effects would have been visible. **This is the one h5bench study whose conclusion rests on a detected difference rather than an undetected one.**

## 9. What this hands to the next phases

| observation | Phase 2 question | Phase 3 action |
|---|---|---|
| Container gains ~2× more from collective data than native (§2) | Profile the two-phase exchange — is the container's gain from fewer/larger writes, or from avoiding its slower per-rank path? Recorder traces the call sequence | Already an optimisation result: **enable `COLLECTIVE_DATA` for containerised HDF5**. Phase 3 should re-test it against the bind-mounted host MPI — if bind-mounting removes the transport deficit, the container's advantage should shrink |
| Collective metadata does nothing at this scale (§4) | Does it matter under file-per-process, where IOR saw MDT contention? | Only worth tuning if profiling shows MDT pressure |
| Collective I/O cuts variance 3–4× (§3) | Confirm with Darshan that aggregation reduces the number of distinct OST requests | Report as a secondary benefit: predictable completion time |

**Single scale (2 nodes) is deliberate** — this study isolates the switches, not scale. Whether the container's advantage grows or shrinks with node count is a natural Phase 2/3 follow-up, and is the more interesting question now that the effect is established.
