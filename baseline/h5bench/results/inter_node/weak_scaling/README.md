# Weak-scaling results

Per-rank work held constant (32 MiB/rank/timestep), so total volume grows with node count: 20 / 40 / 80 / 160 GiB per repetition. n=10 per cell.

Setup: `../../../scripts/inter_node/weak_scaling/README.md`

---

## 1. Headline numbers

Write bandwidth, GiB/s, mean ± 95% CI. "Observed" = end-to-end including file create, flush, close and metadata.

| Nodes | Ranks | Native | Container | Container ÷ Native | CIs |
|---|---|---|---|---|---|
| 1 | 128 | 1.053 ± 0.064 | 1.096 ± 0.106 | 1.04 | overlap |
| 2 | 256 | 1.148 ± 0.084 | 1.231 ± 0.136 | 1.07 | overlap |
| 4 | 512 | 2.153 ± 0.131 | 2.260 ± 0.130 | 1.05 | overlap |
| 8 | 1024 | 2.589 ± 0.299 | 2.646 ± 0.281 | 1.02 | overlap |

## 2. Finding 1 — no measurable container penalty at any scale

Every confidence interval overlaps, at every node count. Ratios span 1.02–1.07, all favouring the container slightly, none significantly.

This matters more than it first appears. The container's MPI has **no UCX** and falls back to TCP over `hsn0`; the native build uses UCX+Slingshot. That gap is large in the OSU latency benchmarks. Yet it produces **no measurable write penalty here, even at 1024 ranks**.

The reason is visible in the time column: a weak-scaling repetition takes 19–63 seconds, dominated by moving 20–160 GiB to Lustre. MPI coordination is a small fraction of that, so a slower transport is diluted below the noise floor.

**The conclusion for the thesis is specific:** for bulk, independent HDF5 writes, the container's inferior MPI transport does not cost measurable bandwidth. That is not the same as "containers are free" — see the collective I/O results, where the same transport difference *is* measurable.

## 3. Finding 2 — scaling is sublinear, and saturates

```
nodes   bandwidth    per-node efficiency
  1     1.053          1.053 GiB/s
  2     1.148          0.574
  4     2.153          0.538
  8     2.589          0.324
```

8× the nodes buys **2.46×** the bandwidth. Per-node efficiency falls to 31% of the single-node figure. That is Lustre saturating, not an MPI or container effect — both variants degrade identically.

## 4. The n1 → n2 plateau — flagged, not explained

Doubling from 1 to 2 nodes gained only **9%** (1.053 → 1.148), while 2 → 4 gained **88%**. That is not the smooth curve weak scaling should produce.

**It is not noise.** Per-repetition values:

```
n1: 0.96 0.97 0.98 1.00 1.02 1.04 1.06 1.12 1.15 1.23
n2: 0.95 1.03 1.05 1.08 1.11 1.22 1.23 1.23 1.29 1.29
n4: 1.87 1.91 2.06 2.12 2.16 2.17 2.19 2.25 2.29 2.50
```

n1 and n2 overlap substantially; n4 separates cleanly. The plateau is real.

**Leading hypothesis, untested:** `stripe_count` is fixed at **4** for every tier. Each shared file is therefore spread over the same 4 OSTs regardless of whether 128 or 1024 ranks are writing to it. At small node counts the 4 OSTs
may already be saturated, so adding client nodes adds nothing — the bottleneck is downstream of the clients.

That would make the n1/n2 points a measurement of **OST bandwidth**, not of client scaling.

**How to test it cheaply:** rerun n1 and n2 with `lfs setstripe -c 8` or `-c -1` (all OSTs). If the plateau disappears, striping was the cause. One parameter, 4 jobs.

Until tested this stays a hypothesis. It is stated as a limitation rather than a conclusion.

## 5. Metadata share decreases with scale

| nodes | native metadata share | container |
|---|---|---|
| 1 | 20.9% | 22.3% |
| 2 | 15.0% | 14.1% |
| 4 | 14.0% | 8.7% |
| 8 | 7.0% | 10.5% |

File create, flush and close cost ~21% of end-to-end time at one node, falling to ~7–10% at eight. The metadata cost is roughly fixed per run while the data phase grows, so its share shrinks.

Consequence: reporting `raw rate` instead of `observed rate` would overstate achievable bandwidth by up to a fifth at small scale. All figures here use observed.

## 6. Reads — excluded, see the calibration

In-job read figures are **not reported as read bandwidth**. The read follows the write in the same config on the same nodes, so it is served from page cache. At n1 the measured read was **65.5 GiB/s** against a write of 1.05 GiB/s on the same run — the data never reached Lustre.

A separate cold-cache measurement on disjoint nodes gives the real figure:

| nodes | warm (in-job) | cold (disjoint nodes) | inflation |
|---|---|---|---|
| 1 | 65.50 | **2.13** | **31×** |
| 2 | 3.88 | **3.31** | 1.2× |

The inflation collapses from 31× to 1.2× between one and two nodes — exactly what a cache effect predicts, since 20 GiB fits easily in one node's 440 GB RAM but 40 GiB spread over two nodes displaces more of it.

See `../cold_read_validation/` for method and the node-overlap verification.

## 7. Validity checks

| check | result |
|---|---|
| Job exit status | 0 on all 8 |
| CSVs per cell | 10 write + 10 read, all 8 cells |
| `total size` per tier | 20 / 40 / 80 / 160 GB, single value each |
| `DIM_1` in every config | `1 M` — the `NUM_PARTICLES` trap did not recur |
| Lustre striping | `stripe_count 4, 1 MiB`, verified by `lfs getstripe` |
| Path collisions | none — every payload dir has exactly one job ID |
| Local vs cluster | 160/160 CSVs, 8/8 logs |

**Cross-experiment anchor:** weak n1 native = **1.053** GiB/s against intra-node `CONTIG→CONTIG` native = **1.086** GiB/s. These are the same workload submitted as two independent experiments, agreeing to **3.1%** — good evidence the measurement is reproducible within a session.

## 8. Caveats

- **Fixed stripe count (4) at all scales.** May bound the small-node results (§4). IOR's study varied stripe count; this one does not.
- **Absolute values are session-specific.** A previous run of the identical configuration measured ~15% higher. Within-run native/container comparisons are unaffected; cross-session absolute comparisons should not be made.
- **One access pattern.** `CONTIG`/`CONTIG` only, chosen so scaling behaviour is not confounded with access-pattern effects (those are in `intra_node/`).

## 9. Statistical power — what "no difference" does and does not mean

The container/native comparison reports overlapping confidence intervals at every node count. That is **absence of evidence, not evidence of absence**.
With n=10 and the measured variance, the smallest difference this experiment could resolve is:

| nodes | CI (% of mean) | smallest resolvable difference |
|---|---|---|
| 1 | ±6.0% | ~12% |
| 2 | ±7.3% | ~15% |
| 4 | ±6.1% | ~12% |
| 8 | ±11.6% | ~23% |

So the correct claim is:

> No container penalty was detected. Given the measured variance (n=10), a penalty smaller than ~12% at one node, or ~23% at eight nodes, would not have been resolvable.

Raising n would help only as sqrt(n) — going to n=20 narrows the intervals by ~29%, still leaving ~16% unresolvable at eight nodes. The variance is intrinsic to a shared production cluster, so the honest response is the caveat rather than more repetitions.

## 10. What this hands to the next phases

This is a **baseline**: it establishes behaviour and surfaces questions. Two concrete targets for Phase 2 (profiling) and Phase 3 (optimisation):

| observation | Phase 2 question | Phase 3 action |
|---|---|---|
| n1 -> n2 gains only 9%, n2 -> n4 gains 88% (§4) | Is the small-node case OST-bound? Darshan / `lfs getstripe` on those runs | Vary `stripe_count` (4 -> 8 -> -1), re-benchmark, quantify |
| Per-node efficiency falls to 31% by n8 (§3) | Where does the time go at scale — data, metadata, or coordination? | Striping and/or collective I/O tuning |

Deliberately **not** tuned here: stripe count is fixed at 4 for every tier so the baseline is a single consistent configuration. Tuning it is Phase 3 work.
