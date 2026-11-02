# Recorder tracing results — IOR intra-node on TATE

Four traced runs, 2026-11-02: tate01, 16 ranks, MPI-IO + shared file, `-t 64k -b 16m -w -m -g -d 5 -c -i 1`, native vs container, default locking vs lock fix (`fs_ufs_lock_algorithm 3`). Jobs 213–216. The container loads the same host Recorder build. Plan and method: `GUIDE.md`; Darshan results for the same cases: `../darshan/REPORT.md`.

Files: `results/<variant>/<case>/` (`ior_<jobid>.txt`, `summary_<jobid>.txt` from `recorder-summary`, raw trace `trace_<jobid>/recorder.dat`, one text file per rank in `trace_<jobid>/_text/`, Chrome-format timeline in `trace_<jobid>/_chrome/timeline_0.json`), `results/logs/`. The timelines are also collected as `results/timelines/<variant>_<case>_<jobid>.json`; open them at https://ui.perfetto.dev (one process row per MPI rank). Numbers below come from `analysis/summarize_recorder.py`.

| Case | Jobs (native / container) | IOR write, native | container |
|---|---|---|---|
| Default locking | 213 / 214 | 0.89 MiB/s, 288.6 s | 1.12 MiB/s, 228.1 s |
| Lock fix | 215 / 216 | 165.3 MiB/s, 1.6 s | 159.0 MiB/s, 1.6 s |

## 1. The lock calls, directly

| | Default locking (native / container) | Lock fix (native / container) |
|---|---|---|
| `fcntl(F_SETLKW, F_WRLCK)` on the shared file — lock request, wait if taken | 4097 / 4097 | **0 / 0** |
| `fcntl(F_SETLK, F_UNLCK)` — unlock | 4097 / 4097 | **0 / 0** |
| Ranks that take locks | 0 and 8 / 0 and 8 | none |
| Locks per rank (rank 0, rank 8) | 2176, 1921 / 2176, 1921 | — |
| `MPI_File_write_at_all` calls | 4096 / 4096 | 4096 / 4096 |
| Lock calls lasting ≥ 29 s | yes, up to 30.51 s / up to 30.44 s | none |

With default locking, OMPIO takes an exclusive write lock (`F_WRLCK`) with the blocking call `F_SETLKW` before **every** 64 KiB write and releases it after: one lock/unlock pair per aggregator write (16 ranks × 256 writes = 4096, plus one). Only the two collective-buffering aggregators (ranks 0 and 8, the same ranks that Darshan shows doing the POSIX writes) take locks; the lock calls are made from inside `MPI_File_write_at_all` (call depth 1). With the lock fix there is not a single lock call on the file, because IOR's 64 KiB writes are aligned to the block size and algorithm 3 only locks partial blocks.

Native and container are identical, down to the split of locks between the two aggregators.

## 2. The 30 s waits are inside the lock requests

Some lock requests take 30.4–30.5 s to return — the Linux NFSv4 client's maximum back-off when the server refuses a lock because another process holds it. While an aggregator waits, the whole collective write waits with it, so every rank sees the stall. From the timeline of rank 1, which takes no locks:

| | Stall events (`MPI_File_write_at_all` ≥ 29 s) | Time in stalls | Share of the repetition |
|---|---|---|---|
| Native | 9, each 30.1–30.5 s, back to back | 273 s | 95% of 288.6 s |
| Container | 7, each 30.1–30.4 s, back to back | 212 s | 93% of 228.1 s |

The stalls follow each other almost without a gap: once the aggregators start colliding on the lock, they keep falling into the 30 s back-off. Native and container differ only in how many stalls the run happened to hit (9 vs 7), which is why default-locking bandwidth swings in both directions between runs. With the lock fix there are no stall events.

## 3. Caveats

- **Timing on the aggregator ranks is unreliable.** Ranks 0 and 8 (thousands of `fcntl` records each) contain calls that overlap in time and timestamps that run past the end of the job (e.g. 600 s and 480 s in a 294 s run), which is impossible for a single thread — most likely an artefact of Recorder's timestamp handling. Call **counts** do not depend on timestamps and are reliable; all timings above come from a rank without locks, whose timeline matches the run (last timestamp 294 s = Recorder's own elapsed time). The count of ≥ 29 s lock calls per aggregator is therefore not reported as a number.
- **The aggregators' data writes are not in the Recorder trace.** Recorder lists no `write`/`pwrite` calls for the 64 KiB data (only 3 small `write`s), although Darshan counted 4096 POSIX writes per repetition. OMPIO most likely writes through a call this Recorder build does not intercept (e.g. `pwritev`). The lock calls, which are what this trace is for, are captured; the writes themselves are covered by Darshan.
- `fcntl` arguments show the command and lock type but not the byte range, so the trace does not by itself show that the **whole** file is locked; that follows from how OpenMPI's `fs_ufs_lock_algorithm` default (auto) handles NFS and from the lock fix (range locking) removing every lock call.
- One repetition per run: enough to show the mechanism, not a statistic. Darshan (3 repetitions) and the baseline (30 repetitions) give the numbers.

## Conclusion for the thesis

Recorder shows directly what Darshan could only show indirectly: with OpenMPI's default settings on NFS, every aggregator write is wrapped in a blocking exclusive `fcntl` lock and an unlock, and the 30 s stalls that dominate the run (93–95% of it) are spent waiting inside those lock requests. With `fs_ufs_lock_algorithm 3` no locks are taken and the stalls disappear. The behaviour is identical in native and container: it is a property of OpenMPI's MPI-IO layer on NFS (mechanism #3, interaction with the filesystem), not of containerisation.
