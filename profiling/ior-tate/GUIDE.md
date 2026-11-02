# IOR profiling — plan

What Darshan should answer, given what the baseline actually found. Plan only; nothing run yet.

---

## 1. What the baseline left unexplained

| finding | status |
|---|---|
| no measurable container penalty — median 1.01–1.07×, bounded at ~20–30% | **bounded, not explained** |
| FPP ≈3.5× faster than shared-file | explained (Lustre lock contention) |
| but shared-file **scales better** — 95% vs 58% of ideal at 8 nodes | **hypothesised, unproven** |
| MPI-IO shared-file stops scaling past 4 nodes (28% efficiency) | **hypothesised, unproven** |
| reads 27× cache-inflated | explained, excluded from reporting |

The first row is the one that matters for the thesis. Right now you can only say *"any container effect is below our noise floor"* — a limit of the measurement. Profiling converts it into a statement about mechanism.

Rows 3 and 4 are substantive I/O findings that currently rest on plausible reasoning rather than evidence. They are secondary to the container question but cheap to test with the same runs.

## 2. Hypotheses, each with a prediction that could fail

**H1 — I/O time is dominated by filesystem wait, so the MPI transport never reaches the critical path.**
*Predicts:* `POSIX_F_WRITE_TIME + POSIX_F_META_TIME` accounts for the large majority of wall-clock, in **both** variants. If instead a significant fraction is unaccounted (i.e. spent in MPI), H1 is wrong and the container's transport *should* have mattered.

**H2 — both variants issue identical I/O calls, so there is nothing for the transport to change.**
*Predicts:* `POSIX_WRITES`, `POSIX_OPENS`, `POSIX_SEEKS` and the `POSIX_SIZE_WRITE_*` histogram match between native and container to within a few percent. A difference in call *count* or *size distribution* would be a real finding — it would mean the container changes the access pattern, not just its speed.

**H3 — FPP scales worse because it exhausts Lustre metadata capacity, not bandwidth.**
*Predicts:* `POSIX_OPENS` grows linearly with rank count for FPP (one file per rank) but stays flat for shared-file, and `POSIX_F_META_TIME` rises as a share of total time for FPP at 8 nodes. If META_TIME stays flat, the metadata explanation is wrong and something else limits FPP.

**H4 — MPI-IO shared-file collapses past 4 nodes because collective aggregation stops engaging.**
*Predicts:* `MPIIO_COLL_WRITES` falls (or `MPIIO_INDEP_WRITES` rises) between 4 and 8 nodes, and/or the aggregated write size shrinks. If collective writes stay constant, aggregation is working and the collapse is elsewhere.

**H1 and H2 together are the deliverable.** Same calls + filesystem-bound = the null result explained rather than merely bounded.

## 3. What to extract from each log

```bash
darshan-parser <log> | grep -P '\tPOSIX_F_(WRITE|READ|META)_TIME'    # H1
darshan-parser <log> | grep -P '\tPOSIX_(OPENS|WRITES|SEEKS)\b'      # H2, H3
darshan-parser <log> | grep -P '\tPOSIX_SIZE_WRITE_'                 # H2
darshan-parser <log> | grep -P '\tPOSIX_(FILE|MEM)_ALIGNMENT'        # H2
darshan-parser <log> | grep -P '\tMPIIO_(COLL|INDEP)_(READS|WRITES)' # H4
```

> Counter lines begin `POSIX<TAB>`, not `POSIX_`. Matching on `^POSIX_` returns nothing — this already caught me once during the smoke test.

## 4. Experiment design — 10 runs

Instrument a **subset**, not the suite. The baseline already has the timings; profiling is for the breakdown.

| # | config | scale | tests |
|---|---|---|---|
| 1–8 | POSIX/shared, POSIX/FPP, MPIIO/shared, MPIIO/FPP × native, container | **1 node, 64 ranks** | H1, H2 |
| 9–10 | MPIIO/shared × native, container | **8 nodes, 128 r/node** | H3, H4 |

Everything else identical to the baseline: `-t 4m -b 64m -e -C -i 10`, striping pinned with `lfs setstripe -c 8 -S 1m`, `place=excl`, payload on `/scratch` (Lustre, **not** `$HOME` which is GPFS).

**Keep `-i 10`.** Darshan aggregates over the whole process lifetime, so fewer iterations would not simplify the log — and matching the baseline's workload exactly is what lets the counters be read against the baseline's timings.

## 5. The container problem, and its fallback

`LD_PRELOAD` needs the library inside the container namespace **and** matching the container's MPI ABI. Your Darshan is built against the host's OpenMPI 4.1.2-hpe; the container has generic apt OpenMPI 4.1.2.

| approach | MPI-IO counters? | effort |
|---|---|---|
| bind-mount your build, hope the ABI holds | maybe | minutes — **try first** |
| `DARSHAN_ENABLE_NONMPI=1` + `DARSHAN_MOD_ENABLE=POSIX` | no | minutes — fallback |
| build darshan-runtime inside the `.def` | yes | image rebuild |

**POSIX-only still answers H1, H2 and H3** — those are all POSIX counters. Only **H4 needs MPI-IO**, and H4 is the least important of the four. So a POSIX-only fallback is not a failure; it costs one secondary hypothesis.

## 6. Order of work

1. **Native, 1 node, 4 configs** — confirm the counters are sane against the baseline (e.g. `POSIX_WRITES` should match ranks × block ÷ transfer).
2. **Container, same 4** — via bind-mount, falling back to NONMPI if MPI-IO wrappers misbehave.
3. **Compare** → H1, H2. This is the deliverable; stop here if time is short.
4. **8-node pair** → H3, H4, if the queue allows.

## 7. Scope discipline

**Do not instrument all 40 intra-node configurations.** Four at one node count answer every hypothesis. More runs would add data without adding an answer.

**Do not run Recorder.** Darshan's aggregates answer H1–H4. Recorder produces a call-by-call trace that is large and slow to analyze, and is only worth it once Darshan has localized a question it cannot resolve — most plausibly H4's aggregation pattern. Running it first would spend the remaining time on data you have no question for.

**Do not profile reads.** They are 27× cache-inflated and excluded from the baseline reporting; profiling them would characterize the page cache, not Lustre.

## 8. The sentence this is for

If H1 and H2 hold, the Phase 2 deliverable is:

> *The container's MPI handicap does not surface in parallel I/O because I/O time is dominated by filesystem wait and both variants issue identical POSIX call patterns — the transport is never on the critical path.*

Combined with OSU measuring that transport cost in isolation, that is a complete root-cause story, and it makes Phase 3's prediction falsifiable: bind-mounting the host MPI should fix OSU's inter-node results and leave IOR unchanged.

**If H1 or H2 fails**, that is more interesting, not less — it would mean the container alters the I/O path in a way 20–30% measurement noise was hiding, and that deserves the remaining time.
