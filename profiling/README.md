# Phase 2 — Profiling and root-cause analysis

Darshan and Recorder, applied to explain what the baseline measured.

---

## 1. The question profiling has to answer

The baseline produced a result that looks contradictory until it is explained:

| benchmark | container vs native |
|---|---|
| OSU pt2pt, inter-node | **2–12× slower** |
| OSU collective, Alltoall intra-node | **1.7–4.9× slower** |
| OSU collective, Allreduce intra-node | **~20% faster** |
| IOR — 72 configurations | **no measurable difference** (median 1.01–1.07×) |
| h5bench | **no measurable write penalty** |

The container's MPI stack is demonstrably crippled — no UCX, TCP instead of Slingshot, CMA disabled — yet parallel I/O shows no penalty at all.

**The hypothesis to test is that I/O time is dominated by the filesystem, so the MPI transport never reaches the critical path.** That is plausible but currently unproven: the baseline can only say the difference is below its ~20% noise floor, which is not the same as showing *why*.

Three falsifiable sub-hypotheses:

| | hypothesis | tool that tests it |
|---|---|---|
| **H1** | I/O wall-clock is dominated by filesystem wait, not MPI | **Darshan** — per-job time breakdown |
| **H2** | Container and native issue the *same* I/O calls (same counts, sizes, alignment) | **Darshan** — access-pattern histograms |
| **H3** | MPI-IO collective aggregation behaves differently in the container (aggregator count, message sizes) even though totals match | **Recorder** — call-by-call trace |

H1 and H2 together would explain the null result: same calls, filesystem-bound, so transport is irrelevant. H3 is the interesting failure mode — if aggregation differs but outcomes match, that is worth reporting.

## 2. Tool status on Aspire 2A

| | state | action |
|---|---|---|
| **Darshan 3.4.6** | **module exists**, `/app/apps/darshan/3.4.6/lib/libdarshan.so` | use it — no build needed for native |
| `~/scratch/fyp/native/darshan` | cloned, unbuilt | redundant for native; keep only if a container build is needed |
| **Recorder** | cloned at `~/scratch/fyp/native/recorder/Recorder`, unbuilt | needs CMake build |
| IOR binary | dynamically linked | `LD_PRELOAD` works |

## 3. The hard part: profiling *inside* the container

Both tools work by `LD_PRELOAD`-ing a shared library that intercepts I/O calls. Inside Apptainer the library must be visible in the **container's** filesystem namespace, and it must match the **container's** MPI ABI.

Three options, in order of correctness:

**Option A — bind-mount the host Darshan (fastest to try, likely partial)**

```bash
apptainer exec --bind /app/apps/darshan/3.4.6:/opt/darshan "$SIF" \
  env LD_PRELOAD=/opt/darshan/lib/libdarshan.so "$BIN" ...
```

The host `libdarshan.so` is built against the host OpenMPI 4.1.2-hpe, while the container has a generic apt OpenMPI. **Expect the POSIX wrappers to work and the MPI-IO wrappers to misbehave or crash** — the POSIX layer only needs libc, which is ABI-stable; the MPI-IO layer needs matching MPI symbols. Worth 20 minutes to test, because POSIX-only data already answers H1 and H2.

**Option B — build Darshan inside the container image (correct, costs a rebuild)**

Add to the `.def`: build `darshan-runtime` with `--with-mem-align`, `CC=mpicc` against the container's own OpenMPI. This gives correct MPI-IO wrappers and is the defensible choice for the thesis. Cost is one image rebuild plus a re-verification that the benchmarks still run.

**Option C — POSIX-only, no MPI**

`DARSHAN_ENABLE_NONMPI=1` with the POSIX module only. Loses MPI-IO detail but needs no MPI ABI match at all. Useful fallback.

**Recommendation: try A first; if MPI-IO wrappers fail, fall back to C for the baseline comparison and do B only if time allows.** A and C both answer H1 and H2, which is where the explanatory value is. H3 needs B or Recorder.

## 4. Staged plan

**Stage 0 — validate on a trivial native job.** One IOR run, 4 ranks, small transfer, native, Darshan enabled. Confirm a log appears and `darshan-parser` reads it. Do not attempt anything else until this works; the output format needs to be familiar before it is relied on.

```bash
module load darshan/3.4.6
export DARSHAN_LOGPATH=$HOME/scratch/fyp/profiling/darshan-logs
mkdir -p "$DARSHAN_LOGPATH"
mpirun -np 4 env LD_PRELOAD=$DARSHAN_ROOT/lib/libdarshan.so ior -a POSIX -t 1m -b 16m -e -o <file>
darshan-parser "$DARSHAN_LOGPATH"/*.darshan | head -60
```

**Stage 1 — native IOR, instrumented.** Re-run a *small subset* of the baseline configurations under Darshan. Not all 40 — pick the four that matter:

| config | why |
|---|---|
| POSIX / shared | the slow access model |
| POSIX / FPP | the fast one — 3.5× faster, and the contrast is the known result |
| MPIIO / shared | where MPI-IO stopped scaling past 4 nodes |
| MPIIO / FPP | completes the 2×2 |

**Stage 2 — container, instrumented.** Same four configurations, via Option A/B/C above.

**Stage 3 — compare.** The specific numbers to extract per run:

- `POSIX_F_READ_TIME` / `POSIX_F_WRITE_TIME` / `POSIX_F_META_TIME` — the H1 time breakdown
- `POSIX_SIZE_WRITE_*` histogram buckets — H2, do both issue the same sizes
- `POSIX_WRITES`, `POSIX_OPENS`, `POSIX_SEEKS` — H2, same call counts
- `POSIX_FILE_ALIGNMENT`, `POSIX_MEM_ALIGNMENT` — alignment differences would be a real finding
- `MPIIO_COLL_WRITES` vs `MPIIO_INDEP_WRITES` — whether collective aggregation actually engaged

**Stage 4 — Recorder, only if Darshan leaves a gap.** Darshan gives aggregates; Recorder gives the exact sequence. Use it only to answer a question Darshan has already localized — most likely H3, the aggregation pattern under MPI-IO collective writes. Build:

```bash
cd ~/scratch/fyp/native/recorder/Recorder
cmake -S . -B build -DCMAKE_INSTALL_PREFIX=$PWD/install && cmake --build build -j && cmake --install build
```

Verify the actual `LD_PRELOAD` library name and env vars against Recorder's own README once built — do not assume they match Darshan's.

## 5. Scope discipline

Profiling can expand without limit. Two rules:

**Instrument a subset, not the suite.** Four IOR configurations at one node count is enough to answer H1–H3. Re-running the whole baseline under instrumentation buys nothing — the baseline already has the timings; profiling is for the *breakdown*.

**Darshan first, Recorder only on a specific question.** Darshan is transparent and cheap; Recorder produces a full call trace that is large and slow to analyze. Running Recorder before knowing what to look for wastes the remaining time.

## 6. Expected outcome

If H1 and H2 hold — same call pattern, filesystem-dominated time — then the baseline's null result is **explained rather than merely bounded**, and that sentence is the Phase 2 deliverable:

> *The container's MPI handicap does not surface in parallel I/O because I/O time is dominated by filesystem wait; both variants issue identical POSIX call patterns, and the transport is not on the critical path.*

That, combined with OSU showing the transport cost in isolation, is a complete root-cause story and directly motivates the Phase 3 bind-mount optimization (which should help transport-bound workloads and leave I/O-bound ones unchanged — a falsifiable prediction).



install darshan in hpc:
module purge
module load libfabric/1.11.0.4.125
module load openmpi/4.1.2-hpe

git clone https://github.com/darshan-hpc/darshan.git
cd darshan
autoreconf -i

./configure --with-log-path=/darshan-logs --with-jobid-env=PBS_JOBID CC=mpicc --prefix=$(pwd)/install

make -j 8 install

install Recorder in hpc:
module purge
module load libfabric/1.11.0.4.125
module load intel/2022.0.2
module load hdf5/1.12.1-parallel-icc22-ompi4
module swap openmpi/4.1.7-icc24.2.1 openmpi/4.1.2-hpe
module swap intel/2024.2.1 intel/2022.0.2
git clone https://github.com/uiuc-hpc/Recorder.git
cd Recorder
export RECORDER_INSTALL_PATH=`pwd`/install
git submodule update --init --recursive
mkdir build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=$RECORDER_INSTALL_PATH -DRECORDER_WITH_HDF5=$HDF5_DIR
make && make install

-->  Build files have been written to: /home/users/ntu/haiyen00/scratch/fyp/native/recorder/Recorder/build