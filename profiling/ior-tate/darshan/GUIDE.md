# Darshan profiling — IOR on TATE

## What and why

The baseline (`baseline/ior-tate/analysis/ANALYSIS.md`) found no meaningful container overhead (≤ 1.5% intra-node, ≤ 4.3% inter-node), storage-bound scaling, and a large filesystem effect: OMPIO's default whole-file locking on NFS costs up to ×18 at `-t 64k`. Profiling explains *why* the numbers look like this and checks that native and container really perform the same I/O. The benchmark runs provide the statistics; one profiled run per case is enough.

| # | Case | Reps | Question |
|---|---|---|---|
| 1 | intra, MPI-IO shared, 64k, **default locking** | 3 | Where does the ×18 go? Expect the same writes as case 2, with long gaps (lock waits, 30 s stalls) — in both variants |
| 2 | intra, MPI-IO shared, 64k, **lock fix** (`fs_ufs_lock_algorithm 3`) | 5 | Pair for case 1; and do native and container issue the same MPI-IO and POSIX calls? |
| 3 | intra, POSIX FPP, 64k | 5 | Same check for the POSIX path: identical call counts, sizes and per-call times (4096 writes per rank)? |

64k throughout: it has the largest locking effect and the most calls per rank, so any per-call difference between native and container would be largest there. Each case runs native and container back to back: **6 jobs**.

Left out on purpose: other transfer sizes (the same mechanisms with fewer calls) and the inter-node runs (container gap of −4% to +0.5%, mostly within noise, and bounded by the single NFS server). `ior_*_inter_darshan.sbatch` / `submit_inter_darshan.sh` stay in `scripts/` in case an examiner asks about the inter-node gap; they are not part of the plan. Everything else matches the baseline: 16 ranks per node, `-b 16m -w -m -g -d 5`, `--exclusive`, same UCX settings.

## One Darshan build for both variants

Darshan 3.5.0 (git `main`) is built once on the host against `/usr/bin/mpicc` (OpenMPI 4.1.6) and installed at `~/native/darshan/darshan/install`. The container jobs bind-mount that install to `/opt/darshan` and load it with `LD_PRELOAD`, so both variants are measured by the identical library. This works on TATE because the container has the same OpenMPI 4.1.6 and glibc 2.39; `ldd` inside the image resolves every dependency (checked 2026-11-02, and again at the start of every container job).

The build was configured with `--with-log-path=/darshan-logs --with-jobid-env=PBS_JOBID`. Neither matters here: the jobs set `DARSHAN_LOGFILE` (one exact log path per job) and `DARSHAN_JOBID=SLURM_JOB_ID`.

What gets recorded:
- **POSIX module:** per-file counters for `open`/`write`/`fsync`/…, access sizes, cumulative time (`POSIX_F_WRITE_TIME`, `POSIX_F_META_TIME`).
- **MPI-IO module:** collective vs independent writes, `MPIIO_F_WRITE_TIME`.
- **DXT** (`DXT_ENABLE_IO_TRACE=1`): start/end time of every POSIX and MPI-IO write, per rank — this shows *when* time is lost.

Darshan does not intercept `fcntl`, so it shows the *effect* of locking (gaps between writes, long MPI-IO writes with no long POSIX writes underneath) but not the lock calls. Recorder is for that, afterwards.

## Run

Copy `scripts/` to TATE, e.g. `~/experiments/profiling/ior/darshan/`, then from there:

```bash
./submit_intra_darshan.sh            # cases 1-3: 6 jobs on tate01
./submit_intra_darshan.sh 3          # one case only (numbers as in the table)
squeue -u $USER
```

Case 1 (default locking) can take up to ~30 min because of the 30 s stalls; cases 2 and 3 take a minute or two.

## Output

```
logs/darshan_<variant>_<case>_<jobid>.out/.err      job log: environment, ldd check, log size, counter counts
<variant>/<case>/ior_<jobid>.txt                      IOR result (compare with the baseline; Darshan adds a little overhead)
<variant>/<case>/<case>_<jobid>.darshan               raw Darshan log
<variant>/<case>/<case>_<jobid>.parsed                darshan-parser: all counters
<variant>/<case>/<case>_<jobid>.perf                  darshan-parser --total --perf: totals and I/O time estimates
<variant>/<case>/<case>_<jobid>.dxt.txt               darshan-dxt-parser: per-operation timeline
```

`<case>` is `mpiio_shared_t64k_lockdefault`, `mpiio_shared_t64k_lock3` or `posix_fpp_t64k`. Each job fails loudly if the log is missing, has no POSIX counters, or (MPI-IO cases) has no MPI-IO counters.

## What to look at first

```bash
P=<case>_<jobid>.parsed
grep -P '\tPOSIX_(OPENS|WRITES|FSYNCS)\t' $P | awk '{s[$4]+=$5} END{for(k in s) print k, s[k]}'
grep -P '\tPOSIX_F_(WRITE|META)_TIME\t'   $P | awk '{s[$4]+=$5} END{for(k in s) print k, s[k]}'
grep -P '\tMPIIO_(COLL|INDEP)_WRITES\t'   $P | awk '{s[$4]+=$5} END{for(k in s) print k, s[k]}'
grep -P '\tMPIIO_F_WRITE_TIME\t'          $P | awk '{s[$4]+=$5} END{for(k in s) print k, s[k]}'
```

Counter lines start with the module name and a TAB (`POSIX\t`, `MPI-IO\t`), not `POSIX_`.

1. **Same calls?** `POSIX_WRITES`, `POSIX_OPENS`, `MPIIO_COLL_WRITES` should match between native and container for the same case. A difference would mean the container changes the I/O pattern.
2. **Where is the time?** For MPI-IO, compare `MPIIO_F_WRITE_TIME` with `POSIX_F_WRITE_TIME`. MPI-IO time not covered by POSIX write time is spent in MPI-IO itself: data exchange between ranks, synchronisation, or lock waits (case 1 vs case 2).
3. **When is time lost?** In `.dxt.txt`, look for writes lasting ~30 s (case 1) and note rank, module (`X_MPIIO` vs `X_POSIX`) and repetition. In case 2, compare the number of ranks with POSIX writes (collective-buffering aggregators) with the 16 MPI-IO writers.
