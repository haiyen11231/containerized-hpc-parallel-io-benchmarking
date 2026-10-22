# OSU analysis — figures and what they show

Parsing, statistics and figures for the OSU baseline. Mirrors `../../h5bench/analysis/` and `../../ior/analysis/` so all three benchmarks look consistent in the report.

```
common.py     shared parsing, statistics, style
plot_osu.py   generates all 10 figures
figures/      fig1a, fig1b, fig2a .. fig2e, fig3, fig4, plus figA1
GUIDE.md      the plotting/analysis plan, checked against the data in section 3
```

```bash
../../../.venv/bin/python plot_osu.py
```

**One idea per figure.** An earlier pass merged these into four dense multi-panel figures; that made each harder to read and to caption, and one of them put pt2pt latency and collective latency on the same bar axis — workloads that are not comparable. For a report, a figure answering one question beats a figure answering three.

All line plots show **mean with 95% confidence intervals** (Student's t, n=10) and **value labels on the data points**. Endpoints are always labeled because they are the two values the Hockney fit is read from: the first point is α, the last is the bandwidth-dominated regime.

---

## 1. Point-to-point

### `fig1a_pt2pt_latency.png` — latency vs message size

Two panels, intra- and inter-node, log-log.

| | 1 B | 4 MiB |
|---|---|---|
| intra-node | 0.152 → 0.174 µs | 197 → 228 µs |
| inter-node | **1.46 → 17.1 µs** | **350 → 1663 µs** |

The container's inter-node curve runs **flat at 13.2–14.0 µs from 4 B to 1 KiB**. That plateau is α dominance made visible: message size barely affects cost until the fixed per-message overhead is amortised. Native starts at 1.46 µs and rises smoothly.

### `fig1b_pt2pt_bandwidth.png` — bandwidth vs message size

Same layout. Native inter-node saturates at ~12.2 GB/s; the container plateaus near 5.1 GB/s, about 41% of it.

**Log y-axis, not linear.** `GUIDE.md` specifies log-linear, but native inter-node bandwidth spans 3.7 → 12,249 MB/s — a **3284× range** that a linear axis would compress entirely onto the baseline.

## 2. Collective scaling

Intra-node and inter-node are **separate figures**, not panels sharing one x-axis. An earlier version spanned 8 → 1024 ranks on a single log axis with a "network starts" divider marking where the regime changes; that compressed the 5-point intra-node curve and the 3-point inter-node curve together and made both harder to read. Splitting removes the divider entirely — each figure's x-axis only ever means one thing, at the cost of needing four figures instead of two.

### `fig2a_allreduce_intra.png` — Allreduce, 8 → 128 ranks, one node

**The sign flip is legible straight from the labels.** Weak scaling: at 128 ranks native is 272 µs and the container 214 — the container is *faster*. Same benchmark, same message size, same node; see `fig2b` for what happens once the network is involved.

The NP=64 spike (500 µs native, 458 µs container, ~3–4× their neighbors) is visible in both variants — see `figA1`.

### `fig2b_allreduce_inter.png` — Allreduce, 2/4/8 nodes

At 2 nodes (256 ranks) native drops to 134 µs while the container climbs to 471 — the sign flip from `fig2a` has fully reversed. The container keeps costing roughly 3–6× native from here on; see `fig4` for the Hockney decomposition of why.

### `fig2c_alltoall_intra.png` — Alltoall, 8 → 128 ranks, one node

The container tracks native with a 1.5–3.3× penalty throughout — no failures at this scale, since Alltoall only becomes a port-exhaustion problem once the network is involved (`fig2d`).

### `fig2d_alltoall_inter.png` — Alltoall, with the failure

Native keeps running cleanly through all three node counts. The container tracks native with a similar penalty at 2 nodes (256 ranks), then **fails outright at 4 and 8 nodes (512/1024 ranks)**, marked with an X rather than omitted.

Those cells contain **0 data rows** — pure error output. They are excluded from every statistic and drawn explicitly as failures, because "the container cannot run this configuration" is the most consequential OSU result and a figure that silently dropped the points would erase it.

### `fig2e_internode_growth.png` — how cost grows as nodes are added

`fig2b`/`fig2d` show inter-node cost in absolute µs; this isolates **relative growth**: **node count on x, cost relative to the 2-node point on y, so the slope is the scaling penalty.**

The dashed line is what workload growth alone predicts — flat where per-rank work is constant, linear in P for weak Alltoall. **Distance above it is contention, not workload.**

| at 8 nodes | growth vs 2 nodes | |
|---|---|---|
| allreduce weak, native | **1.23×** | near-flat, close to ideal |
| allreduce weak, container | **2.14×** | degrades ~3× faster than native |
| alltoall weak, native | **10.0×** | against 4× predicted — 2.5× is pure contention |
| alltoall strong, native | 2.10× | should be flat; the rise is coordination overhead |

**The top-left panel is the clearest result.** Under weak-scaling Allreduce per-rank data is constant, so ideal is flat. Native holds 1.23× while the container climbs to 2.14× — **adding nodes costs the container roughly three times what it costs native**, which is what more TCP traffic and no RDMA predicts.

**The top-right panel shows the Alltoall ceiling as a scaling story** rather than a bare failure: native rises steadily to 10× while the container simply has no points beyond 2 nodes.

> **One oddity to flag if you use the bottom-left panel.** Native Allreduce strong goes 1.00 → 0.96 → 3.64× while the container goes 1.00 → 1.88 → 1.06×, and the two cross. Both are non-monotonic for the same reason as `figA1` — OpenMPI's tuned-collective selection picks different algorithms at different rank counts, and both variants inherit it. The crossing is not meaningful.

## 3. Diagnostic

### `fig3_port_exhaustion.png` — why Alltoall fails

Three arms from one job on the same four nodes within 51 seconds, plotted against the measured 28,232-port ephemeral limit:

| arm | connections/node | | |
|---|---|---|---|
| container, 128 ranks/node (512 total) | 65,408 (2.32×) | **FAIL** | 512 port errors |
| container, **64** ranks/node (256 total) | 16,320 (0.58×) | **PASS** | |
| native, 128 ranks/node (512 total) | 0 — RDMA | **PASS** | |

Arm 2 changes only the connection count. Arm 3 runs the *same 512 ranks* without TCP. Together they exclude "the scale is too large" and "those nodes were unhealthy", leaving the transport as the only explanation.

### `fig4_hockney_decomposition.png` — which cost component

Fitting `T(S) = α + S/B` splits the penalty into per-message overhead and bandwidth:

| | α penalty | B penalty |
|---|---|---|
| intra-node | 1.26× | 1.15× |
| **inter-node** | **9.25×** | 4.74× |

Inter-node α goes from 1.46 to 13.47 µs — **12.0 µs added to every message, whatever its size**. Intra-node both components are ~1.2×, so no single culprit.

This is the figure that drives Phase 2: the 12 µs is a falsifiable prediction, and it should appear as kernel time in TCP syscalls rather than user-space copying.

`GUIDE.md` placed this in a table; it is promoted to a figure because it is the most diagnostic single result in the OSU work.

## 4. Appendix

### `figA1_np64_anomaly.png` — native's own non-monotonicity

Native Allreduce at NP=64 costs 500 µs against 84 µs at NP=32 (5.95×) and 272 µs at NP=128 (1.84×), CV 0.25%, reproduced again in this rerun on top of the earlier confirmations, in **both** variants.

`bindings.txt` rules out socket saturation: NP=64 places 64 ranks on socket 0 while NP=128 places 64 on *each*, so per-socket load is identical — saturation would predict equal cost, not a multi-fold spike. OpenMPI's tuned-collective algorithm selection remains.

Both variants inherit it, so the comparison stays valid. Included so the native scaling curve is not presented as smoother than it is.

---

## 5. GUIDE.md checked against the data

Its **analytical** claims all hold exactly:

| claim | measured | |
|---|---|---|
| ~12 µs fixed overhead inter-node | **12.0 µs** (1.46 → 13.47) | ✅ |
| ~20% faster Allreduce intra-node | **0.80×** over 5 rank counts | ✅ |
| 3.5×–6× Allreduce slowdown inter-node | **3.52 / 5.71 / 6.11×** | ✅ |
| Alltoall fails from the ephemeral port limit | 65,408 vs 28,232, proven | ✅ |
| do not use Darshan for OSU | confirmed — Darshan wraps only `MPI_File_*` | ✅ |

Three recommendations were **not** adopted, each for a measured reason:

**"Drop Run 1 as warm-up" — rejected as a blanket rule.** Tested over 8 cases: only one has rep1 as a genuine outlier (inter container 1 B, z=3.63); the rest are z≤2.3. That one case is *informative* — rep1 reads 30.36 µs against a 15.63 µs steady state, which is **TCP connection-establishment cost**, evidence for the α hypothesis rather than noise. Dropping it would delete a finding and discard 10% of the data elsewhere for nothing.

**"Bandwidth on a log-linear axis" — rejected.** 3284× range; see `fig1b`.

**"Report median where CV>15%" — adopted selectively.** Only **26 of 184** points exceed CV 15%, clustered entirely in bandwidth and in the container. `cv()` is reported alongside every mean so the reader can see which is which.

**On the Hockney fit.** `GUIDE.md` prescribes OLS over S≤8192. Both methods agree α dominates inter-node (OLS 7.87×, flat-region 9.25×) but differ on B (1.93× vs 4.74×), because OLS over small messages fits *pre-asymptotic* bandwidth — its R² for the container is only **0.699**, since that curve is flat then rises and a line fits it poorly. The figures take α from the flat small-message region and B from the asymptotic end; `alpha_B()` documents why.

## 6. Three things the code has to get right

**The "better" direction flips between kernels.** `osu_latency` is µs (lower better), `osu_bw` is MB/s (higher better). `ratio()` always returns a **slowdown factor**, inverting bandwidth internally, so **>1 always means the container is worse** in every figure.

**Failed cells stay failed.** See `fig2d` — never dropped, never interpolated.

**α must not come from the 1-byte point.** On the inter-node container it reads 17.10 µs while 4–32 B all read ~13.2 µs; it is the noisiest point in the dataset (CV 35%) and using it inflated α by 27%. `alpha_B()` takes the median of the genuinely flat region.

## 7. What the figures say together

**Containerisation's cost is concentrated in the MPI network transport.**

- In **shared memory** it is small and can reverse sign — Allreduce is 20% *faster*, because native's UCX pays a CMA syscall the container's cache-resident copy avoids.
- Across the **network** it is severe and per-message — 12 µs on every message, so small messages suffer ~9–12× while bulk transfer suffers ~4.7×.
- For **all-to-all at scale** it is not a slowdown but a **hard functional limit**: 512 ranks cannot run.

That framing makes the IOR and h5bench null results consistent rather than contradictory — I/O is not transport-bound, so it never exposes the defect — and gives Phase 3 a falsifiable prediction: bind-mounting the host MPI should make Alltoall **run**, close most of the inter-node gap, and leave I/O unchanged.
