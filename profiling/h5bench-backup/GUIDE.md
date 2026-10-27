# h5bench profiling — plan

What Darshan and Recorder should answer, given what the baseline actually found. Plan only; nothing run yet.

---

## 1. What the baseline left unexplained

| finding | status |
|---|---|
| no measurable container write penalty, any pattern (CI overlaps on all 4 intra-node layout cells) | **bounded, not explained** |
| CONTIG→INTERLEAVED is 6.1× slower than CONTIG→CONTIG, in *both* variants identically | explained (HDF5 gather, userspace CPU) — not yet confirmed at the syscall level |
| metadata is 23–33% of wall-clock in the fast patterns, 3–5% in the slow one | inferred from raw-vs-observed rate subtraction, not yet confirmed by a direct per-phase timer |
| weak scaling plateaus at 2.589 GiB/s @ 8 nodes ("shared Lustre saturation") | **hypothesised, unproven** |
| strong scaling efficiency collapses to ~10% @ 8 nodes ("per-rank payload too small to amortise overhead") | **hypothesised, unproven** |
| container's `COLLECTIVE_DATA` gain resolves (+18.7%); native's does not (+10.3%, ns); container ends up faster in absolute terms (1.80 vs 1.67 GiB/s) | **flagged in the baseline's own analysis as "a profiling question, not a settled one"** |

The last row is the one that matters most. Every other container comparison in h5bench is a null result (CIs overlap); this is the one cell where the container's *mean* beats native's by enough to actually resolve, and the baseline explicitly declined to call it settled. That makes it the centerpiece of this plan — the only place profiling could overturn a conclusion rather than just explain one.

## 2. Hypotheses, each with a prediction that could fail

**H1 — intra-node I/O time is filesystem/metadata-bound, not MPI-transport-bound, in both variants.** (Extends IOR's H1 to HDF5's own POSIX layer.)
*Predicts:* `POSIX_F_WRITE_TIME + POSIX_F_META_TIME` accounts for the large majority of wall-clock in all 4 layout cells, native and container alike. This is *expected* to hold — intra-node, both variants share one Lustre client (`results/intra_node/README.md` §2) — so confirming it is a sanity check, not a discovery.

**H2 — native and container issue the same underlying POSIX call pattern, in every layout cell.** (Extends IOR's H2.)
*Predicts:* `POSIX_WRITES`, `POSIX_OPENS` and the `POSIX_SIZE_WRITE_*` histogram match between native and container for each of the 4 `MEM×FILE` combinations. This is what "no container penalty" (overlapping CIs) should look like at the call level — if H1+H2 hold for all 4 cells, the null result is explained rather than merely measured.

**H3 — the already-computed metadata share is a real per-phase cost, not an artifact of the raw/observed subtraction method.**
*Predicts:* `POSIX_F_META_TIME ÷ (POSIX_F_META_TIME + POSIX_F_WRITE_TIME)` from Darshan lands close to the existing 23–33% (fast patterns) / 3–5% (CONTIG→INTERLEAVED) figures in `results/intra_node/README.md` §4, independently confirming that table via a direct timer rather than a derived rate.

**H4 — the CONTIG→INTERLEAVED slowdown is a userspace gather, not a different I/O call shape.**
*Predicts:* the `POSIX_SIZE_WRITE_*` histogram for this cell is **not** dramatically more fragmented than CONTIG→CONTIG's — i.e. HDF5 still submits similarly-sized writes to Lustre, and the 6.1× cost sits in CPU time between calls (gathering 7 arrays into a compound record), not in smaller/more numerous syscalls. If the histogram instead shows a collapse to tiny writes, the mechanism is wrong and it *is* an I/O-shape problem, not a CPU one — Recorder would then be needed to see the actual call sequence (§5).

**H5 — weak-scaling's plateau is shared Lustre saturation, not a container-specific limit.**
*Predicts:* at 8 nodes, `POSIX_F_WRITE_TIME` as a share of wall-clock is high and **similar between native and container** (a shared-resource ceiling affects both equally). If the container's share is markedly higher, the plateau isn't purely filesystem-side.

**H6 — strong-scaling's efficiency collapse is overhead amortization, not a concurrency limit.**
*Predicts:* at 8 nodes, `POSIX_F_META_TIME`'s share of wall-clock is markedly higher in strong scaling (128 KiB/rank) than in weak scaling (32 MiB/rank) at the *same* node count/rank count — directly confirming "per-rank payload too small" as the mechanism, via a counter rather than an inference from the efficiency curve alone.

**H7 — the container's resolved `COLLECTIVE_DATA` gain reflects a genuinely different two-phase aggregation pattern, not noise.** (The centerpiece; Recorder, not Darshan — see §5.)
*Predicts:* the call-by-call trace shows container forming fewer/larger aggregated write requests under `COLLECTIVE_DATA=YES` than its own `=NO` baseline, by a margin consistent with the measured +18.7%; and critically, that most of the aggregation traffic is visible as **intra-node** exchange (shared memory) rather than inter-node — which is the baseline's own stated reason the container's known network weakness might simply not bite at 2-node/128-ranks-per-node scale. If native shows an equally large aggregation-pattern change but it doesn't improve its bandwidth, H7 is wrong and the asymmetry is elsewhere (e.g. HDF5 version difference — native 1.12.1 vs container 1.10.7 — rather than MPI-IO behavior).

## 3. What to extract from each log

```bash
# H1
darshan-parser <log> | grep -P '\tPOSIX_F_(WRITE|META)_TIME'
# H2
darshan-parser <log> | grep -P '\tPOSIX_(OPENS|WRITES)\b'
darshan-parser <log> | grep -P '\tPOSIX_SIZE_WRITE_'
# H3 -- compute META / (META + WRITE) per cell, compare to results/intra_node/README.md §4
# H4 -- same SIZE_WRITE histogram as H2, read against CONTIG->CONTIG as the reference shape
# H5, H6 -- same two time counters as H1, at 8-node scale instead of 1-node
```

> Same counter-naming trap as IOR: lines begin `POSIX<TAB>`, not `POSIX_`. Matching `^POSIX_` returns nothing.

H7 needs Recorder's own trace format, not Darshan counters — verify the exact event/field names against Recorder's README once built (per `profiling/README.md` §4 Stage 4), the same caution already flagged there.

## 4. Experiment design — Darshan, 16 runs

Instrument a **subset**, not the suite — the baseline already has every timing; profiling is for the breakdown.

| # | config | scale | tests |
|---|---|---|---|
| 1–8 | all 4 `MEM×FILE` combos × native, container | **1 node, 128 ranks** (the existing intra-node study) | H1, H2, H3, H4 |
| 9–12 | weak scaling × native, container | **1 node and 8 nodes** | H5 |
| 13–16 | strong scaling × native, container | **1 node and 8 nodes** | H6 |

The 1-node points in rows 9–16 are the cheap calibration baseline (per-rank size and node count both minimal, so a short run); the 8-node points are where H5/H6 actually get tested. Everything else identical to the baseline configs already in `baseline/h5bench/scripts/`: same `DIM_1`/`NUM_PARTICLES`, same `-i 10` repetitions worth of signal (though profiled runs likely need fewer reps than the full statistical baseline — Darshan aggregates per-process-lifetime, so 1–3 reps is enough to get a representative log, not 10), same Lustre striping, same `place=excl`.

`COLLECTIVE_DATA`/`COLLECTIVE_METADATA` are **not** part of the Darshan matrix — that factorial is the Recorder target (§5), where the question is about the aggregation *pattern*, not aggregate time.

## 5. Experiment design — Recorder, 6 runs, targeted only

Per `profiling/README.md`'s own rule (Darshan first, Recorder only on a specific question) and the IOR plan's precedent (Recorder was skipped there entirely, with H4 left to a future pass) — this is the one place in the whole project's profiling work where Recorder is actually the right tool, because the question is explicitly about *call sequence and aggregator selection*, which Darshan's aggregates cannot show.

| # | config | COLLECTIVE_DATA | COLLECTIVE_METADATA | tests |
|---|---|---|---|---|
| 1–2 | native, container | NO | NO | the `dno_mno` reference pattern |
| 3–4 | native, container | YES | NO | H7 — does the aggregation pattern actually differ where only container's gain resolves |
| 5–6 | native, container | — | — | CONTIG→INTERLEAVED, 1 node — confirms H4 at the call-sequence level if the Darshan histogram result is ambiguous |

All at the same 2-node/128-ranks-per-node scale as the existing `fig3` factorial, so the Recorder trace can be read directly against numbers already in hand. Rows 5–6 are conditional: only run them if H4's Darshan histogram doesn't cleanly settle the question.

## 6. The container problem, and its fallback

Same mechanics as the IOR plan (`profiling/ior/GUIDE.md` §5) and the general setup (`profiling/README.md` §3): `LD_PRELOAD` must resolve inside the container's namespace and match its MPI ABI. h5bench's container launch (`apptainer exec --bind /scratch ${SIF}` embedded directly into `MPI_CONFIG` in `h5bench_container_intra.pbs`) is structurally identical to IOR's, so the same three-tier fallback applies:

| approach | MPI-IO counters? | effort |
|---|---|---|
| bind-mount host Darshan, hope the ABI holds | maybe | **try first** |
| `DARSHAN_ENABLE_NONMPI=1`, POSIX module only | no | fallback |
| build darshan-runtime inside the `.def` | yes | image rebuild |

**POSIX-only still answers H1–H6** — all six are POSIX counters. Only **H7 needs Recorder** regardless (Recorder traces MPI-IO calls directly, independent of this Darshan ABI problem, though it has its own LD_PRELOAD/ABI concern to verify against its own README).

One h5bench-specific wrinkle IOR didn't have: the driver is a **host Python script** (`src/h5bench.py`) that shells out to `apptainer exec ... h5bench_write` — so `LD_PRELOAD` must be set on the *inner* `apptainer exec` invocation, not on the outer `mpirun`/driver process, or it will instrument the Python driver instead of the actual I/O binary. Verify with the same driver-log grep the baseline already uses to confirm the container binary ran (`baseline/h5bench/scripts/README.md:144`), extended to also grep for the LD_PRELOAD env var in that same command line.

## 7. Order of work

1. **Native, 1 node, 4 layout cells** — confirm counters are sane against `results/intra_node/README.md`'s existing numbers (e.g. `POSIX_WRITES` should scale with 1,048,576 particles/rank × 5 timesteps in a predictable way).
2. **Container, same 4 cells** — via bind-mount, falling back to NONMPI if needed.
3. **Compare → H1–H4.** This is the main deliverable for the intra-node half; stop here if time is short.
4. **8-node pair, weak and strong** → H5, H6, if the queue allows.
5. **Recorder, the `COLLECTIVE_DATA` on/off pair, native + container** → H7. This is the one profiling result that could change a conclusion rather than just explain one — prioritize it over H5/H6 if time runs short, not after.

## 8. Scope discipline

**Do not instrument all 4 points of the collective-I/O factorial with Recorder.** `dyes_mno` vs `dno_mno` (±`COLLECTIVE_METADATA`) is where the open question lives; `COLLECTIVE_METADATA`'s own effect is already established as null (§1), so a metadata-focused Recorder run would spend time on a question already answered.

**Do not re-run the full weak/strong scaling sweep under Darshan.** Two node counts (1 and 8) per scaling study is enough to test H5/H6; the intermediate points (2, 4 nodes) add confirmation, not a different answer.

**Recorder is the exception to "Darshan first" only for H7.** Every other hypothesis here is answerable from Darshan aggregates alone, matching the IOR plan's own rule.

## 9. The sentence this is for

If H1–H4 hold, intra-node h5bench gets the same explanation IOR already has:

> *The container's MPI handicap does not surface in single-node HDF5 I/O because both variants share one Lustre client and issue identical POSIX call patterns; the data-shape cost (CONTIG→INTERLEAVED's 6.1×) is a userspace HDF5 gather operation, present identically in both environments.*

**If H7 holds** — container's aggregation pattern genuinely differs and the traffic is visibly intra-node — the deliverable is sharper and more interesting than a null result:

> *The one case where the container measurably outperforms native is explained by two-phase I/O aggregation trading disk access for intra-node shared-memory communication — exactly the container's strength (per the OSU Allreduce finding) rather than its weakness, because at this scale the aggregation traffic never crosses the network.*

That would tie all three benchmarks' profiling into one coherent architecture-level story: the container's transport problem is real and severe (OSU), invisible when I/O dominates (IOR, h5bench's null cells), and can even reverse favorably when the workload happens to route through the container's actual advantage (shared memory) instead of its actual weakness (the network) — which is a stronger, more specific claim than "containerization doesn't matter for I/O."

**If H7 fails** (native shows the same aggregation change without the same benefit), that's still worth reporting: it would point at the HDF5 version difference (1.12.1 vs 1.10.7) as the more likely explanation, which is itself useful groundwork for anyone trying to reproduce this on a different HDF5 pairing.

## 10. Implementation status

**Code is written. Nothing has been run.** All scripts below were built by adapting the matching baseline script (`baseline/h5bench/scripts/...`) with Darshan/Recorder instrumentation inserted into the same `MPI_CONFIG` string the baseline already uses — no other part of any baseline script was changed, so a working profiling run should reproduce the baseline's own bandwidth numbers alongside the new counters.

```
darshan/scripts/
  h5bench_config_intra.json.template     (copy of the baseline intra template)
  h5bench_config_weak.json.template      (copy of the baseline weak template)
  h5bench_config_strong.json.template    (copy of the baseline strong template)
  h5bench_native_intra_darshan.pbs       -- rows 1-8 (native half), H1-H4
  h5bench_container_intra_darshan.pbs    -- rows 1-8 (container half), H1-H4
  submit_intra_darshan.sh                -- submits all 8
  h5bench_native_scaling_darshan.pbs     -- rows 9-16 (native half), H5/H6, MODE+NODE_COUNT params
  h5bench_container_scaling_darshan.pbs  -- rows 9-16 (container half), H5/H6
  submit_scaling_darshan.sh              -- submits all 8

recorder/scripts/
  h5bench_config_collective.json.template
  h5bench_native_collective_recorder.pbs     -- H7, native, COLL_DATA param
  h5bench_container_collective_recorder.pbs  -- H7, container, COLL_DATA param
  submit_collective_recorder.sh              -- submits all 4 (native/container x YES/NO)
```

Rows 5–6 of the Recorder plan (the conditional CONTIG→INTERLEAVED confirmation of H4) are **not yet built** — per the plan, only write them if the Darshan histogram in rows 1–8 leaves H4 ambiguous.

**Before submitting anything, verify these — none have been tried yet:**

1. **`DARSHAN_LIB` / `DARSHAN_HOST_INSTALL` paths.** The Darshan scripts assume the native build already validated in `profiling/scripts/stage0_validate/` lives at `$HOME/scratch/fyp/native/darshan/darshan/install/lib/libdarshan.so`. `profiling/SETUP.md`'s Path B instructions describe building to a separate `install-ompi` prefix — confirm which one actually exists before running, with `ldd <path>/lib/libdarshan.so | grep -i mpi` (expect `libmpi.so.40`, never `libmpi_cray.so.12`).
2. **`RECORDER_HOST_INSTALL` path**, same caution — `$HOME/scratch/fyp/native/recorder/Recorder/install`, per the stage0 script. Verify the `.so` name and env var names against Recorder's own README once confirmed, same instruction `profiling/SETUP.md` §5 already gives.
3. **The container bind-mount itself is untried for h5bench specifically.** `profiling/SETUP.md` §3 and the IOR plan both flag this as "expect POSIX to work, MPI-IO to be unreliable" for Darshan — that reasoning has not actually been tested against h5bench's container image. The Darshan container scripts default to `DARSHAN_ENABLE_NONMPI=1` + POSIX-only specifically to sidestep this risk, since H1–H6 don't need MPI-IO. The Recorder container script has **no such fallback** (H7 specifically needs MPI-IO tracing) — if the bind-mount doesn't produce a usable trace, that failure is itself worth reporting rather than working around, per the script's own header comment.
4. **The in-container `DARSHAN_LOGFILE`/trace-dir path construction** (`realpath --relative-to=...` building a `/scratch/...` path) is logic, not yet exercised — sanity-check the computed path once on a real job before trusting the loop to run 8 times unattended.
5. **REPS defaults** (2 for Darshan, 1 for Recorder) are a first guess, not validated against actual log/trace sizes on this system — adjust after seeing how large a real `.darshan` log or Recorder trace directory turns out to be.
