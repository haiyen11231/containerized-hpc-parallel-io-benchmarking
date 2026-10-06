# OSU pt2pt — intra-node

Two MPI ranks on **one** node. Measures the intra-node MPI transport with no network involved.

---

## 1. What this measures, and why it comes first

Point-to-point is the simplest MPI operation: rank 0 sends, rank 1 receives. With both ranks on the same node there is no network — the message goes through **shared memory**. That isolates one specific thing:

| | native | container |
|---|---|---|
| transport | **UCX** shared memory (`--mca pml ucx`) | **vader** (`--mca btl vader,self`) — the apt OpenMPI has no UCX |

So any gap here is the cost of the container's MPI stack on the shared-memory path alone. It is the cleanest possible isolation of **mechanism #1 (runtime overhead)**, with mechanisms #2 and #3 (storage, filesystem) entirely absent — OSU touches no files.

This is the counterpart to h5bench's intra-node study, which isolates #2 and #3 by removing the network. Together they let you attribute a multi-node gap to the right layer.

## 2. The two kernels

| binary | measures | dominated by |
|---|---|---|
| `osu_latency` | round-trip time for one message, size swept 1 B → 4 MB | **small messages** — fixed per-message cost |
| `osu_bw` | sustained bandwidth with a window of outstanding sends | **large messages** — memory/copy throughput |

They stress different things and usually disagree about which stack is better, which is why both are run. Latency exposes per-call overhead (where container indirection would show up); bandwidth exposes copy efficiency (where the single-copy mechanism matters).

## 3. Why `btl_vader_single_copy_mechanism none` matters here

OpenMPI's `vader` shared-memory transport normally uses **CMA** (`process_vm_readv`) to copy a message directly from one rank's address space to another's — a *single* copy.

Apptainer's user-namespace isolation breaks that syscall's permission check, so without the flag the transport either fails or falls back unpredictably. With `none`, vader uses a shared-memory staging buffer instead — a **double** copy.

That is not a workaround detail to hide; it is likely a real part of the measured gap, and `osu_bw` at large messages is exactly where a double copy would show. Worth saying explicitly in the write-up.

## 4. Resources

```bash
-l select=1:ncpus=2:mpiprocs=2:mem=8gb   # passed by the submit script
#PBS -l place=excl
#PBS -l walltime=00:30:00                # fixed for all pt2pt jobs
```

**`ncpus` matches `mpiprocs`** — the convention used throughout this project (IOR's 16- and 64-rank jobs do the same). Declare the cores you actually launch on; don't inflate the request.

**Exclusivity comes from `place=excl`, not from a large `ncpus`.** This was verified empirically: a job submitted as `ncpus=2:place=excl` reports `state = job-exclusive` with `jobs = <this job only>`, so no other job shares the hardware. That matters because a noisy neighbour perturbs latency far more than bandwidth — a few microseconds of interference is invisible in an I/O benchmark and fatal in a sub-microsecond latency measurement.

**Why not request 128 anyway?** Because it costs scheduling time for nothing. The same probe measured a `ncpus=2` job starting **16 seconds** after submission while an otherwise identical `ncpus=128` job was still queued many minutes later — qdev's 256-ncpu cap is cluster-wide, so a 128-core request takes half of it. PBS confines the job to an `ncpus`-sized cpuset either way (`cpuset.cpus = 0-1,128-129` for `ncpus=2`), and since OpenMPI pins the two ranks to cores 0 and 1 regardless, the measurement is unchanged.

**Walltime is a fixed `00:30:00`** for every pt2pt job — ample for these runs, and it keeps them all in `qdev`.

## 5. Rank placement is pinned deliberately

```bash
--map-by core --bind-to core
```

Rank 0 → core 0, rank 1 → core 1, deterministically.

Intra-node latency depends heavily on *where* the two ranks land: same core complex, same socket, or across sockets on this dual-EPYC node give materially different numbers. Pinning makes the measurement reproducible and the native/container comparison fair — without it, run-to-run placement differences would swamp the effect being measured.

A same-socket vs cross-socket sweep would be a legitimate extension, but it is a different question and is not part of this baseline.

## 6. Guards

| guard | catches |
|---|---|
| `: "${BENCH:?…}"`, `: "${REPS:?…}"` | job submitted without required variables |
| `test -x` on the binary (inside the `.sif` for the container) | wrong path or missing build |
| `ACTUAL_NODES -ne 1` | PBS granting a different allocation |
| `grep -cE '^[0-9]'` on the output | **a run that exits 0 but produces no data table** — the silent failure mode |

The last one matters: OSU can exit cleanly having printed only a header if MPI wiring fails in certain ways. Counting data rows catches that at job time rather than during analysis.

## 7. Output

```
logs/osu_<variant>_pt2pt_intra_<bench>.out    PBS job output
<variant>/<bench>/osu_<bench>_rep<N>.txt      one OSU table per repetition
<variant>/<bench>/nodes.txt                   which node ran it
```

Every path carries the variant and the benchmark, so the four jobs write to disjoint trees — native cannot overwrite container.

Each `.txt` is a two-column OSU table:

```
# Size          Latency (us)
1                       0.21
2                       0.21
...
4194304              1234.56
```

Analysis parses size → value per repetition and computes a mean ± 95% CI **per message size**, since the native/container gap is expected to vary with size rather than being a single number.

`REPS=10` matches the h5bench and IOR sample size.

**On a rerun:** `.txt` files and `logs/*.out` are overwritten (deterministic names). Wipe `native/`, `container/` and `logs/*.out` before resubmitting, after copying anything worth keeping.

## 8. Running it

```bash
./submit_native_pt2pt_intra_job.sh       # 2 jobs (latency, bw)
./submit_container_pt2pt_intra_job.sh    # 2 jobs
REPS=1 ./submit_native_pt2pt_intra_job.sh   # smoke test
```

Each job takes a couple of minutes — OSU's default message sweep is short.

All pt2pt jobs use a fixed `walltime=00:30:00`, set in the `.pbs`. That is far more than these runs need and keeps every pt2pt job in `qdev`, so there is nothing to choose at submission time.
