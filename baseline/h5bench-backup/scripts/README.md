# h5bench — baseline experiments, overview

Four studies comparing native against an Apptainer container, writing HDF5 to Lustre on Aspire 2A. This file is the overview: what each study varies, every parameter and why it has that value. Per-study detail is in the subdirectory READMEs.

```
intra_node/                      access-pattern sweep, 128 ranks on one node
inter_node/weak_scaling/         node-count scaling, per-rank work fixed
inter_node/strong_scaling/       node-count scaling, total work fixed
inter_node/collective_io/        2x2 factorial on the two HDF5 collective switches
inter_node/cold_read_validation/ methodology check: are reads cache-inflated?
simple_test/                     early validation
```

h5bench's role in the project: **a realistic application-shaped I/O pattern**. IOR issues synthetic block writes; h5bench writes particle data through HDF5 → MPI-IO → POSIX, which is how a real simulation actually reaches Lustre.

---

## 1. The four studies at a glance

| | intra-node | weak scaling | strong scaling | collective I/O |
|---|---|---|---|---|
| **scale** | 1 node, 128 ranks | 1/2/4/8 nodes | same | 2 nodes, 256 ranks |
| **scaling variable** | — (fixed) | node count | node count | — (fixed) |
| **sweeps** | MEM × FILE pattern | — | — | COLLECTIVE_DATA × METADATA |
| **held fixed** | 128 ranks | **DIM_1 = 1 M/rank** | **total = 128 M particles** | 256 ranks, CONTIG/CONTIG |
| **jobs per variant** | 4 | 4 | 4 | 4 |

Every configuration repeated **10 times** (`REPS=10`), each run a separate job invocation producing its own CSV.

## 2. How h5bench is configured — a JSON file, not CLI flags

This is the main structural difference from IOR and OSU. h5bench is driven by a **JSON config** passed to a Python driver:

```bash
h5bench -a -d config.json
```

The scripts generate that JSON per run from `*.json.template` by substituting `@TOKEN@` placeholders.

```json
{
  "mpi":         { "command": "mpirun", "configuration": "@MPI_CONFIG@" },
  "vol":         {},
  "file-system": { "lustre": { "stripe-count": "4", "stripe-size": "1M" } },
  "directory":   "@DIRECTORY@",
  "benchmarks": [{
    "benchmark": "write",
    "file": "@DATA_FILE@",
    "configuration": {
      "MEM_PATTERN": "@MEM_PATTERN@",   "FILE_PATTERN": "@FILE_PATTERN@",
      "NUM_DIMS": "1",
      "DIM_1": "1 M", "DIM_2": "1", "DIM_3": "1",
      "TIMESTEPS": "5",
      "EMULATED_COMPUTE_TIME_PER_TIMESTEP": "0 s",
      "MODE": "SYNC",
      "COLLECTIVE_DATA": "NO", "COLLECTIVE_METADATA": "NO",
      "CSV_FILE": "@CSV_FILE@"
    }
  }]
}
```

### Every parameter, and why

| key | value | why |
|---|---|---|
| `MEM_PATTERN` | `CONTIG` / `INTERLEAVED` | how particle data is laid out **in memory** |
| `FILE_PATTERN` | `CONTIG` / `INTERLEAVED` | how it is laid out **in the HDF5 file** |
| `NUM_DIMS` | `1` | 1-D particle array — the VPIC-style pattern |
| **`DIM_1`** | `"1 M"` (weak) / computed (strong) | **particles per rank.** 1 M × 32 B = **32 MiB per rank per timestep** |
| `DIM_2`, `DIM_3` | `1` | unused in 1-D, but must be present — see the trap below |
| `TIMESTEPS` | `5` | 5 write phases per run, as a simulation would |
| `EMULATED_COMPUTE_TIME` | `0 s` | no artificial compute — this is an I/O benchmark |
| `MODE` | `SYNC` | synchronous I/O; async would measure a different thing |
| `COLLECTIVE_DATA` | `NO` (except collective study) | route bulk data through MPI collective I/O |
| `COLLECTIVE_METADATA` | `NO` (except collective study) | consolidate HDF5 metadata through one rank |
| `stripe-count` / `stripe-size` | `4` / `1M` | Lustre striping, pinned so native and container are comparable |

### Three traps in h5bench's own parameter handling

These were found by reading h5bench's source, and each silently produces wrong results rather than an error.

**1. `NUM_PARTICLES` is overwritten.** It is parsed and then unconditionally replaced by `DIM_1 × DIM_2 × DIM_3` (`commons/h5bench_util.c:1170`). Setting only `NUM_PARTICLES` yields **1 particle per rank** and a benchmark that writes essentially nothing. This is why the configs set `DIM_1` and leave `DIM_2`/`DIM_3` at 1.

**2. `"1 M"` needs the space.** `parse_unit()` uses `strtok(str, " ")`, so `"1M"` without a space parses as a literal **1**. `M_VAL = 1024 × 1024`.

**3. Units are binary but labeled decimal.** h5bench switches between `MB/s` and `GB/s` by magnitude, and both are binary (`1 "GB" = 1024 "MB"`). Averaging the bare numbers mixes scales — an early draft of this analysis reported a nonsensical 497 GiB/s that way. The analysis code normalizes via the unit column.

**Particle size is 32 bytes** (7 floats + 1 int), verified empirically: 4 ranks × 2 timesteps × 1 particle produced exactly 256 B.

## 3. What each study varies

### intra-node — access pattern
`MEM_PATTERN × FILE_PATTERN`, both ∈ {CONTIG, INTERLEAVED} = 4 combinations at 128 ranks. Probes how the memory→file layout mapping interacts with HDF5 and Lustre.

### weak scaling — per-rank work fixed
`DIM_1 = "1 M"` throughout, so each rank always writes 32 MiB/timestep and total volume grows with node count. Asks *can Lustre absorb more load*.

### strong scaling — total work fixed
```bash
TOTAL_PARTICLES_M=128                       # 128 M particles, always
DIM_1 = TOTAL_PARTICLES / NP                # per-rank share shrinks
#   1 node  (128 ranks)  -> 1048576  (32 MiB/rank)
#   8 nodes (1024 ranks) ->  131072  ( 4 MiB/rank)
```
Asks *does splitting a fixed job across more clients still help*. A divisibility guard aborts if `TOTAL_PARTICLES % NP ≠ 0`, so no per-rank size is silently truncated.

### collective I/O — a 2×2 factorial
Fixed at 2 nodes / 256 ranks; varies only the two HDF5 switches:

| `COLLECTIVE_DATA` | `COLLECTIVE_METADATA` | directory |
|---|---|---|
| NO | NO | `dno_mno` |
| NO | YES | `dno_myes` |
| YES | NO | `dyes_mno` |
| YES | YES | `dyes_myes` |

**Both flags are varied separately because they exercise different mechanisms.** `COLLECTIVE_DATA` routes bulk data through MPI-IO two-phase aggregation — network communication traded for better disk access. `COLLECTIVE_METADATA` consolidates HDF5 metadata through one rank instead of 256 hitting the MDT. Collapsing them into one on/off switch would make an observed change unattributable.

### cold read validation — a methodology check
Separate **write** and **read** jobs so the read runs on *different nodes* from the write, defeating client page cache. `READ_OPTION=FULL` — the only parallel-safe option (`PRL`/`RDC`/`LDC`/`CS` are single-process). Each run records `node_overlap.txt`; a read that landed on a writer's node is **void**, and this check caught a 6× phantom "native advantage" early on.

## 4. The launch model — hybrid, and why it is mandatory

```bash
# native
h5bench -a -d config.json

# container
h5bench -a -d -p /opt/h5bench/install/bin config.json
#              ^^ host driver, container binaries
```

The **host Python driver** runs in both cases; `-p` points it at the binary directory **inside the `.sif`**. The driver calls `mpirun`, and each rank enters the container.

Why not run the driver inside the container? The container's generic OpenMPI has no PBS `tm` support and no inter-node ssh path, so it cannot spawn ranks across nodes from inside. The host `mpirun` must do the fan-out.

Two source details that make `-p` work:
- `src/h5bench.py:402` — the `-p` prefix is concatenated **without** an `os.path.isfile()` check (that check exists only on the no-prefix branch), which is what allows a path that exists only inside the container.
- `src/h5bench.py:257` — `mpi.configuration` **replaces** `ranks` entirely, so `-np` must be given explicitly in `MPI_CONFIG`.

The container jobs assert afterwards that the driver really invoked the container binary:
```bash
grep -Eq "apptainer exec .*${CONTAINER_BIN_DIR}/+h5bench_write" "$DRIVER_LOG" \
  || { echo "FATAL: driver did not invoke the container binary"; exit 1; }
```

## 5. Resources and placement

| | intra-node | inter-node |
|---|---|---|
| select | `1:ncpus=128:mpiprocs=128:mem=64gb` | `${NODES}:ncpus=128:mpiprocs=128:mem=64gb` |
| place | `excl` | **`scatter:excl`** |
| walltime | `02:30:00` | per study |

`ncpus` equals `mpiprocs` — the convention used across IOR and OSU too. `place=scatter:excl` is what makes inter-node genuinely multi-node; without `scatter`, PBS could pack chunks onto one host and an "8-node" job would quietly run on fewer.

**MPI flags** mirror the other benchmarks: native uses `--mca pml ucx`; the container uses `vader,self` with `btl_vader_single_copy_mechanism none` on one node, adding `tcp` + `hsn0` pins across nodes.

## 6. Output layout

```
<study>/logs/<job>.out                           PBS output
<variant>/<config>/...                           per-run CSVs
payload/<variant>/<config>/<uuid>/               h5bench's own output dir
```

**Finding the CSV is non-obvious.** The driver rewrites `CSV_FILE` to `<directory>/<uuid>/<csv>` (`src/h5bench.py:370`), so results land under `payload/.../<random-uuid>/`. The UUID carries no ordering — the repetition index survives only in the filename (`write_rep3.csv`).

HDF5 payload stays on Lustre and is not copied back; only CSVs and logs are.

## 7. Running it

```bash
cd intra_node                    && ./submit_native_intra_job.sh       && ./submit_container_intra_job.sh
cd inter_node/weak_scaling       && ./submit_native_weak_job.sh        && ./submit_container_weak_job.sh
cd inter_node/strong_scaling     && ./submit_native_strong_job.sh      && ./submit_container_strong_job.sh
cd inter_node/collective_io      && ./submit_native_collective_job.sh  && ./submit_container_collective_job.sh
cd inter_node/cold_read_validation && ./submit_coldread_jobs.sh
```

**Queue routing.** PBS routes on ncpus *and* walltime: 128 ncpus needs walltime > 02:00:01 to reach `q4`, otherwise it lands in `qdev` whose 256-ncpu cap is cluster-wide. ≥129 ncpus → `q5`.

## 8. Before reading the results

**Reads are cache-inflated unless cold-read validated.** Within a single run h5bench reads back what it just wrote. The cold-read study exists precisely to quantify that; everywhere else, treat write bandwidth as the measurement.

**The container effect is below this experiment's noise floor**, as with IOR — h5bench found no measurable container write penalty. That is a bounded negative result, corroborating IOR independently through a different I/O stack (HDF5 rather than raw POSIX/MPI-IO).

Full analysis: [`../results/`](../results/) and [`../analysis/README.md`](../analysis/README.md).
