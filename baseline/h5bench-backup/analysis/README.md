# h5bench analysis — figures and what they show

Parsing, statistics and figures for the h5bench baseline. Numbering and style mirror `../../osu/analysis/` and `../../ior/analysis/` so all three benchmarks read the same way.

```
common.py        parsing, unit normalization, 95% CI helpers
plot_h5bench.py  generates all 4 figures
make_summary.py  the CSV/markdown summary table
figures/         fig1a, fig2a, fig2b, fig3
GUIDE.md         the plotting plan these follow
```

```bash
../../../.venv/bin/python plot_h5bench.py
```

Native and container together in every figure, mean + **95% CI** over `REPS=10`, value labels throughout.

| slot | OSU | IOR | h5bench |
|---|---|---|---|
| 1a | pt2pt latency | transfer sweep | **layout study** |
| 2a | allreduce scaling | weak scaling | **weak scaling** |
| 2b | alltoall scaling | strong scaling | **strong scaling** |
| 3 | port exhaustion | — | **collective I/O factorial** |

---

## 1. Units — the trap to handle first

h5bench labels **binary** units as decimal and switches between `MB/s` and `GB/s` by magnitude, so `1 "GB" = 1024 "MB"`. Averaging raw numbers mixes scales — an early draft reported a nonsensical **497 GiB/s** that way. `common.to_gib()` normalizes through the unit column; every figure is in GiB/s.

Results also live under `payload/<variant>/<config>/<random-uuid>/` because the driver rewrites `CSV_FILE` (`src/h5bench.py:370`). The UUID carries no ordering; the repetition index survives only in the filename.

## 2. The figures

### `fig1a_intra_layout.png` — intra-node layout study

Write bandwidth across the four `MEM_PATTERN × FILE_PATTERN` combinations, 128 ranks on one node. Probes how the memory→file mapping drives HDF5's internal conversion buffers and the writes it submits to Lustre.

### `fig2a_weak_scaling.png` — can Lustre absorb more load?

`DIM_1` fixed at 1 M particles/rank, so every rank writes 32 MiB per timestep and total volume grows with node count.

Aggregate bandwidth rises to **2.589 GiB/s at 8 nodes** but plateaus well below the dashed ideal — shared Lustre saturation, not a container effect.

### `fig2b_strong_scaling.png` — does splitting fixed work still help?

128 M particles total, fixed; per-rank share shrinks 1 M → 128 k as nodes are added.

| nodes | 1 | 2 | 4 | 8 |
|---|---|---|---|---|
| native efficiency | 100% | 61% | 26% | **11%** |
| container efficiency | 100% | 60% | 30% | **10%** |

Efficiency collapses because per-rank payloads become too small to amortise filesystem and request overhead — not because concurrency itself is the limit.

**Read 2A and 2B together for the sharpest h5bench result.** At **identical rank counts** (1024 ranks, 8 nodes):

| | per-rank write | native bandwidth |
|---|---|---|
| weak scaling | 32 MiB | **2.589 GiB/s** |
| strong scaling | 4 MiB | **0.985 GiB/s** |

**2.6× at the same concurrency, from per-rank write size alone.** Rank count is not what governs h5bench throughput — the size of each rank's contribution is. That is why strong scaling collapses while weak scaling does not.

### `fig3_collective_io.png` — the mechanistic study

Left: absolute bandwidth across the 2×2 factorial at 2 nodes / 256 ranks. Right: each switch isolated by subtraction from `dno_mno`, **with the uncertainty on each difference**.

| switch | native | container |
|---|---|---|
| `COLLECTIVE_DATA` alone | +10.3% ± 11.2% — **ns** | **+18.7% ± 11.3% — resolves** |
| `COLLECTIVE_METADATA` alone | +2.2% ± 12.7% — **ns** | −0.1% ± 13.5% — **ns** |

**Only one of the four effects resolves at 95%.** The right panel hatches the other three and marks them `ns`, with error bars visibly crossing zero.

**Why metadata does nothing.** `COLLECTIVE_METADATA` consolidates HDF5 metadata through one rank instead of 256 hitting the MDT. That matters when metadata is a meaningful share of the work — here it is not. Each rank writes 32 MiB × 5 timesteps against a handful of dataset operations, so bulk data utterly dominates and consolidating metadata saves a cost that was already negligible. The ±13% intervals confirm it: the sign of −0.1% is arbitrary.

**Why the 2×2 was necessary.** A single collective on/off switch would have shown "collective I/O helps" without revealing that *all* of the benefit comes from the data path and none from metadata. The factorial is what makes the effect attributable.

**One result worth flagging rather than glossing.** The container's data-aggregation gain resolves while native's does not, and the container ends up faster in absolute terms (1.80 vs 1.67 GiB/s). Two-phase aggregation trades disk access for network communication — the container's weak point — so this is counter-intuitive. At 2 nodes with 128 ranks each, most aggregation traffic is intra-node shared memory, so the network penalty may simply not bite at this scale. **A profiling question, not a settled one.**

## 3. Reads are excluded — and why there is no figure for it

A cold-read validation study ran separate write and read jobs on different nodes, with `node_overlap.txt` recording whether any read rank landed on a writer's node.

**It measured 31× page-cache inflation** (65.5 → 2.1 GiB/s) on the cells that validated, which is why **write bandwidth only** is reported throughout.

**But two of its four cells were void.** PBS reused the just-freed write nodes for the read job in both native cells (overlap 1-of-1 at 1 node, 2-of-2 at 2 nodes), so those reads came from page cache. All four experiments ran and completed successfully — nothing was skipped — but there is **no valid native cold read**, and therefore no native/container read comparison.

**No figure.** A plot documenting its own partial failure would obscure the finding behind experimental noise. The useful content is two sentences, and they are above.

> **Methodological note worth keeping in the thesis.** PBS node reuse defeated cold-read measurement in half the attempts. The `node_overlap` guard caught it both times — which is the practical contribution here for anyone repeating this work on a busy scheduler. Closing the gap needs a rerun with write and read forced onto disjoint node sets (`submit_coldread_full.sh` was written for this).

## 4. What was removed

Fourteen figures from five earlier scripts:

| removed | now |
|---|---|
| `h5bench_intra_pattern_bar`, `_overhead` | `fig1a` |
| `h5bench_weak_scaling`, `_strong_scaling`, `_strong_efficiency` | `fig2a`, `fig2b` |
| `h5bench_collective_bar`, `_gain`, `_variance` | `fig3` |
| `h5bench_coldread_calibration`, `_inflation`, `figA1` | §3 text |
| `h5bench_overhead_summary`, `h5bench_perrank_size` | §2 text |
| `h5bench_scaling_reads` | dropped — reads are cache-inflated |

The five scripts that produced them are folded into `plot_h5bench.py`.

## 5. What h5bench contributes to the thesis

**No measurable container write penalty** — consistent with IOR, and the corroboration matters because the two reach Lustre through *different stacks*: IOR via raw POSIX/MPI-IO, h5bench via HDF5 → MPI-IO → POSIX. Two independent paths, same null result.

What h5bench does resolve is about the I/O path, not the container:

- **per-rank write size governs throughput**, not rank count — 2.6× at identical concurrency
- **collective data aggregation gives a real gain** (resolvable in the container); **collective metadata gives none** at this workload
- **page-cache inflation is 31×**, which is why only writes are reported

Set beside OSU — container up to 12× slower, Alltoall failing outright — the combined claim is:

> **Containerization's cost is concentrated in the MPI transport. Application-shaped HDF5 I/O is not transport-bound enough to expose it: throughput is governed by layout, per-rank write size, and collective-aggregation choices rather than by the runtime environment.**
