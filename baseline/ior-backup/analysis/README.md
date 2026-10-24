# IOR analysis — figures and what they show

Parsing, statistics and figures for the IOR baseline. Numbering and style mirror `../../osu/analysis/` so the two benchmarks read the same way in the report.

```
common.py     shared parsing + 95% CI helpers
plot_ior.py   generates all 5 figures
figures/      fig1a, fig1b, fig2a, fig2b, figA1
GUIDE.md      the plotting plan, checked against the data in section 3
```

```bash
../../../.venv/bin/python plot_ior.py
```

**One idea per figure**, with mean + **95% confidence intervals** (Student's t, n=10 from IOR's own `-i 10`) and value labels on the data points. Native and container appear **together in every comparison figure** — same panel for line plots, side-by-side bars for Figure 1C — so the comparison is always direct rather than split across charts. The one exception is `figA1`, which is about IOR's own measurement behavior rather than about containers; see section 4.

| slot | OSU | IOR |
|---|---|---|
| 1a | pt2pt latency | transfer sweep, stripe 1 |
| 1b | pt2pt bandwidth | transfer sweep, stripe 8 |
| 1c | pt2pt overhead | access model |
| 2a | allreduce scaling | weak scaling |
| 2b | alltoall scaling | strong scaling |
| A1 | NP=64 anomaly | read cache inflation |

---

## 1. How the data becomes a plot

**IOR's "10 runs" live inside one file.** This differs from OSU and h5bench, and it is the first thing to understand before reading any figure.

`-i 10` tells IOR to repeat the measurement 10 times *within a single invocation*, so one job produces one `.txt` file containing all ten, followed by IOR's own summary:

```
write  bw=1474   iter=0
write  bw=1295   iter=1
   ...                       <- 10 iteration rows
write  bw=1514   iter=9

Summary of all tests:
write   Max=1623.46  Min=1295.29  Mean=1437.61  StdDev=106.66
```

(OSU and h5bench instead submit the job 10 times and produce 10 separate files. Same sample size, different mechanism — which is why the parsers differ.)

**`plot_ior.py` reads the Summary row**, taking `Mean(MiB)` and `StdDev`. Verified against the raw rows for this file: computing the mean of the ten values by hand gives **1437.61**, identical to IOR's. The standard deviations also match once you account for IOR using the *population* form (÷n) rather than the sample form (÷n−1).

**Each plotted point is then:**

```
dot        = Mean                       = 1438 MiB/s
error bar  = 2.262 x StdDev / sqrt(10)  = +-76 MiB/s
             +- Student's t, 95%, df = 9
```

So every dot is an average of 10 iterations and every error bar is the 95% confidence interval on that average. **The error bars are not decoration** — with a null headline result they *are* the finding, and reading any figure without them will mislead.

## 2. Intra-node

### `fig1a_transfer_sweep_stripe1.png` and `fig1b_transfer_sweep_stripe8.png`

Bandwidth vs transfer size, **one figure per stripe count**, each a single row of 4 panels (the API × access-model combinations). Every panel holds exactly **two lines — native and container**.

*(Earlier versions put all four series in one panel, then both stripes in a 2×4 grid. Splitting into two figures gives each panel room for its value labels and error bars, and makes the shaded band unambiguous because only one stripe count is present.)*

**The shaded band is that panel's native 95% CI.** Where the container line sits inside it, the two are indistinguishable for that configuration — **14 of 20** stripe-8 points do.

> The band is a visual aid, **not a significance test**. A point just outside it is not automatically significant: the correct test compares the *difference* against its own combined interval, which is what the 14-of-72 count in §5.1 uses. Band = "same neighborhood"; Welch test = resolvability.

**Comparing 1A against 1B gives the stripe effect directly** — which is where §5.2's finding lives: at 16 MiB, shared-file gains from stripe 8 (1.24×) while FPP loses (0.63–0.66×).

**The dotted line at 1 MiB** marks the Lustre stripe size (`-S 1m`). `GUIDE.md` suggests it explains where throughput "changes trajectory". Checked against the data, it does not — slopes either side are 1.06× → 1.05× (POSIX/Shared) and 0.85× → 0.96× (MPIIO/Shared, within noise). It is drawn as a neutral physical reference and **should not be captioned as a cause**; anyone checking the slopes will find the claim unsupported.

### `fig1c_access_model.png` — the effect that actually dominates

Grouped bars, native and container side by side, averaged over both stripe counts and all five transfer sizes (10 measurements per bar).

| | native | container |
|---|---|---|
| POSIX / Shared | 1287 | 1271 |
| MPIIO / Shared | 1257 | 1231 |
| POSIX / FPP | **4902** | **4417** |
| MPIIO / FPP | **3947** | **3710** |
| **FPP ÷ Shared** | **3.5×** | **3.2×** |

**Both variants are plotted, and that is the point.** The access-model gap is 3.5× native and 3.2× in the container — near-identical. If containerization affected how the access model behaves, those ratios would diverge. They do not, so the effect belongs to Lustre, not to the container.

*(An earlier version of this figure plotted native only, reasoning that the access model is a filesystem property. That was a mistake: showing both is what demonstrates the claim rather than asserting it.)*

**Why FPP wins.** With one shared file all 64 ranks serialize on Lustre's distributed lock manager for overlapping extents; with file-per-process each rank owns its file outright and the locking disappears.

**The figure also carries the null result.** The shared-file pairs differ by ~2%, well inside their error bars. The FPP pairs differ by ~10%, but their confidence intervals span **±1400 MiB/s** — so even that gap is unresolvable. One figure therefore shows both the dominant effect and the absent one.

**Read the error bars as data.** Shared-file bars are tight; FPP bars are enormous — same measurement, same repetitions. The difference is Lustre metadata-server variability under 64 ranks each creating their own file, which §5.4 quantifies at CV 40.5% vs 17.6%.

**This is IOR's real contribution to the thesis** — and it is about mechanism #3 (filesystem interaction), not about containers.

## 3. Inter-node scaling

### `fig2a_weak_scaling.png` — can Lustre absorb more load?

2×2 panels, one per configuration, native and container together, with a dashed **ideal linear** reference anchored at each series' own 1-node value.

Per-rank work is fixed, so 8 nodes should deliver 8× the bandwidth of 1. The gap from the dashed line is where Lustre stops scaling:

| | 8-node efficiency |
|---|---|
| POSIX / Shared | **95%** of ideal |
| MPIIO / Shared | 69% |
| MPIIO / FPP | 68% |
| POSIX / FPP | **58%** |

**The counter-intuitive result: shared-file scales best, file-per-process scales worst** — despite FPP being ~6.9× faster in absolute terms at one node. They are limited by different things. Shared-file pays its lock-contention cost at n=1 and that cost barely grows, so adding nodes adds bandwidth almost linearly. FPP skips the locking but at 1024 ranks is creating and fsyncing 1024 separate files, and **MDT load grows with rank count**. FPP runs out of metadata headroom before it runs out of OST bandwidth.

### `fig2b_strong_scaling.png` — does splitting fixed work still help?

Same layout, but **parallel efficiency** rather than raw bandwidth. Total is fixed at 64 GiB, so ideal means bandwidth grows linearly and efficiency = `BW(n) / (BW(1) × n)`.

```
native POSIX / Shared : 100 → 93 → 78 → 74%    degrades gracefully
native MPIIO / Shared : 100 → 80 → 55 → 28%    collapses
```

Efficiency is the right axis here: on a bandwidth plot both curves merely rise and that contrast is invisible. As the total splits across more ranks each one's contribution shrinks, and MPI-IO's collective buffering stops being able to assemble usefully-sized writes. POSIX, with no aggregation layer, degrades more gracefully.

**One thing not to misread.** Each efficiency curve is relative to *its own* 1-node value. Where the container sits above native (MPIIO/Shared, 45% vs 28% at 8 nodes) that is **not** a container advantage — native's 8-node MPIIO/Shared point is the unstable one (CV 29%), which depresses its ratio. The caveat is printed on the figure.

## 4. Appendix

### `figA1_read_cache_inflation.png` — why read bandwidth is never reported

```
same file, same run:   write 1188 MiB/s     read 32678 MiB/s     →  27×
```

IOR reads back data it has just written, so reads are served from the client page cache rather than Lustre. `-C` reorders tasks so a rank does not read its *own* block, but on a single node every block is still in that node's cache.

**Native only, deliberately.** This figure documents a property of *IOR's methodology*, not a native-vs-container comparison — the cache inflation affects both variants identically, so plotting both would double the bars without adding information.

**Report write bandwidth only.** A 27× read "advantage" is a measurement artifact — the same trap the h5bench cold-read study was built to address.

---

## 5. Critical reading — four anomalies worth understanding

These are the things a careful reader will notice. Each is real, and each has an explanation the data supports.

### 5.1 The container effect is a coin flip, not a penalty

Across all **72 comparisons**:

| | count | of which resolve at 95% |
|---|---|---|
| container slower | 44 | 9 |
| container faster | 28 | 5 |
| **median ratio** | **1.051** | |

A genuine effect would be lopsided in *one* direction. Instead the split is near even, and critically **the resolving cases appear in both directions** — 9 "significantly slower" and 5 "significantly faster". Both cannot be true of the same system.

That is the signature of noise crossing a significance threshold by chance, not of a container penalty. With 72 comparisons at 95%, roughly 4 false positives are expected from chance alone; 14 with mixed signs is consistent with a slightly heavy-tailed noise distribution, not with an effect.

**How to state it:** *"no container penalty is demonstrated; the experiment bounds any effect at roughly 20–30%."* Not *"the container is 5% slower."*

### 5.2 The stripe effect flips direction by access model — and only at 16 MiB

Ratio of stripe 8 to stripe 1, native, write (`*` = resolves at 95%):

| | 64k | 256k | 1m | 4m | 16m |
|---|---|---|---|---|---|
| POSIX / Shared | 0.97 | 1.06 | 1.00 | 1.10 | **1.24\*** |
| POSIX / FPP | 1.03 | 0.90 | 0.97 | 0.73 | **0.63\*** |
| MPIIO / Shared | 0.86 | 1.03 | 0.90 | 0.89 | 0.98 |
| MPIIO / FPP | 0.71 | 0.92 | 0.79 | 1.00 | **0.66\*** |

**All three resolving cases are at 16 MiB, and the direction depends on the access model.**

- **Shared file at 16m: striping over 8 OSTs helps (1.24×).** One file, many ranks — spreading it across more OSTs gives more parallel writers and relieves per-OST contention.
- **FPP at 16m: striping over 8 OSTs hurts (0.63–0.66×).** Each rank already owns its own file, so there is nothing to parallelise. Striping each small file across 8 OSTs just fragments a sequential write into 8 scattered ones, adding seeks and OST round-trips for no benefit.

This is a coherent mechanism, but rests on **3 of 20** comparisons. State it as *"consistent with, and worth testing"* rather than as established — the honest framing in `fig1a`, where the stripe curves share a color.

### 5.3 MPI-IO is usually *slower* than POSIX, and most so where it should help

Ratio MPI-IO ÷ POSIX, native, write (<1 means MPI-IO is slower):

| | 64k | 256k | 1m | 4m | 16m |
|---|---|---|---|---|---|
| shared, stripe 1 | 1.18 | 1.11 | 0.96 | 0.97 | 1.01 |
| shared, stripe 8 | 1.04 | 1.08 | 0.86 | **0.79** | **0.80** |
| fpp, stripe 1 | 0.87 | **0.72** | 0.99 | **0.75** | 0.83 |
| fpp, stripe 8 | **0.59** | 0.73 | 0.81 | 1.03 | 0.86 |

MPI-IO exists to aggregate scattered writes into large contiguous ones. It should be at its best on a shared file with large transfers — yet that is exactly where it loses most (0.79–0.80× at 4m/16m, stripe 8).

The likeliest reading: at 4–16 MiB transfers each rank is *already* issuing well-formed, stripe-aligned writes, so there is nothing for two-phase aggregation to improve — and its coordination overhead becomes pure cost. This is the same story as the strong-scaling collapse in §3, seen at a single node.

**This is a profiling question, not a settled one.** `MPIIO_COLL_WRITES` vs `MPIIO_INDEP_WRITES` would show whether collective aggregation is even engaging — see `../../../profiling/ior/GUIDE.md`.

### 5.4 FPP is more than twice as noisy as shared-file

| | median CV | max CV |
|---|---|---|
| shared file | 17.6% | 26.8% |
| **file-per-process** | **40.5%** | **68.5%** |

The variance is itself a measurement. 64 ranks each creating, writing and `fsync`-ing their own file hammer the Lustre **metadata servers**, and MDT response time depends on whatever else the cluster is doing. A shared file touches the MDT essentially once.

Two consequences:

1. **It explains §3's scaling paradox.** FPP is ~3.5× faster in absolute terms but reaches only 58% of ideal at 8 nodes versus shared-file's 95% — because FPP is limited by metadata capacity, which grows with rank count, rather than by OST bandwidth.
2. **It is why so few FPP comparisons resolve.** A 40% CV cannot detect a 10% effect at n=10. Any FPP cell showing a dramatic container difference should be read against its confidence interval first.

## 6. What was dropped, and why

**A container-overhead heatmap.** It spanned −44% to +29% in red/green with no significance encoding, across 32 cells. Only **11 resolve at 95%**, in mixed directions, and six of its most dramatic cells have confidence intervals *wider* than the effect shown:

```
strong N=8 mpiio/fpp : +12.3%  but CI ±46%
strong N=4 mpiio/fpp : -28.6%  but CI ±34%
strong N=4 posix/fpp : -14.9%  but CI ±36%
```

A reader would conclude containers matter a great deal for I/O. They do not — that is run-to-run Lustre variance rendered as color. The native-vs-container comparison now lives inside Figures 1A, 2A and 2B, where **overlapping confidence intervals state the null result directly** instead of dressing it up.

Four earlier figures were also removed as redundant once both variants shared a panel (`1node_overhead_heatmap_t4m`, `1node_stripe_bar_t4m`, the separate read/write transfer sweeps, and `multinode_strong_scaling_bandwidth`).

## 7. GUIDE.md checked against the data

| GUIDE asks for | status |
|---|---|
| 1A bandwidth vs transfer size, stripe 1 vs 8 | ✅ `fig1a` — stripe shown, with the 3/20 caveat |
| 1B shared vs FPP ~3.5× bar chart | ✅ `fig1b` — measured 3.5× |
| 2A weak scaling bandwidth vs node count | ✅ `fig2a` |
| **2B strong scaling efficiency %** | ✅ `fig2b` — **the GUIDE was right**, I had plotted bandwidth first |

Two deviations:

**Log y-axis, not log-linear** (GUIDE Fig 1A specifies linear). Native inter-node bandwidth spans 3.7 → 12,249 MiB/s, a **3284× range**; a linear axis compresses everything below 1 GiB/s onto the baseline.

**Stripe count is de-emphasized.** The GUIDE treats it as a comparison dimension; the data makes it a non-finding (3/20 resolving, mixed directions), so it is drawn but not colored as a contrast.

## 8. Two things the parsing must get right

**Read IOR's summary block, not the per-iteration rows.** Each result file contains 10 iterations followed by `Summary of all tests` carrying `Mean(MiB)` and `StdDev`. `parse()` takes the summary — averaging the per-iteration rows by hand would give the same mean but lose the standard deviation, which is the column that matters most when the headline is a null result.

**Error bars are not decoration here.** Run-to-run variation on shared Lustre is **CV 14–25%, up to 69% for FPP** — larger than any container effect present. Across all 72 comparisons the median is 1.01–1.07×. A bar chart of bare means would imply differences the data cannot support, which is exactly how the dropped heatmap went wrong.

## 9. What the figures say together

**IOR shows no measurable container penalty**, and bounds it at roughly 20–30% — the limit of what this experiment can resolve against Lustre's own variance. That is a bounded negative result, not proof of zero, and it is corroborated independently by h5bench.

What IOR *does* resolve is about the filesystem, not the container:

- **access model dominates** — FPP ~3.5× faster than shared-file
- **but shared-file scales better** — 95% of ideal at 8 nodes vs FPP's 58%, because FPP hits Lustre *metadata* limits rather than bandwidth limits
- **MPI-IO shared-file stops scaling past 4 nodes** under strong scaling while POSIX keeps climbing

Set beside OSU — where the container was up to 12× slower and Alltoall failed outright — the combined claim is: **containerization's cost is concentrated in the MPI transport, and bulk parallel I/O is not transport-bound enough to expose it.**
