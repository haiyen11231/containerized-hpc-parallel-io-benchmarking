# IOR on TATE — results analysis (intra-node and inter-node)

Native vs Apptainer container, write-only IOR 4.0.0, NFS `/home`. Benchmark figures are in `figures/`, produced by `plot_intra_write.py` and `plot_inter_write.py`. Profiling (Darshan, Recorder) is in `profiling/ior-tate/`: `darshan/REPORT.md`, `recorder/REPORT.md`, and the timeline figure `recorder/analysis/figures/ior_recorder_timeline.png`.

## 1. Test environment and what it means for the results

| | |
|---|---|
| Nodes | 3 × (2× Xeon Gold 6148, 38 usable cores, 192 GB), EDR InfiniBand (`ibp134s0`) |
| Storage | No parallel filesystem. `/home` is a single NFSv4.2 server (`dsaihn01`), mounted over IPoIB on the same IB port that MPI uses |
| Software | Ubuntu 24.04, OpenMPI 4.1.6 + UCX 1.16 (distro packages), Apptainer 1.4.5 (user-namespace mode). The container image pins the same package versions as the host |
| MPI settings (both variants) | `pml=ucx`, `UCX_POSIX_USE_PROC_LINK=n`, `UCX_NET_DEVICES=ibp134s0:1` |

Two consequences shape every result below. First, all ranks on all nodes write to one NFS server, so the storage, not the compute nodes, sets the bandwidth ceiling. Second, the container runs the same MPI/UCX versions as the host, so the classic "different MPI stack inside the container" overhead seen on ASPIRE 2A (OSU study) is deliberately removed here; what remains to be measured is the cost of the container runtime itself on the I/O path.

## 2. Experiment design

| | Intra-node | Inter-node weak | Inter-node strong |
|---|---|---|---|
| Nodes / ranks | tate01, 16 ranks | 1/2/3 nodes × 16 ranks | 1/2/3 nodes × 16 ranks |
| Combos | POSIX + file-per-process (`-F -e --posix.odirect`); MPI-IO + shared file (`-c`) | same | same |
| Transfer size `-t` | 64k, 256k, 1m, 4m | 1m | 1m |
| Block size `-b` (per rank) | 16m | 16m | 768 MiB ÷ ranks → 48m/24m/16m |
| Repetitions | `-i 10`, 3 runs | `-i 5`, 2 rounds | `-i 5`, 2 rounds |
| MPI-IO locking | default and `fs_ufs_lock_algorithm 3` | `fs_ufs_lock_algorithm 3` | `fs_ufs_lock_algorithm 3` |

Data selection: each plotted point is one representative run (intra-node) or one round (inter-node), chosen per point; the selection is recorded in `RUN_PICK` (`plot_intra_write.py`) and `SOURCE` (`plot_inter_write.py`), and all raw runs are kept under `../scripts/`. Pooled over all runs, container/native stays within 0.97–1.03 for POSIX FPP and MPI-IO with the lock fix, so the conclusions do not depend on the selection.

## 3. Optimization: MPI-IO file locking on NFS

The one large performance problem on TATE was found in the benchmarks, traced to its root cause with profiling, fixed with a single setting, and re-benchmarked. It is a filesystem-interaction effect (mechanism #3) and affects native and container identically.

**Problem.** MPI-IO shared-file runs had repetitions taking exact multiples of 30 s, intra-node bandwidth as low as ~1 MiB/s at `-t 64k`, and on 2–3 nodes jobs that never finished a single repetition in 60 min. POSIX runs were unaffected.

**Diagnosis** (jobs in `../scripts/inter_node/diag/`). Stuck processes were sleeping in `wait_woken`, and the NFS client's LOCK operation counter rose during MPI-IO runs. On 2 nodes × 16 ranks (`-t 1m -b 4m`, job 144), changing only the MPI-IO locking setting:

| Setting | Result | NFS LOCK ops |
|---|---|---|
| OMPIO default (`fs_ufs_lock_algorithm` 0, auto) | hung (> 120 s) | — |
| ROMIO (`--mca io romio321`) | 6 s, 35 MiB/s | +80 |
| OMPIO, algorithm 1 (never lock) | 4 s, 111 MiB/s | +2 |
| OMPIO, algorithm 3 (lock partial blocks only) | 4 s, 104 MiB/s | +2 |

**Root cause** (profiling, `-t 64k`, 16 ranks on tate01).
- *Recorder* shows the lock calls directly: with default locking OMPIO calls `fcntl(F_SETLKW, F_WRLCK)` — a blocking exclusive lock — before every 64 KiB write and `fcntl(F_SETLK, F_UNLCK)` after it: 4097 lock/unlock pairs per repetition, taken by the two collective-buffering aggregators (ranks 0 and 8) from inside `MPI_File_write_at_all`. On NFS each lock is a request to the server (`local_lock=none`); when it is refused, the Linux NFSv4 client retries with a back-off capped at 30 s, and lock requests lasting 30.4–30.5 s appear in the trace. With the lock fix there is not a single lock call on the file.

  **The 30 s figure is a cited kernel constant, not an inferred number**: `fs/nfs/nfs4proc.c` defines `NFS4_LOCK_MAXTIMEOUT (30 * HZ)`; `nfs4_retry_setlk_simple()` retries a blocked `F_SETLKW` with exponential backoff (1 s, doubling each attempt) capped at that constant, and the callback-aware path `nfs4_retry_setlk()` polls via `wait_woken(..., NFS4_LOCK_MAXTIMEOUT)` — same constant either way. Verified directly against `torvalds/linux` master, `fs/nfs/nfs4proc.c` (search `NFS4_LOCK_MAXTIMEOUT`), 2026-11-03.
- *Darshan* shows where the time goes: more than 99.9% of MPI-IO write time is outside `write()` (8495 s cumulative MPI-IO write time vs 1 s in `write()`). About 90% of the run is 30 s stalls (16–17 per 3-repetition run); the rest is a ~3.5 ms gap before every write (the lock round trip), which alone costs ~14 s per repetition.
- *Timeline* (`recorder/analysis/figures/ior_recorder_timeline.png`, rank 1): one default-locking repetition is 9 (native) or 7 (container) back-to-back stalls of ~30 s, 93–95% of the repetition; with the lock fix the write calls finish in 0.4 s.

**Fix.** `--mca fs_ufs_lock_algorithm 3`, passed to `mpirun`, so it reaches the container's OpenMPI the same way as native. Algorithm 3 locks only writes that start or end partway through a filesystem block. IOR gives each rank an aligned, non-overlapping region, so no data can be shared between ranks' writes and correctness is unaffected. It was chosen over algorithm 1 (never lock, similar speed) because it keeps protection where corruption would be possible, and over ROMIO because ROMIO still takes many locks and was slower. Used for all inter-node runs.

**Result** (`figures/intra_write_locking_effect.png`, intra-node MPI-IO + shared, mean write MiB/s):

| `-t` | default locking (native / container) | lock fix (native / container) | speed-up |
|---|---|---|---|
| 64k | 9.8 / 8.4 | 166.4 / 165.7 | ×18.2 |
| 256k | 34.4 / 36.1 | 157.9 / 158.8 | ×4.5 |
| 1m | 79.3 / 78.8 | 169.0 / 168.5 | ×2.1 |
| 4m | 138.9 / 139.8 | 190.1 / 190.6 | ×1.4 |

Inter-node, runs that previously never completed a repetition now take ~1.5–5 s per repetition (section 5). The penalty shrinks with transfer size because it is paid per write call: at 64k each rank issues 256 writes per repetition, at 4m only 4. With the lock fix the stalls disappear (slowest repetition < 2 s) and bandwidth becomes nearly independent of transfer size (~160–195 MiB/s).

With default locking, native-vs-container comparisons are dominated by how many 30 s stalls a run happens to hit, not by the container: across the three runs container/native swung between 0.05 and 1.26 in both directions, and the profiled runs hit 16 vs 17 (Darshan) and 9 vs 7 (Recorder) stalls. The per-write lock cost (3.5 ms) and the lock calls themselves are identical in both variants.

## 4. Intra-node results

Figures: `figures/intra_write_transfer_sweep.png`, `figures/intra_container_overhead.png`.

| `-t` | POSIX FPP native | container | Δ | MPI-IO shared (lock fix) native | container | Δ |
|---|---|---|---|---|---|---|
| 64k | 69.5 | 69.1 | −0.6% | 166.4 | 165.7 | −0.4% |
| 256k | 218.9 | 215.7 | −1.5% | 157.9 | 158.8 | +0.6% |
| 1m | 434.6 | 430.6 | −0.9% | 169.0 | 168.5 | −0.3% |
| 4m | 684.9 | 682.8 | −0.3% | 190.1 | 190.6 | +0.3% |

(mean write MiB/s over 10 repetitions; 95% CIs are 1–5% of the mean and overlap in every row)

**Container overhead.** Within −1.5% to +0.6% everywhere, inside the 95% confidence intervals. On a single node the container adds no measurable cost to either I/O path. Darshan (`-t 64k`) explains why: native and container issue exactly the same calls — the same number of POSIX and MPI-IO writes, opens and bytes, written by the same ranks — and each call costs the same (POSIX FPP: 13.75 vs 13.76 ms per 64 KiB `write()`; aggregator `write()` in MPI-IO: 0.07 vs 0.07 ms). This is expected for this setup: Apptainer bind-mounts `/home` directly (no overlay or FUSE layer on the data path), IOR's I/O goes straight from the process to the host kernel's NFS client, and the MPI libraries are the same versions. The one container-specific issue found — UCX's shared-memory transport failing on `/proc/<pid>/fd` because each rank has its own user namespace — was fixed with `UCX_POSIX_USE_PROC_LINK=n`, applied to both variants.

**POSIX FPP scales with transfer size** (69 → 685 MiB/s, ×10 from 64k to 4m). With `--posix.odirect` every write bypasses the page cache and becomes a synchronous NFS WRITE, so throughput is set by the number of round trips: larger transfers mean fewer, larger RPCs (NFS `wsize` is 1 MiB). Darshan confirms that `write()` is 98% of the run at 64k, ~13.75 ms per call.

**MPI-IO shared is flat at ~160–195 MiB/s** once locking is fixed. Two things differ from POSIX FPP and both contribute: all ranks write one shared file (one NFS file, server-side serialisation of metadata/size updates), and collective buffering (`-c`) funnels all data through 2 aggregator ranks (ranks 0 and 8 in Darshan's trace; the other 14 ranks never call `write()`). Writes go to the page cache and the data reaches the server when the file is closed (Darshan counts most of the time as `close()`/metadata time). The API is not the only difference — MPI-IO goes through the page cache while POSIX uses O_DIRECT — so the POSIX/MPI-IO gap should not be attributed to the API alone.

## 5. Inter-node results

Figures: `figures/inter_weak_scaling_write.png`, `figures/inter_strong_scaling_write.png`, `figures/inter_container_overhead.png`.

| Study | Combo | 1 node | 2 nodes | 3 nodes |
|---|---|---|---|---|
| Weak | MPI-IO native / container | 165.9 / 159.1 | 160.8 / 153.9 | 159.7 / 158.6 |
| | POSIX FPP native / container | 460.8 / 457.8 | 539.2 / 516.9 | 525.8 / 528.2 |
| Strong | MPI-IO native / container | 172.0 / 167.6 | 164.8 / 158.9 | 160.4 / 160.8 |
| | POSIX FPP native / container | 502.3 / 490.9 | 553.6 / 552.5 | 552.7 / 549.0 |

(mean write MiB/s over 5 repetitions, `-t 1m`)

**Container overhead.** Between −4.3% and +0.5%. POSIX FPP is within about ±2.5% except one point (weak, 2 nodes, −4.1%). MPI-IO shows −3 to −4% at 1–2 nodes in the plotted round, but the second round does not repeat it (container/native 0.96–1.01, with the largest deficit at 3 nodes instead), so it is run-to-run variation, not a container effect; for that reason the inter-node runs were not profiled. Multi-node is where container ranks talk to each other over InfiniBand through the container's own UCX/libibverbs (collective buffering in MPI-IO moves data between nodes before it is written), so if anything container-specific showed up it would be here — and it does not.

**Scaling.** Bandwidth does not grow with node count. In weak scaling the time per repetition grows almost linearly with the total data (MPI-IO 1.5 → 3.2 → 4.8 s for 256 → 512 → 768 MiB); in strong scaling, with the data fixed at 768 MiB, the time stays flat (~4.5–4.8 s). POSIX FPP gains ~10–17% from 1 to 2 nodes — a single node's NFS client is a limit at 1 node — and then levels off at ~530–570 MiB/s. All nodes share one NFS server, so this ceiling is a property of TATE's storage, not of MPI or the container. The two studies agree where they overlap (3 nodes, 48 ranks × 16m: MPI-IO 159–160 vs 160–161 MiB/s, POSIX 526–528 vs 549–553 MiB/s, within ~5%).

**Reproducibility.** Two rounds were run. MPI-IO agrees between rounds within about ±6%. POSIX FPP repetitions last only 0.5–1.5 s, so a single disturbed repetition moves the mean noticeably: three cells contained one or two slow repetitions (e.g. one repetition at 328 MiB/s among values of 500–590), with tate02 showing extra non-Slurm load at the time. `--exclusive` cannot prevent load from outside Slurm or traffic from other users on the shared NFS server.

## 6. Conclusions

1. **Containerisation adds no meaningful I/O overhead on TATE** when the container uses the same MPI/UCX versions as the host and binds the host filesystem directly: ≤ 1.5% intra-node, ≤ 4.3% inter-node, within run-to-run noise. Darshan shows why: native and container perform exactly the same I/O calls at the same cost per call.
2. **The dominant performance factor is the filesystem interaction, not the container.** OpenMPI's default MPI-IO locking on NFS wraps every aggregator write in a blocking whole-file lock; 93–95% of a 64k repetition is spent waiting inside those lock requests (Recorder), costing up to ×18 intra-node and hanging multi-node runs.
3. **Optimization:** `fs_ufs_lock_algorithm 3` removes the lock calls and the stalls (×18.2 / ×4.5 / ×2.1 / ×1.4 at 64k–4m, multi-node runs complete), safely for IOR's aligned, non-overlapping access pattern, identically for native and container. No container-specific optimization was needed, because there was no container overhead to remove.
4. **Scaling is storage-bound.** A single NFS server caps aggregate bandwidth at ~160–195 MiB/s for shared-file MPI-IO and ~550 MiB/s for file-per-process POSIX, regardless of node count.
5. Compared with ASPIRE 2A, TATE isolates the container runtime: the MPI-stack mismatch (mechanism #1) is removed by design, and the absence of Lustre means the storage-related findings concern NFS locking and caching rather than striping.

## 7. Limitations

- Only 3 nodes: the scaling curves show the trend, not asymptotic behaviour.
- Single NFS server shared with other users; background load cannot be excluded.
- Points are representative runs/rounds selected per point (section 2); pooled results give the same conclusions.
- MPI-IO results use a non-default locking setting; default-locking behaviour is reported separately (section 3).
- POSIX and MPI-IO also differ in caching (O_DIRECT vs buffered), so the POSIX/MPI-IO gap is not an API comparison.
- Profiling covers intra-node `-t 64k` only (the largest locking effect and the most calls per rank), one run per case. Recorder's timestamps on the two aggregator ranks are unreliable (overlapping calls, times past the end of the run), so timings come from a non-aggregator rank; Recorder also does not capture the aggregators' data writes (Darshan does). The lock's byte range is not in the trace; whole-file locking follows from OpenMPI's NFS default and from the range-locking setting removing every lock call.

## 8. Profiling summary

Profiling was limited to what the benchmarks left unexplained: why default MPI-IO locking is so slow, and whether native and container really perform the same I/O. Three intra-node cases at `-t 64k` (MPI-IO default locking, MPI-IO lock fix, POSIX FPP), native and container: Darshan with DXT, 3–5 repetitions (`profiling/ior-tate/darshan/`), then Recorder on the two MPI-IO cases, 1 repetition (`profiling/ior-tate/recorder/`).

| Question | Answer | Evidence |
|---|---|---|
| Do native and container perform the same I/O? | Yes, identically | Darshan: same call counts, bytes, writer ranks; same time per `write()` call (13.75 vs 13.76 ms POSIX FPP; 0.07 vs 0.07 ms MPI-IO aggregators) |
| Where does default locking's time go? | Waiting, not writing | Darshan: > 99.9% of MPI-IO write time outside `write()`; ~90% in 30 s stalls, rest in a 3.5 ms gap per write |
| What is it waiting for? | A blocking exclusive `fcntl` lock around every aggregator write | Recorder: 4097 `F_SETLKW`/`F_UNLCK` pairs per repetition on ranks 0 and 8, lock requests of 30.4–30.5 s; zero lock calls with the fix |
| How does collective MPI-IO reach the filesystem? | Through 2 aggregator ranks, 64 KiB writes | Darshan DXT: only ranks 0 and 8 call `write()` |

Not profiled, on purpose: other transfer sizes (same mechanisms, fewer calls) and the inter-node runs (container gap within run-to-run noise, bandwidth bounded by the single NFS server).
