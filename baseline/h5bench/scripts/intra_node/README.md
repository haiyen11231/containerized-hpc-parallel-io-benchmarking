# Intra-node case study — setup and rationale

Single node, 128 ranks. Sweeps the four supported 1-D write access patterns, native vs container.

This file explains **how the experiment is set up and why**. For the measured numbers and their interpretation see `../../results/intra_node/README.md`.

---

## 1. Why a single node

The project asks whether containerization costs parallel-I/O performance, via three named mechanisms: **runtime overhead**, **storage mounting**, and **filesystem interaction**.

Running on one node is deliberate. With all 128 ranks on one machine every MPI message goes through shared memory, so the network is removed from the experiment. That matters because the container's generic OpenMPI has no UCX and
falls back to TCP over Slingshot — the dominant effect in the multi-node studies. Removing it leaves only the HDF5 library and the storage path: **mechanisms #2 and #3, isolated from #1**.

The variable swept is the **shape** of the data, not its size. That is complementary to IOR, which sweeps transfer size. Shape is a question only an HDF5-level benchmark can ask.

## 2. What the benchmark actually models

h5bench's write kernel is **VPIC-IO** — the I/O pattern of VPIC (Vector Particle-In-Cell), a real plasma-physics code from Los Alamos. Production VPIC runs track trillions of particles and dump them every few timesteps, so "every rank writes its slice of particles into a shared HDF5 file, repeatedly" became a reference example of realistic HPC I/O.

From h5bench's own documentation:

> an I/O kernel developed based on a particle physics simulation's I/O pattern (**VPIC-IO** for writing data in a HDF5 file) and on a big data clustering algorithm (**BDCATS-IO** for reading the HDF5 file VPIC-IO wrote)

So `h5bench_write` = VPIC-IO (simulation writing dumps) and `h5bench_read` = BDCATS-IO (analysis reading them back) — a real producer→consumer workflow, not two unrelated microbenchmarks.

This is why h5bench earns its place alongside IOR: **IOR writes meaningless bytes to measure raw bandwidth; h5bench reproduces the I/O shape of an actual scientific application.** It also explains the 32 bytes/particle — that is one VPIC particle record (7 floats + 1 int: position, momentum, IDs).

## 3. What the two patterns mean

`MEM_PATTERN` — how data sits **in RAM** before writing:

```
CONTIG  (Structure of Arrays)        INTERLEAVED  (Array of Structures)
  x: [x0][x1][x2]…                     [x0 y0 z0 px0 py0 pz0 id0]
  y: [y0][y1][y2]…                     [x1 y1 z1 px1 py1 pz1 id1]
  …  7 separate arrays                 …  one array of 32-byte structs
```

`FILE_PATTERN` — how it is stored **in the HDF5 file**:

```
CONTIG                               INTERLEAVED
  /x, /y, /z …                         /particles → ONE dataset whose
  one dataset per field                element type is a COMPOUND type
```

The interesting cases are the **mismatches**. When the layouts agree HDF5 streams bytes through; when they disagree it must transpose in userspace before any syscall happens:

| MEM → FILE | What HDF5 must do | Stresses |
|---|---|---|
| CONTIG → CONTIG | nothing; each array maps onto its dataset | baseline: large sequential writes |
| CONTIG → INTERLEAVED | **gather** — pull from 7 arrays, pack 32-byte records | type conversion, memory packing |
| INTERLEAVED → CONTIG | **scatter** — strided reads through the struct array | strided access, poor cache behaviour |
| INTERLEAVED → INTERLEAVED | nothing, but elements are 32-byte compounds | compound-datatype path |

### Why this is the right test

Below the kernel boundary, native and container are **identical** — the same host Lustre client services every `write()`. They differ only above it: HDF5 1.12.1/icc vs 1.10.7/gcc, and different MPI/ROMIO builds.

So this sweep is a dial controlling **how much work happens in the layer where they actually differ**. That yields a falsifiable prediction:

> If the gap is small for CONTIG/CONTIG and grows for the mismatched patterns, the overhead lives in the userspace library stack. If the gap is roughly constant across all four, it is a fixed per-run cost (container startup, library loading) rather than a data-path difference.

Either outcome is a real result.

## 4. Why write-only

The read kernel supports only `CONTIG`/`CONTIG` with `READ_OPTION=FULL` in parallel — an interleaved file cannot be read back. (`PRL`, `RDC`, `LDC`, `CS` are documented as single-process: only rank 0 reads and every other rank skips,
which would silently serialise the measurement.) Reads are covered in the weak/strong-scaling studies.

## 5. Files

| File | Role |
|---|---|
| `h5bench_config.json.template` | h5bench JSON with `@TOKEN@` placeholders |
| `h5bench_native_intra.pbs` | one job = one (MEM, FILE) combo, native |
| `h5bench_container_intra.pbs` | same combo through Apptainer |
| `submit_*_intra_job.sh` | submits all 4 combos |
| `logs/` | PBS job output, one `.out` per job |

## 6. PBS directives, line by line

```bash
#PBS -l select=1:ncpus=128:mpiprocs=128:mem=64gb
```
One chunk, one physical node. 128 ncpus is a **full** Aspire 2A CPU node (2× AMD EPYC 7713, 128 physical cores). `mpiprocs=128` places 128 MPI ranks there. `mem=64gb` is generous — actual use is ~4 GiB — but costs nothing and avoids an OOM kill.

```bash
#PBS -l place=excl
```
Exclusive node access. Aspire 2A is `sharing=default_shared`, so without this another user's job could land on the same node and contaminate the measurement with noisy-neighbour I/O. Non-negotiable for a benchmark.

```bash
#PBS -l walltime=02:30:00
```
**Not about runtime** — jobs finish in 4–21 minutes. It controls **queue routing**. PBS routes on ncpus *and* walltime:

| queue | ncpus | walltime | 1-node job? |
|---|---|---|---|
| `q4` | =128 | **> 02:00:01** | ✓ 25 concurrent per user |
| `q5` | ≥129 | any | ✗ 128 is one short |
| `qdev` | ≤128 | ≤ 2 h | ✓ but capped at 256 ncpus **cluster-wide** |

At ≤2 h a 128-core job falls into `qdev`, where one job takes half the cluster-wide cap and only two can run at once. Measured directly: the same jobs queued for hours at `00:30:00` and started immediately at `02:30:00`.

```bash
#PBS -j oe
```
Merge stderr into stdout so one `.out` file holds the whole story.

## 7. MPI flags

**Native:**
```bash
-np 128 --map-by ppr:128:node --bind-to core
--mca btl ^openib --mca pml ucx
--mca orte_base_help_aggregate 0
--mca opal_common_ucx_opal_mem_hooks 1
-x UCX_LOG_LEVEL=ERROR
```

| flag | meaning and purpose |
|---|---|
| `--map-by ppr:128:node` | **p**rocesses **p**er **r**esource — exactly 128 ranks per node. Without it OpenMPI may distribute differently and the rank-to-node mapping stops being comparable between runs. |
| `--bind-to core` | pin each rank to a core. Unpinned ranks migrate between NUMA domains mid-run, adding variance unrelated to I/O. |
| `--mca pml ucx` | use the UCX point-to-point layer — the Slingshot-native path. **This is what the container cannot do.** |
| `--mca btl ^openib` | disable the obsolete InfiniBand BTL (`^` = exclude), which otherwise warns and is probed pointlessly. |
| `--mca opal_common_ucx_opal_mem_hooks 1` | let UCX install memory hooks so registered-memory caching stays correct. |
| `-x UCX_LOG_LEVEL=ERROR` | suppress UCX info chatter. `-x` exports the variable to every rank. |
| `--mca orte_base_help_aggregate 0` | show every rank's error instead of one aggregated message — essential when debugging a 128-rank failure. |

**Container** differs in exactly two ways:
```bash
--mca btl vader,self --mca btl_vader_single_copy_mechanism none
… apptainer exec --bind /scratch ${SIF}
```

| flag | meaning and purpose |
|---|---|
| `--mca btl vader,self` | the container's apt OpenMPI has **no UCX**, so `pml ucx` is unavailable. `vader` is shared memory, `self` is loopback — sufficient on one node. |
| `btl_vader_single_copy_mechanism none` | Apptainer's user-namespace isolation breaks OpenMPI's CMA single-copy path. Without this, intra-node transfers fail or fall back unpredictably. Confirmed empirically during OSU container debugging. |
| `apptainer exec --bind /scratch` | enter the container per rank, with Lustre visible inside. `--bind` makes the host's already-mounted `/scratch` appear in the container's mount namespace. |

## 8. Why the h5bench driver runs natively even for the container

`h5bench` is a single-process Python orchestrator. It builds an `mpirun` command string and shells out (`src/h5bench.py:409`) — **it never joins MPI**.

Running it *inside* the container would make the container's mpirun the launcher. That build has no PBS `tm` support, so it cannot spawn ranks on other nodes — fatal for the multi-node studies, and inconsistent if used only here.

So the driver stays on the host and containerization happens **per rank**:

```
native    : host mpirun → h5bench_write                      (host libs)
container : host mpirun → apptainer exec → h5bench_write     (container libs)
              ↑ identical launcher; only the libraries differ
```

That isolates **one** variable. Running the driver inside the container would
change the launcher *and* the libraries — two variables at once.

Two details make it work:
- `mpi.configuration` **replaces** the `ranks` property entirely (`src/h5bench.py:257`), so `-np` must be given explicitly.
- `-p <prefix>` is concatenated with **no** `os.path.isfile()` check (`src/h5bench.py:402`; the check only runs in the no-prefix branch), so a binary path existing only inside the `.sif` is accepted.

This also matches the IOR and OSU container scripts, which already use host `mpirun` + `apptainer exec` — including intra-node — so cross-benchmark statements in the thesis stay valid.

## 9. Workload parameters

Fixed in `h5bench_config.json.template`:

| Key | Value | Why |
|---|---|---|
| `NUM_DIMS` / `DIM_2` / `DIM_3` | 1 / 1 / 1 | 1-D; unused dims **must** be 1 |
| `DIM_1` | `"1 M"` | per-rank particles — **the only working size knob** |
| `TIMESTEPS` | 5 | repeated dumps, as a time-stepped simulation does |
| `EMULATED_COMPUTE_TIME_PER_TIMESTEP` | `"0 s"` | measure pure I/O, no simulated compute |
| `MODE` | `SYNC` | no async VOL connector is built |
| `COLLECTIVE_DATA` / `_METADATA` | `NO` / `NO` | independent I/O; collectives are their own case study |
| stripe | `-c 4 -S 1m` | pinned explicitly (§10) |

**`DIM_1` is the only size knob that works.** h5bench parses `NUM_PARTICLES` then overwrites `num_particles` with `DIM_1 × DIM_2 × DIM_3` (`commons/h5bench_util.c:1170`). Setting `NUM_PARTICLES` alone silently yields **1 particle per rank** — an early run wrote 256 bytes instead of 20 GiB and still reported a plausible-looking bandwidth.

**The space in `"1 M"` is mandatory.** `parse_unit()` does `strtok(str, " ")` — it splits on whitespace and reads the unit as a separate token. `"1M"` without the space parses as a literal **1**. `M_VAL` is `((unsigned long long)1024*1024)`, so `"1 M"` is exactly 1048576.

**Volume** — a particle is 7 floats + 1 int = **32 bytes** (verified: 4 ranks × 2 timesteps × 1 particle produced exactly `Total write size: 256.000 B`):

```
128 ranks × 5 timesteps × 1 048 576 × 32 B = 20 GiB per repetition
                                           = 200 GiB per job at REPS=10
```

## 10. Lustre striping

```bash
lfs setstripe -c 4 -S 1m "$PAYLOAD_DIR"
lfs getstripe "$PAYLOAD_DIR"      # verify, don't assume
```

`-c 4` spreads each file across 4 OSTs; `-S 1m` sets the stripe unit. Without pinning, a directory inherits whatever default is current — not guaranteed stable, so native and container could silently be measured on different layouts.

The JSON's `file-system.lustre` block asks h5bench to do this itself and would work (the driver runs natively in both cases), but it is set **again** in the script as a cheap guard, and `lfs getstripe` prints what was actually applied so the log carries proof rather than an assumption.

## 11. Repetitions vs timesteps

`REPS=10`, matching IOR's `-i 10` so confidence intervals across both benchmarks come from the same sample size.

Each repetition is a **separate driver invocation** writing a fresh file (the `.h5` is deleted between reps), not 10 entries in one `benchmarks` array. That keeps repetitions as close to independent as practical — a warm cache cannot carry across them — which is what a confidence interval assumes.

The two are different things:
- **`TIMESTEPS=5`** is *inside* one measurement — part of the workload. h5bench reports one aggregate figure covering all five.
- **`REPS=10`** *wraps* the measurement — 10 independent samples for statistics.

## 12. Guards built into the scripts

| Guard | Catches |
|---|---|
| `: "${MEM_PATTERN:?…}"` etc. | job submitted without required variables |
| `ACTUAL_NODES -ne NODE_COUNT` | PBS granting a different allocation than requested |
| `python3 -m json.tool` | malformed generated JSON, before compute is spent |
| `grep -q '@[A-Z_]*@'` | an unsubstituted placeholder — h5bench would otherwise treat `@MEM_PATTERN@` as a pattern name and produce garbage |
| `apptainer exec … test -x` | the `-p` path missing inside the image |
| post-run `grep "apptainer exec .*h5bench_write"` | the driver silently falling back to the **native** binary if `-p` were dropped |
| `trap 'rm -f …' EXIT` | stranded payload on Lustre after a failure |

## 13. Output layout, and why nothing collides

```
logs/<jobname>.out                                  PBS job output
<variant>/<combo>/config_repN.json                  exact config used
<variant>/<combo>/driver_repN.log                   driver output
payload/<variant>/<combo>/<uuid>-<jobid>/
    ├── write_repN.csv                              ← the measurement
    ├── stdout / stderr
    └── h5bench.cfg                                 what the binary received
```

Every path carries the **variant** and the **combo**, so the 8 jobs in a run write to disjoint trees — verified: no payload directory contains more than one job ID, and no output path lacks its variant name.

The driver rewrites `CSV_FILE` to `<directory>/<uuid>/<csv>`
(`src/h5bench.py:370`), which is why results live under `payload/` rather than the report directory. UUIDs are random and carry no ordering, so the repetition index survives only in the **filename** (`write_rep3.csv`).

**On a rerun:** `config_repN.json` and `logs/*.out` are *overwritten*, while payload UUID directories *accumulate*. Accumulation is the dangerous one — nothing errors, but the analysis glob would see 20 CSVs and report `n=20`, averaging two runs. **Wipe `payload/`, `native/`, `container/` and `logs/*.out`
before resubmitting**, after copying anything worth keeping.

Measurement data itself can never be overwritten: a CSV path contains both a random UUID and the unique job ID, so no two runs can target the same file.

## 14. Running it

```bash
./submit_native_intra_job.sh          # 4 jobs
./submit_container_intra_job.sh       # 4 jobs
REPS=1 ./submit_native_intra_job.sh   # quick smoke test
```
