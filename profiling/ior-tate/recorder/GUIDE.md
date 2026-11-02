# Recorder tracing — IOR intra-node on TATE

## What and why

Darshan (`../darshan/REPORT.md`) showed that with OMPIO's default locking on NFS, more than 99.9% of MPI-IO write time is spent outside `write()`: 16–17 stalls of ~30 s per run plus ~3.5 ms between consecutive 64 KiB writes. Darshan does not record `fcntl()`, so it cannot show the lock calls themselves. Recorder traces every POSIX and MPI-IO call of every rank with start and end time, including `fcntl()`, which turns the lock explanation from indirect into direct evidence.

| # | Case | Reps | What it should show |
|---|---|---|---|
| 1 | MPI-IO shared, 64k, **default locking** | 1 | An `fcntl` lock/unlock pair around every 64 KiB write by the aggregators; the ~30 s waits inside the lock calls |
| 2 | MPI-IO shared, 64k, **lock fix** (`fs_ufs_lock_algorithm 3`) | 1 | Those lock calls gone or rare |

Each case runs native and container back to back: **4 jobs** on tate01. Same flags as the baseline otherwise (16 ranks, `-b 16m -w -m -g -d 5 -c`). One repetition each: a default-locking repetition can take ~8 min, and Recorder logs every call of every rank.

## No separate container image

On ASPIRE 2A, h5bench needed its own Recorder image (`deployment/h5bench/h5bench_benchmarks_recorder.def`) because the host Recorder pulled in Cray MPI, HDF5 and PBS libraries that do not exist in the container. On TATE the host Recorder links only the distro OpenMPI (`libmpi.so.40`, the same as the image), `libz` and its own `libgotcha`, and `ldd` inside the IOR image resolves all of them (checked 2026-11-02, and again at the start of every container job). The container job loads the host build from its own path under `$HOME`, which Apptainer mounts automatically. Native and container are traced by the identical library, and the baseline image stays unchanged.

The Recorder build has `RECORDER_ENABLE_FCNTL_TRACE=ON` (a build-time option, checked in `build/CMakeCache.txt`); POSIX and MPI-IO tracing are on by default at run time, MPI (non-I/O) tracing is off.

## 1. Smoke test (once, ~1 min)

Checks that Recorder catches the `fcntl` calls made inside OpenMPI's I/O component, not only calls made by IOR itself.

```bash
salloc -p teaching -w tate01 -n 4 -t 10        # interactive allocation with 4 slots
R=$HOME/native/recorder/Recorder/install
mkdir -p ~/recorder_smoke && cd ~/recorder_smoke
export OMPI_MCA_pml=ucx UCX_POSIX_USE_PROC_LINK=n
mpirun -np 4 -x UCX_POSIX_USE_PROC_LINK -x LD_PRELOAD=$R/lib/librecorder.so -x RECORDER_TRACES_DIR=$PWD/trace \
  $HOME/native/ior/ior-4.0.0/install/bin/ior -a MPIIO -c -w -t 64k -b 1m -o $PWD/f
$R/bin/recorder2text $PWD/trace > /dev/null
grep -h " fcntl " trace/_text/*.txt | head -5       # expect lock calls with F_SETLKW / F_SETLK
grep -ch " fcntl " trace/_text/*.txt                # per rank; non-zero for the aggregator rank(s)
exit                                                # leave the allocation
rm -rf ~/recorder_smoke
```

If no `fcntl` lines appear, stop and check before running the real jobs.

## 2. Run

Copy `scripts/` to TATE, e.g. `~/experiments/profiling/ior/recorder/`, then from there:

```bash
./submit_intra_recorder.sh           # cases 1-2: 4 jobs on tate01
./submit_intra_recorder.sh 2         # one case only
squeue -u $USER
```

## Output

```
logs/recorder_<variant>_mpiio_shared_t64k_lock<L>_<jobid>.out/.err   job log: environment, ldd check, fcntl count, top calls
<variant>/<case>/ior_<jobid>.txt              IOR result
<variant>/<case>/summary_<jobid>.txt          recorder-summary: call counts per function
<variant>/<case>/trace_<jobid>/               raw Recorder trace
<variant>/<case>/trace_<jobid>/_text/<rank>.txt   recorder2text: one line per call
```

`<case>` is `mpiio_shared_t64k_lockdefault` or `mpiio_shared_t64k_lock3`. Each job fails loudly if no trace is written or `recorder2text` fails, and prints the number of `fcntl` calls, the longest one, and how many lasted ≥ 29 s.

## Reading the text traces

Each line of `_text/<rank>.txt` is one call:

```
<start> <end> <function> <call depth> <type> ( <arguments> )
```

Times are seconds since the start of the run. Call depth 0 is a call made by IOR; depth > 0 is a call made from inside another traced call (for example `fcntl` and `pwrite` inside `MPI_File_write_at_all`).

What to compare between case 1 and case 2, native vs container:
1. **Number of `fcntl` calls per rank** — expect two per aggregator write (lock + unlock) with default locking, near zero with the lock fix.
2. **Duration of `fcntl` calls** — expect a few lasting ~30 s (the NFS client's lock back-off) with default locking; they should line up with the stall times seen in Darshan's DXT trace.
3. **Which ranks lock** — expect the two aggregators (ranks 0 and 8, as in Darshan), the same in native and container.
