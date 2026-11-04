# OSU analysis — figures and what they show

Parsing, statistics and figures for the OSU baseline. Mirrors `../../h5bench/analysis/` and `../../ior/analysis/` so all three benchmarks look consistent in the report.

```
common.py     shared parsing, statistics, style
plot_osu.py   generates 5 figures
figures/      fig1a, fig1b, fig2b, fig2d, fig3
GUIDE.md      the plotting/analysis plan, checked against the data in section 3
```

**Trimmed to 5 figures for the report** (2026-11-04): intra-node collective scaling (`fig2a` Allreduce, `fig2c` Alltoall), inter-node relative growth (`fig2e`), the NP=64 appendix (`figA1`), and the Hockney decomposition (`fig4`) are no longer plotted — the first three are discussed in `baseline/osu/results/collective/intra_node/README.md` instead; the Hockney figure was dropped outright (not needed for this report). This document now only discusses the 5 kept figures.

```bash
../../../.venv/bin/python plot_osu.py
```

**One idea per figure.** An earlier pass merged these into four dense multi-panel figures; that made each harder to read and to caption, and one of them put pt2pt latency and collective latency on the same bar axis — workloads that are not comparable. For a report, a figure answering one question beats a figure answering three.

All line plots show **mean with 95% confidence intervals** (Student's t, n=10) and **value labels on the data points**. Endpoints are always labeled: the smallest message (where fixed per-message cost dominates) and the largest (the asymptotic, bandwidth-saturated regime) are the two most informative points on each curve.

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

## 2. Collective scaling — inter-node only

This report plots Allreduce and Alltoall **inter-node only** (2/4/8 nodes, 128 ranks/node).

### `fig2b_allreduce_inter.png` — Allreduce, 2/4/8 nodes

At 2 nodes (256 ranks) native runs 134 µs while the container runs 471 µs. The container keeps costing roughly 3–6× native from here on.

### `fig2d_alltoall_inter.png` — Alltoall, with the failure

Native keeps running cleanly through all three node counts. The container tracks native with a similar penalty at 2 nodes (256 ranks), then **fails outright at 4 and 8 nodes (512/1024 ranks)**, marked with an X rather than omitted.

Those cells contain **0 data rows** — pure error output. They are excluded from every statistic and drawn explicitly as failures, because "the container cannot run this configuration" is the most consequential OSU result and a figure that silently dropped the points would erase it.

## 3. Diagnostic

### `fig3_port_exhaustion.png` — why Alltoall fails

Three arms from one job on the same four nodes within 51 seconds, plotted against the measured 28,232-port ephemeral limit:

| arm | connections/node | | |
|---|---|---|---|
| container, 128 ranks/node (512 total) | 65,408 (2.32×) | **FAIL** | 512 port errors |
| container, **64** ranks/node (256 total) | 16,320 (0.58×) | **PASS** | |
| native, 128 ranks/node (512 total) | 0 — RDMA | **PASS** | |

Arm 2 changes only the connection count. Arm 3 runs the *same 512 ranks* without TCP. Together they exclude "the scale is too large" and "those nodes were unhealthy", leaving the transport as the only explanation.

**Where the 28,232 and the PASS/FAIL verdicts actually come from** (not hardcoded in the plot — `plot_osu.py`'s `fig_port()` parses this directly, 2026-11-04): `../scripts/collective/inter_node/diagnostics/port_exhaustion_diag.pbs` reads `/proc/sys/net/ipv4/ip_local_port_range` on a real compute node at run time (`32768–60999` → `28232`), not an assumed value. Each arm's verdict is computed from the actual job outcome — `exit_code == 0 and data_rows >= 1` — and `port_errors` is a literal `grep -c "Address already in use"` on that arm's own log, not inferred. Raw log: `../scripts/collective/inter_node/diagnostics/logs/osu_port_exhaustion_diag.out`. Native's bar is plotted as 0, not its own logged "predicted" 65,408 — that predicted figure is the same hypothetical TCP-connection-count used for the paired comparison, but native never opens those sockets at all (UCX/RDMA), so 0 is what it actually does, not an omission.

---

## 4. GUIDE.md checked against the data

Its **analytical** claims all hold exactly:

| claim | measured | |
|---|---|---|
| 3.5×–6× Allreduce slowdown inter-node | **3.52 / 5.71 / 6.11×** | ✅ |
| Alltoall fails from the ephemeral port limit | 65,408 vs 28,232, proven | ✅ |
| do not use Darshan for OSU | confirmed — Darshan wraps only `MPI_File_*` | ✅ |

Three recommendations were **not** adopted, each for a measured reason:

**"Drop Run 1 as warm-up" — rejected as a blanket rule.** Tested over 8 cases: only one has rep1 as a genuine outlier (inter container 1 B, z=3.63); the rest are z≤2.3. That one case is *informative* — rep1 reads 30.36 µs against a 15.63 µs steady state, which looks like **TCP connection-establishment cost**, not noise. Dropping it would delete a finding and discard 10% of the data elsewhere for nothing.

**"Bandwidth on a log-linear axis" — rejected.** 3284× range; see `fig1b`.

**"Report median where CV>15%" — adopted selectively.** Only **26 of 184** points exceed CV 15%, clustered entirely in bandwidth and in the container. `cv()` is reported alongside every mean so the reader can see which is which.

## 5. Three things the code has to get right

**The "better" direction flips between kernels.** `osu_latency` is µs (lower better), `osu_bw` is MB/s (higher better). `ratio()` always returns a **slowdown factor**, inverting bandwidth internally, so **>1 always means the container is worse** in every figure.

**Failed cells stay failed.** See `fig2d` — never dropped, never interpolated.

## 6. What the figures say together

**Containerisation's cost is concentrated in the MPI network transport.**

- Across the **network** it is severe and per-message — inter-node latency goes from 1.46 µs to 13.2–17.1 µs at small sizes (fig1a), so small messages suffer ~9–12× while bulk transfer suffers ~2.4× (fig1b).
- For **all-to-all at scale** it is not a slowdown but a **hard functional limit**: 512 ranks cannot run.

That framing makes the IOR and h5bench null results consistent rather than contradictory — I/O is not transport-bound, so it never exposes the defect — and gives Phase 3 a falsifiable prediction: enabling UCX should make Alltoall **run**, close most of the inter-node gap, and leave I/O unchanged.

> **Update (Phase 3, `optimization/osu/README.md`):** all three held — but the mechanism was a single MCA flag, not the bind-mount this document and `GUIDE.md` assumed would be necessary. The container's OpenMPI had UCX compiled in all along; the baseline's TCP-only results were a launch-script misconfiguration, not a build limitation. See `optimization/osu/README.md` §1–§3 for the full correction.
