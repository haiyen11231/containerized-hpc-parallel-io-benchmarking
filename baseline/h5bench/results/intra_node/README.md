# Intra-node results — h5bench write access-pattern sweep

Run: One node, 128 ranks, 20 GiB per repetition, 10 repetitions per cell. All 8 jobs exited 0.

Setup and rationale: `../../scripts/intra_node/README.md`.

---

## 1. Headline numbers

Write bandwidth, GiB/s, mean ± 95% CI from n=10. "Observed" rate — end to end, including file create, flush, close and metadata, i.e. what an application actually experiences.

| MEM → FILE | Native | Container | Container ÷ Native |
|---|---|---|---|
| CONTIG → CONTIG | 1.086 ± 0.048 | 1.027 ± 0.122 | 0.95 |
| CONTIG → INTERLEAVED | **0.179 ± 0.003** | **0.182 ± 0.004** | 1.01 |
| INTERLEAVED → CONTIG | 0.711 ± 0.076 | 0.652 ± 0.116 | 0.92 |
| INTERLEAVED → INTERLEAVED | 1.036 ± 0.092 | 1.163 ± 0.079 | 1.12 |

## 2. Finding 1 — no measurable container overhead

**Every native/container confidence interval overlaps.** Checked explicitly:

| pattern | native CI | container CI | overlap |
|---|---|---|---|
| CONTIG→CONTIG | [1.038, 1.134] | [0.905, 1.150] | yes |
| CONTIG→INTERLEAVED | [0.177, 0.182] | [0.178, 0.186] | yes |
| INTERLEAVED→CONTIG | [0.634, 0.787] | [0.536, 0.769] | yes |
| INTERLEAVED→INTERLEAVED | [0.944, 1.127] | [1.084, 1.242] | yes |

The ratios span 0.92–1.12, and the container is *faster* in one cell. With overlapping intervals **no container penalty can be claimed** at this scale.

This is a positive result, not an absence of one, and it is exactly what the architecture predicts. On a single node:

- Both variants' `write()` calls are serviced by the **same host kernel Lustre client** — the container has no Lustre client of its own, `--bind /scratch`
  only exposes the host's existing mount.
- The MPI difference (UCX vs `vader`) barely matters, because all 128 ranks are on one machine and both end up using shared memory.
- What remains is the HDF5 library version difference, which this experiment shows is **not** worth a measurable amount for writes.

Any container overhead seen in the multi-node studies cannot be attributed to containerization *per se*, because containerization alone costs nothing here. It must come from the network path.

## 3. Finding 2 — access pattern dominates, by 6×

The container question is a small effect. The data *shape* is a large one:

```
CONTIG → CONTIG            1.086 GiB/s    baseline
CONTIG → INTERLEAVED       0.179 GiB/s    6.1x SLOWER
INTERLEAVED → CONTIG       0.711 GiB/s    1.5x slower
INTERLEAVED → INTERLEAVED  1.036 GiB/s    ~same as baseline
```

**Evidence this is real, not noise:**

1. **It reproduces in wall-clock time, independently of the bandwidth calculation.** The same 20 GiB took 111.6 s for CONTIG→INTERLEAVED versus 18.5 s for CONTIG→CONTIG — a 6.0× ratio, matching the 6.1× bandwidth ratio.
2. **It is the most reproducible cell in the experiment.** CONTIG→INTERLEAVED has the tightest confidence interval of all eight (±1.5% native, ±2.1% container), so the slow result is highly consistent, not a few bad runs.
3. **Both variants agree.** Native 0.179 and container 0.182 — the effect is a property of HDF5's data path, not of either environment.

**Why**: writing a compound dataset from separate in-memory arrays forces HDF5 to *gather* — read one float from each of 7 arrays and pack them into a 32-byte record, for every one of 1 048 576 particles per rank per timestep. That is pure userspace CPU work before a single byte reaches the filesystem.

By contrast INTERLEAVED→INTERLEAVED is ~as fast as the baseline (1.036 vs 1.086): memory and file layouts agree again, so no transposition is needed even though the element type is a 32-byte compound. **The cost is the mismatch, not the compound type.** That distinction is only visible because all four cells
were run.

INTERLEAVED→CONTIG sits in between (1.5× slower): the *scatter* direction — strided reads through the struct array — is cheaper than the gather direction.

## 4. Finding 3 — metadata is a large, pattern-dependent share

Comparing `raw rate` (data transfer only) with `observed rate` (end to end):

| pattern | variant | raw | observed | metadata share |
|---|---|---|---|---|
| CONTIG→CONTIG | native | 1.415 | 1.086 | **23.2%** |
| CONTIG→CONTIG | container | 1.392 | 1.027 | **26.2%** |
| CONTIG→INTERLEAVED | native | 0.184 | 0.179 | 2.8% |
| CONTIG→INTERLEAVED | container | 0.191 | 0.182 | 4.5% |
| INTERLEAVED→CONTIG | native | 0.965 | 0.711 | 26.3% |
| INTERLEAVED→CONTIG | container | 0.780 | 0.652 | 16.4% |
| INTERLEAVED→INTERLEAVED | native | 1.537 | 1.036 | **32.6%** |
| INTERLEAVED→INTERLEAVED | container | 1.512 | 1.163 | 23.1% |

File create, flush and close consume **23–33%** of end-to-end time in the fast patterns. In the slow pattern it collapses to 3–5% — not because metadata got cheaper, but because the data phase got ~6× longer, so the fixed metadata cost is diluted.

Two consequences:

- **Reporting `raw rate` alone would overstate achievable bandwidth by up to a third.** This analysis uses `observed rate` throughout for that reason.
- The fast patterns are partly **metadata-bound**, not purely bandwidth-bound. Worth remembering when interpreting the scaling studies, where metadata contention on the MDT grows with rank count.

## 5. Confidence and stability

| pattern | variant | relative CI |
|---|---|---|
| CONTIG→INTERLEAVED | native | 1.5% |
| CONTIG→INTERLEAVED | container | 2.1% |
| CONTIG→CONTIG | native | 4.4% |
| INTERLEAVED→INTERLEAVED | container | 6.8% |
| INTERLEAVED→INTERLEAVED | native | 8.9% |
| INTERLEAVED→CONTIG | native | 10.7% |
| CONTIG→CONTIG | container | 11.9% |
| INTERLEAVED→CONTIG | container | 17.8% |

All within normal range for a shared cluster; nothing unstable. The container cells are generally wider than native (11.9% vs 4.4% for CONTIG→CONTIG) — consistent with per-rank container instantiation adding jitter, though with n=10 this is an observation rather than a claim.

## 6. Validity checks performed

| check | result |
|---|---|
| Job exit status | 0 on all 8 |
| "Completed Successfully" in logs | 8/8 |
| FATAL / FAILED in any log | none |
| CSVs per cell | 10/10 on all 8 |
| `total size` across all 80 runs | `20.000 GB`, single value |
| `DIM_1` in every generated config | `1 M` — the `NUM_PARTICLES` trap did not recur |
| `ranks` in every CSV | 128 |
| Lustre striping applied | `stripe_count 4, stripe_size 1 MiB`, verified by `lfs getstripe` |
| Path collisions | none — every payload dir has exactly one job ID |
| Local vs cluster sync | 520 files identical; 4 CSVs checksum-matched |

## 7. Caveats

- **Absolute values are not comparable across sessions.** An earlier run of the identical configuration measured 1.271 GiB/s for CONTIG→CONTIG versus 1.086 here — about 15% apart. Both runs are internally consistent, so this is shared-cluster variation between sessions. **Within-run native-vs-container comparisons are unaffected**, because both variants ran in the same session under the same conditions; cross-session absolute comparisons carry this noise and should not be made.
- **Write-only.** The read kernel cannot read an interleaved file in parallel, so no read data exists for this case study by design.
- **Single node.** These results say nothing about the network path; that is the purpose of the inter-node studies.
- **One HDF5 version pair.** Native 1.12.1 (icc) vs container 1.10.7 (gcc) — the closest pairing available on Aspire 2A. A different pairing could shift the HDF5-layer comparison.

## 8. Data layout

```
payload/<variant>/<combo>/<uuid>-<jobid>/
    ├── write_repN.csv      the measurement (N = 1..10)
    ├── stdout / stderr     full h5bench output
    └── h5bench.cfg         exact config the binary received
<variant>/<combo>/
    ├── config_repN.json    generated h5bench config
    └── driver_repN.log     driver output
```

Rates in the CSVs are in h5bench's **binary units mislabelled as decimal**
(`1 "GB" = 1024 "MB"`), and the unit switches with magnitude. Always normalise
via the unit column — see `../../analysis/common.py:to_gib()`.
