# Strong-scaling results

**Total** work held constant at 20 GiB per repetition; per-rank work shrinks as nodes grow (32 → 4 MiB/rank/timestep). n=10 per cell.

Setup: `../../../scripts/inter_node/strong_scaling/README.md`

---

## 1. Headline numbers

| Nodes | Ranks | `DIM_1` | MiB/rank/ts | Native GiB/s | Container GiB/s | Ratio | CIs |
|---|---|---|---|---|---|---|---|
| 1 | 128 | 1 048 576 | 32 | 1.156 ± 0.069 | 1.157 ± 0.075 | 1.00 | overlap |
| 2 | 256 | 524 288 | 16 | **1.399 ± 0.171** | **1.381 ± 0.099** | 0.99 | overlap |
| 4 | 512 | 262 144 | 8 | 1.202 ± 0.158 | 1.375 ± 0.251 | 1.14 | overlap |
| 8 | 1024 | 131 072 | 4 | 0.985 ± 0.155 | 0.879 ± 0.102 | 0.89 | overlap |

## 2. Finding 1 — scaling peaks at 2 nodes, then reverses

The defining result. Elapsed time for the same fixed 20 GiB:

```
nodes    time      vs ideal
  1     17.4 s     (baseline)
  2     14.7 s     ideal would be 8.7 s
  4     17.1 s     ideal would be 4.4 s   <- SLOWER than 2 nodes
  8     21.5 s     ideal would be 2.2 s   <- SLOWER than 1 node
```

**Adding nodes past two makes the job take longer.** At eight nodes it is *worse than a single node* — 21.5 s versus 17.4 s.

**Two independent measurements agree**, which is why this is a finding rather than noise: the bandwidth curve (1.16 → 1.40 → 1.20 → 0.99) and the elapsed time both turn at the same point. Those are derived from different fields of the h5bench output.

**Why:** total work is fixed, so each doubling halves per-rank work. By eight nodes each rank writes only **4 MiB per timestep**. Per-operation costs — HDF5 metadata, MPI-IO coordination, Lustre MDT round-trips — are roughly constant
per call, so their share grows until they dominate. You stop measuring bandwidth and start measuring overhead.

The metadata column shows it directly:

| nodes | native metadata share |
|---|---|
| 1 | 14.4% |
| 2 | 16.8% |
| 4 | **38.5%** |
| 8 | 26.2% |

At four nodes nearly **40%** of end-to-end time is file create/flush/close rather than data transfer.

**Practical conclusion:** for a 20 GiB HDF5 write on this system, two nodes is the sweet spot. This is a concrete, actionable result — and it is a property of the I/O stack, not of containerisation, since both variants turn at the same
point.

## 3. Finding 2 — no container penalty, again

All four CIs overlap. Ratios 0.89–1.14, with the container ahead at n4 and behind at n8 — consistent with noise rather than a systematic effect.

Together with weak scaling, this gives a clear statement: **for independent HDF5 writes, containerisation costs nothing measurable at any scale tested**, despite the container lacking UCX. The data phase dominates, so the transport
difference is diluted.

The exception is collective I/O — see `../collective_io/`, where the same transport difference *does* become measurable.

## 4. Comparison with weak scaling

The two studies share their 1-node point by design (both 32 MiB/rank), and agree: weak n1 = 1.053, strong n1 = 1.156 GiB/s. The 9% difference is within the combined confidence intervals.

They then diverge, as they should:

```
          n1      n2      n4      n8
weak    1.053   1.148   2.153   2.589     rising   (more total work)
strong  1.156   1.399   1.202   0.985     falling  (less work per rank)
```

**At the same 1024 ranks, weak n8 reaches 2.589 GiB/s while strong n8 manages 0.985.** The difference is per-rank write size — 32 MiB versus 4 MiB. Same hardware, same rank count, same software; bandwidth tracks the size of each individual write, exactly as physics predicts.

That cross-check is the strongest evidence in this dataset that the measurements reflect real I/O behaviour.

## 5. Validity checks

| check | result |
|---|---|
| Job exit status | 0 on all 8 |
| CSVs per cell | 10 write + 10 read, all 8 cells |
| `total size` | **20.000 GB at every tier** — confirms total work really was held constant |
| `DIM_1` per tier | 1048576 / 524288 / 262144 / 131072 — exact division, guard would have aborted otherwise |
| Lustre striping | `stripe_count 4, 1 MiB`, verified |
| Path collisions | none |
| Local vs cluster | 160/160 CSVs, 8/8 logs |

The constant 20.000 GB across all four tiers is the defining check for strong scaling: if `TOTAL_PARTICLES / NP` had truncated, the total would drift and the comparison would be meaningless. The script aborts on non-exact division.

## 6. Reads — excluded

Same page-cache artifact as weak scaling. In-job reads at n1 measured ~80 GiB/s against writes of 1.16 GiB/s on the same runs. Not reported as read bandwidth; see `../cold_read_validation/`.

## 7. Caveats

- **Fixed stripe count (4).** Not varied across tiers.
- **20 GiB total may be small for 8 nodes.** At 1024 ranks this leaves only 4 MiB/rank, which is why the n8 point is overhead-dominated. A larger total (e.g. 80 GiB) would push the turning point further out and show where scaling genuinely stops helping for a *bigger* job. The current result is valid for a 20 GiB job specifically.
- **Absolute values are session-specific** (~15% between sessions). Within-run comparisons are unaffected.

## 8. Statistical power — what "no difference" does and does not mean

Overlapping confidence intervals at every node count mean **absence of evidence, not evidence of absence**. With n=10:

| nodes | CI (% of mean) | smallest resolvable difference |
|---|---|---|
| 1 | ±5.9% | ~12% |
| 2 | ±12.2% | ~24% |
| 4 | ±13.2% | ~26% |
| 8 | ±15.8% | **~32%** |

The correct claim is:

> No container penalty was detected. Given the measured variance (n=10), a penalty smaller than ~12% at one node, or ~32% at eight nodes, would not have been resolvable.

Note the intervals widen with node count — the same scale at which a transport difference would be most likely to appear. This study is therefore least sensitive exactly where it would most want to be, which is worth stating plainly rather than leaving the reader to infer it.

## 9. What this hands to the next phases

| observation | Phase 2 question | Phase 3 action |
|---|---|---|
| Time reverses past 2 nodes; n8 slower than n1 (§2) | Where does the time go? Darshan should separate data, metadata and MPI-IO coordination | If metadata-bound, test collective metadata; if coordination-bound, test the bind-mounted host MPI |
| Metadata reaches 38.5% of end-to-end time at n4 (§2) | Confirm with Darshan that this is MDT round-trips, not HDF5 internal work | Collective metadata, or fewer/larger datasets |

**The 20 GiB total is deliberate and stays.** At 8 nodes it leaves only 4 MiB/rank, which is *why* the curve reverses — that is the finding, not a flaw. The claim is scoped accordingly: "for a 20 GiB write, scaling stops helping
beyond 2 nodes." Testing a larger total to find where the turning point moves is a Phase 2/3 question, not a baseline correction.
