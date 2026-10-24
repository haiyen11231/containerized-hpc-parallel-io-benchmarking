# IOR — intra-node

64 ranks on a single node writing to Lustre. This is the **access-pattern sweep**: rank count is fixed and the I/O configuration is what varies, matching the convention used by h5bench's intra-node study and OSU pt2pt (fixed concurrency, sweep a workload dimension; node-count scaling lives in `../inter_node/`).

---

## 1. What it varies — a 2×2×2 factorial, each cell sweeping transfer size

| dimension | values | what it probes |
|---|---|---|
| **API** | `POSIX`, `MPIIO` | the I/O library path — POSIX goes straight to the filesystem, MPI-IO adds the MPI collective-I/O layer |
| **Access model** | `shared`, `fpp` | one file for all 64 ranks vs one file per rank |
| **Lustre stripe count** | `1`, `8` | how many OSTs the data is spread across |
| **Transfer size** | 64k, 256k, 1m, 4m, 16m | per-call I/O size, swept inside each job |

8 jobs per variant (2 API × 2 model × 2 stripe), each sweeping 5 transfer sizes = **40 measurements per variant**.

**Why these three knobs.** They map directly onto the project's three mechanisms: API is the runtime/library path (#1), access model is how the container's filesystem view maps onto storage (#2), and stripe count is Lustre-specific behavior (#3). Sweeping transfer size inside each cell separates per-call overhead from bulk throughput.

## 2. Striping is pinned explicitly

```bash
lfs setstripe -c "$STRIPE_COUNT" -S 1m "$PAYLOAD_DIR"
lfs getstripe "$PAYLOAD_DIR"      # verified, and the output is kept in the log
```

This is not optional. Lustre's default striping is not guaranteed stable, so without pinning it a native run and a container run could silently be writing to differently-striped directories and the comparison would be meaningless. Setting it explicitly and then *reading it back* is what makes the two variants comparable.

`-S 1m` fixes the stripe size at 1 MiB in both cases so only the stripe **count** varies.

## 3. Resources

```bash
#PBS -l select=1:ncpus=64:mpiprocs=64:mem=32gb
#PBS -l place=excl
#PBS -l walltime=00:30:00
```

`ncpus` matches `mpiprocs` — the convention used throughout this project. 64 ranks is half a node, deliberately: it leaves headroom so the measurement is not simultaneously contending for every core, while still being enough concurrency to load the filesystem.

`place=excl` keeps other jobs off the hardware. On a shared cluster writing to shared Lustre, you cannot remove *filesystem* contention, but you can remove *node* contention — and this does that much.

## 4. IOR flags

```bash
ior -a "$API" $FPP_FLAG -t "$T" -b 64m -e -C -i 10 -o "$TEST_FILE"
```

| flag | why |
|---|---|
| `-t` | transfer size, the swept variable |
| `-b 64m` | block size per rank, fixed so only transfer size changes |
| `-e` | `fsync` before closing — without it the write would be timed as "handed to the page cache", not "on Lustre" |
| `-C` | reorder tasks so a rank does not read back the block it just wrote |
| `-i 10` | **10 repetitions inside IOR**, which is where this study's statistics come from |
| `-F` (via `$FPP_FLAG`) | file-per-process when `MODEL=fpp`; absent means single shared file |

**Note the repetition model differs from the other benchmarks.** h5bench and OSU run the whole job 10 times (`REPS=10`), producing 10 files. IOR uses its own `-i 10` and writes one file containing all 10 iterations plus a `Summary of all tests` block with mean and standard deviation. The analysis reads that summary.

**`-e` is the flag that makes the numbers meaningful** and is worth stating in the thesis: without `fsync`, write bandwidth measures memory speed.

## 5. Guards

| guard | catches |
|---|---|
| `: "${STRIPE_COUNT:?…}"`, `: "${API:?…}"` | job submitted without required variables |
| `lfs getstripe` echoed into the log | striping silently not applied |
| `$MPIRUN_EXIT` checked per transfer size | one cell failing while the sweep continues |
| `COMPLETED WITH FAILURES` banner | a job that finished but had failed cells — visible without reading the whole log |

## 6. Output

```
logs/<job>.out                                       PBS job output
<variant>/<api>/<model>/stripe_c<N>/ior_t<T>.txt     one file per transfer size
```

Every path carries variant, API, access model and stripe count, so the 16 jobs write to disjoint trees and cannot overwrite one another.

The payload (the actual test files) is written to `<variant>/stripe_c<N>/<api>_<model>/` on Lustre and is **not** copied back — only the `.txt` result files are.

## 7. Running it

```bash
./submit_native_job.sh       # 8 jobs
./submit_container_job.sh    # 8 jobs
```

64 ncpus with walltime ≤ 2 h routes to `qdev`. For `q3` (65–127 ncpus) or `q4` (128), raise walltime above 02:00:01 — see the queue notes in `../../../CLAUDE.md`.

## 8. Reading the results

See [`../../results/intra_node/README.md`](../../results/intra_node/README.md). The short version: **the container effect is below this experiment's noise floor**, and the dominant finding is the access model (FPP ≈ 3.5× shared-file), not containerization.
