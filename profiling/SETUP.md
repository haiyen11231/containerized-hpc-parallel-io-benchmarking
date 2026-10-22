# Darshan + Recorder — setup guide

Everything here is verified against Aspire 2A as it actually is, not against the generic docs. Run these yourself; nothing in this file has been executed.

---

## 0. The thing that will bite you first

**The system module `darshan/3.4.6` is built against cray-mpich, not OpenMPI.**

```
$ ldd /app/apps/darshan/3.4.6/lib/libdarshan.so
    libmpi_cray.so.12 => /opt/cray/pe/lib64/libmpi_cray.so.12
```

Every benchmark in this project runs under `openmpi/4.1.2-hpe`. `LD_PRELOAD`-ing a cray-mpich-linked Darshan into an OpenMPI job pulls two MPI implementations into one process — the same class of ABI mismatch you already hit with `hdf5-…-cmpi` versus `-ompi4`, which produced `MPI_Comm_create_keyval` / `MPI_ERR_ARG`.

So there are two usable paths:

| path | MPI-IO data? | effort |
|---|---|---|
| **A. `DARSHAN_ENABLE_NONMPI=1` + POSIX module only** | ❌ no | minutes |
| **B. build darshan-runtime against `openmpi/4.1.2-hpe`** | ✅ yes | ~30 min |

**Do A first to learn the workflow, then B for the real data.** A is enough to answer H1 (time breakdown) and H2 (call patterns), which is most of the explanatory value. Only MPI-IO collective behavior (H3) needs B.

The system module is still useful for the **analysis** tools (`darshan-parser`, `darshan-job-summary.pl`) — those don't care which MPI produced the log.

---

## 1. Path A — POSIX-only, no build (start here)

```bash
module load libfabric/1.11.0.4.125
module load openmpi/4.1.2-hpe
module load darshan/3.4.6          # for the .so and the parser

mkdir -p ~/scratch/fyp/profiling/darshan-logs

# inside a PBS job, 4 ranks, trivial IOR:
export DARSHAN_ENABLE_NONMPI=1
export DARSHAN_MOD_ENABLE=POSIX        # POSIX only; skip the MPI-IO wrappers
export DARSHAN_LOGFILE=~/scratch/fyp/profiling/darshan-logs/test_native.darshan

mpirun -np 4 \
  -x LD_PRELOAD=$DARSHAN_ROOT/lib/libdarshan.so \
  -x DARSHAN_ENABLE_NONMPI -x DARSHAN_MOD_ENABLE -x DARSHAN_LOGFILE \
  $HOME/scratch/fyp/native/ior/ior-4.0.0/src/ior \
     -a POSIX -t 1m -b 16m -e -o <a path on /scratch>
```

Then read it:

```bash
darshan-parser $DARSHAN_LOGFILE | head -60
```

**Three things that commonly go wrong:**

- `-x VAR` is required for `mpirun` to export the variable to ranks. Setting it in the shell is not enough.
- `DARSHAN_LOGFILE` names an **exact file**, not a directory. With multiple ranks Darshan writes one shared log, so one filename is correct — but if you loop over configurations, change the filename each time or you will overwrite silently.
- If no log appears, Darshan almost certainly never loaded. Check `LD_PRELOAD` reached the ranks and that the binary is dynamically linked (`ldd …/ior` — it is).

**Stop here until `darshan-parser` prints a table.** Everything downstream assumes you can read the output.

---

## 2. Path B — build Darshan against OpenMPI

Your clone is at `~/scratch/fyp/native/darshan/darshan` and has already been configured once (`config.status` exists), so configure it cleanly rather than reusing that state.

```bash
module purge
module load libfabric/1.11.0.4.125
module load openmpi/4.1.2-hpe

cd ~/scratch/fyp/native/darshan/darshan/darshan-runtime

./configure \
    --prefix=$HOME/scratch/fyp/native/darshan/install-ompi \
    --with-log-path=$HOME/scratch/fyp/profiling/darshan-logs \
    --with-jobid-env=PBS_JOBID \
    CC=mpicc

make -j && make install
```

| flag | why |
|---|---|
| `CC=mpicc` | **the whole point** — builds the MPI-IO wrappers against OpenMPI, not cray-mpich |
| `--with-jobid-env=PBS_JOBID` | tags each log with the PBS job id, so logs are traceable back to a run |
| `--with-log-path` | a directory you own; the default system path is not writable by you |

Verify it linked against the right MPI before using it:

```bash
ldd $HOME/scratch/fyp/native/darshan/install-ompi/lib/libdarshan.so | grep -i mpi
#   expect libmpi.so.40 (OpenMPI), NOT libmpi_cray.so.12
```

That one check is the difference between real MPI-IO data and a crash.

Then use the same run recipe as Path A, but point `LD_PRELOAD` at your build and drop `DARSHAN_ENABLE_NONMPI` / `DARSHAN_MOD_ENABLE`.

---

## 3. Container instrumentation

The library must exist **inside** the container namespace and match the **container's** MPI (generic apt OpenMPI, not the host's).

**Try first — bind-mount the host build:**

```bash
apptainer exec \
  --bind $HOME/scratch/fyp/native/darshan/install-ompi:/opt/darshan \
  --bind $HOME/scratch/fyp/profiling:/opt/prof \
  "$SIF" env LD_PRELOAD=/opt/darshan/lib/libdarshan.so \
             DARSHAN_LOGFILE=/opt/prof/darshan-logs/test_container.darshan \
             <binary> …
```

**Expect POSIX to work and MPI-IO to be unreliable.** The POSIX wrappers only need libc, which is ABI-stable across these builds; the MPI-IO wrappers need matching MPI symbols, and the host OpenMPI 4.1.2-hpe is not the container's apt OpenMPI 4.1.2. If it segfaults or silently produces no MPI-IO records, that is the reason — fall back to `DARSHAN_ENABLE_NONMPI=1` + `DARSHAN_MOD_ENABLE=POSIX`, which has no MPI dependency at all.

**The correct fix, if time allows:** add a darshan-runtime build to the container `.def`, compiled with `CC=mpicc` against the container's own OpenMPI, installed to `/opt/darshan`. Then no bind-mount is needed and MPI-IO records are trustworthy.

> One caution from earlier in this project: keep the `.def` `%environment` block free of command substitution. A `$(…)` there runs a process on every container start, and at 256 ranks that exceeded Apptainer's 60 s startup deadline. Plain assignments only.

---

## 4. What to pull out of the logs

```bash
darshan-parser <log> | grep -E 'POSIX_(OPENS|WRITES|READS|SEEKS)\b'
darshan-parser <log> | grep -E 'POSIX_F_(READ|WRITE|META)_TIME'
darshan-parser <log> | grep -E 'POSIX_SIZE_WRITE_'
darshan-parser <log> | grep -E 'POSIX_(FILE|MEM)_ALIGNMENT'
darshan-parser <log> | grep -E 'MPIIO_(COLL|INDEP)_(READS|WRITES)'
```

Mapped onto the hypotheses in `README.md`:

| counters | answers |
|---|---|
| `POSIX_F_*_TIME` | **H1** — is wall-clock dominated by filesystem wait rather than MPI? |
| `POSIX_SIZE_WRITE_*`, `POSIX_WRITES`, `POSIX_OPENS` | **H2** — do container and native issue the *same* calls? |
| `POSIX_*_ALIGNMENT` | **H2** — an alignment difference would be a real finding |
| `MPIIO_COLL_WRITES` vs `MPIIO_INDEP_WRITES` | **H3** — did collective aggregation actually engage? |

`darshan-job-summary.pl <log>` produces a PDF overview — useful for a first look and for thesis figures, but the counters above are what the argument rests on.

---

## 5. Recorder — only after Darshan localises a question

Darshan gives aggregates. Recorder gives the full call-by-call sequence, which is large and slow to analyze, so use it only once you know what you are looking for (most likely H3, the MPI-IO aggregation pattern).

```bash
module load libfabric/1.11.0.4.125 openmpi/4.1.2-hpe cmake
cd ~/scratch/fyp/native/recorder/Recorder

cmake -S . -B build \
      -DCMAKE_INSTALL_PREFIX=$PWD/install \
      -DCMAKE_C_COMPILER=mpicc
cmake --build build -j
cmake --install build
```

**Verify the library name and environment variables against Recorder's own README once it is built — do not assume they mirror Darshan's.** The mechanism is the same (`LD_PRELOAD`), the naming is not.

The same container ABI problem applies, with the same two options: bind-mount and accept POSIX-only, or build inside the image.

---

## 6. Suggested order of work

1. Path A on a trivial 4-rank native IOR job → confirm `darshan-parser` output is readable
2. Path B build → confirm `ldd` shows OpenMPI, not cray-mpich
3. Native IOR, 4 configurations only (POSIX/shared, POSIX/FPP, MPIIO/shared, MPIIO/FPP), 1 node
4. Container, same 4 configurations, bind-mount first and fall back to NONMPI if MPI-IO fails
5. Compare the counters in section 4 → H1, H2, H3
6. Recorder only if a specific question survives

**Instrument a subset, not the suite.** The baseline already has the timings; profiling is for the breakdown. Four configurations at one node count answer all three hypotheses, and re-running 40 under instrumentation would buy nothing.
