# Darshan profiling results — IOR intra-node on TATE

Six profiled runs, 2026-11-02: tate01, 16 ranks, `-t 64k -b 16m -w -m -g -d 5`, native vs container, one job each (207–212). Darshan 3.5.0 with DXT (per-call trace); the container loads the same host Darshan build. Plan and method: `GUIDE.md`.

| Case | Jobs (native / container) | Reps | IOR write MiB/s per rep, native | container |
|---|---|---|---|---|
| MPI-IO shared, default locking | 207 / 208 | 3 | 0.54, 5.58, 16.27 | 0.55, 5.53, 5.53 |
| MPI-IO shared, lock fix (`fs_ufs_lock_algorithm 3`) | 209 / 210 | 5 | 161–167 | 159–166 |
| POSIX FPP | 211 / 212 | 5 | 70–73 | 70–72 |

Darshan's own overhead is negligible: the lock-fix and POSIX FPP bandwidths match the unprofiled baseline (~158–172 and ~63–70 MiB/s). The default-locking run was hit even harder than in the baseline (first repetition: 470 s for 256 MiB), which is the same stall mechanism at work.

Files: `results/<variant>/<case>/` (raw `.darshan`, `.parsed` counters, `.perf` totals, `.dxt.txt` trace, `ior_<jobid>.txt`), `results/logs/`, and one PyDarshan HTML report per run in `results/reports/` (open in a browser). Numbers below come from `analysis/summarize_darshan.py`.

## 1. Native and container perform exactly the same I/O

| Counter (summed over the IOR test files) | MPI-IO default | MPI-IO lock fix | POSIX FPP |
|---|---|---|---|
| `POSIX_WRITES` native / container | 12291 / 12291 | 20485 / 20485 | 20480 / 20480 |
| `POSIX_BYTES_WRITTEN` | identical (768 MiB) | identical (1280 MiB) | identical (1280 MiB) |
| `POSIX_OPENS` | 201 / 201 | 335 / 335 | 80 / 80 |
| `MPIIO_COLL_WRITES` | 12288 / 12288 | 20480 / 20480 | — |
| POSIX writer ranks | 0 and 8 / 0 and 8 | 0 and 8 / 0 and 8 | all 16 / all 16 |
| Mean POSIX write call | 0.08 / 0.09 ms | 0.07 / 0.07 ms | 13.75 / 13.76 ms |
| `POSIX_F_WRITE_TIME` (cumulative) | 1.02 / 1.12 s | 1.42 / 1.46 s | 281.67 / 281.75 s |

Every call count, byte count and access size is identical, the same ranks do the writing, and the time per POSIX write call matches to within 0.01 ms. The container changes neither the I/O pattern nor the cost of an individual I/O call. This is the mechanism behind the benchmark result of no measurable container overhead: the container's processes issue the same system calls to the same host NFS client, and nothing on the I/O path is different.

## 2. How MPI-IO collective writes reach the filesystem

With `-c` (collective I/O), OMPIO funnels the data of all 16 ranks through **2 aggregator ranks (0 and 8)**, which issue all the POSIX writes; the other 14 ranks never call `write()` on the file. The POSIX writes stay 64 KiB each (one per rank's transfer, because each rank's 64 KiB lies 16 MiB away from its neighbour's in the file, so they cannot be merged).

## 3. Where the ×18 goes with default locking

| | MPI-IO default | MPI-IO lock fix |
|---|---|---|
| Cumulative MPI-IO write time | **8495 s** native / 8962 s container | 14.7 / 15.1 s |
| ...of which inside POSIX `write()` | 1.0 / 1.1 s | 1.4 / 1.5 s |
| MPI-IO write calls ≥ 29 s | 253 / 272 | 0 / 0 |
| Longest MPI-IO write call | 60.6 s / 30.5 s | < 0.01 s |
| Stall events (gap ≥ 29 s between aggregator writes) | 16 / 17 | 0 / 0 |
| Time lost in those gaps | 484 s / 512 s (of 547 s run) | 0 |
| Median gap between consecutive aggregator writes | 3.5 ms | ~0 ms |

With default locking, more than 99.9% of MPI-IO write time is spent **outside** `write()` — the actual data copies take about one second in total. The rest has two parts:

1. **Stalls of 30 s (and 60 s = two back-offs).** About 16 times per run all writing stops for ~30 s; all 16 ranks sit inside the collective write meanwhile (≈ 16 events × 16 ranks = the ~253 MPI-IO calls ≥ 29 s). These stalls account for ~90% of the run time. 30 s is the Linux NFSv4 client's maximum back-off when retrying a blocked lock request.
2. **A fixed cost per write.** Even without stalls, consecutive 64 KiB writes are ~3.5 ms apart, against ~0 ms with the lock fix. With 4096 writes per repetition this alone costs ~14 s per repetition, which matches the one stall-free default repetition (15.7 s, 16 MiB/s). This is consistent with a lock and unlock request to the NFS server around every write.

Darshan does not record `fcntl` calls, so it shows where the time goes but not the lock calls themselves. Together with the earlier diagnostics — NFS LOCK operation counters, processes blocked in `wait_woken`, and the stalls disappearing when only the lock setting changes — the evidence points to OMPIO's whole-file lock as the cause. A Recorder trace with `RECORDER_ENABLE_FCNTL_TRACE` on this case would show the lock calls and their durations directly.

Native and container behave the same here too: the same per-write gap (3.5 ms), and a similar number of stalls (16 vs 17). Whether a run hits 16 or 17 stalls is chance, which is why default-locking results swing in both directions between runs.

## 4. With the lock fix, the time moves to close/flush

With algorithm 3 the MPI-IO write calls themselves become cheap (0.001 s on average, 15 s cumulative), but `POSIX_F_META_TIME` rises to ~101 s and `MPIIO_F_META_TIME` to ~115 s (cumulative over 16 ranks and 5 repetitions, i.e. most of each 1.55 s repetition). Without lock round trips, `write()` only copies into the page cache, and the data goes to the server when the file is closed — NFS writes back cached data at `close()` (close-to-open consistency), and Darshan counts `close()` as metadata time. With default locking each unlock already forces the data out, so little is left for `close()`. The data transfer is the same; it just lands in a different call. Identical in native and container (101.4 vs 102.8 s).

## 5. POSIX FPP: one synchronous NFS round trip per write

Every rank writes its own file with `O_DIRECT`, so each 64 KiB `write()` is a synchronous NFS WRITE and takes ~13.75 ms (native 13.75, container 13.76). Write time is 98% of the run (`POSIX_F_WRITE_TIME` 282 s of ~288 rank-seconds). This explains why POSIX FPP bandwidth grows with transfer size in the baseline: the cost is per call, so larger transfers need fewer round trips.

## Conclusions for the thesis

1. **Same I/O, same cost per call** — Darshan shows native and container issue identical POSIX and MPI-IO calls with identical per-call times. The "no overhead" result is explained, not just measured.
2. **The ×18 slowdown is waiting, not writing** — with OMPIO's default whole-file locking on NFS, >99.9% of MPI-IO write time is outside `write()`: ~90% in 30 s lock back-off stalls and the rest in a ~3.5 ms per-write lock round trip. The lock fix removes both.
3. **The bottleneck is the NFS protocol, in both variants** — per-call round trips (POSIX O_DIRECT), lock round trips and stalls (MPI-IO default), or the flush at close (MPI-IO lock fix).
