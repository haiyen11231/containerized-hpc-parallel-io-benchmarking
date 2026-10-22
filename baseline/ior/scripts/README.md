# IOR — baseline experiments, overview

Three studies comparing native against an Apptainer container, writing to Lustre on Aspire 2A. This file is the overview: what each study varies, every parameter and why it has that value. Per-study detail is in the subdirectory READMEs.

```
intra_node/                 access-pattern sweep, 64 ranks on one node
inter_node/weak_scaling/    node-count scaling, per-rank work fixed
inter_node/strong_scaling/  node-count scaling, total work fixed
simple_test/                early validation + system diagnostics
```

---

## 1. The three studies at a glance

| | intra-node | weak scaling | strong scaling |
|---|---|---|---|
| **scale** | 1 node, 64 ranks | 1/2/4/8 nodes, 128 ranks each | same |
| **scaling variable** | — (fixed) | node count | node count |
| **sweeps** | API × model × stripe × transfer size | API × model | API × model |
| **held fixed** | 64 ranks | per-rank block = 128 MiB | **total = 64 GiB** |
| **jobs per variant** | 8 (each sweeping 5 transfer sizes) | 16 | 16 |
| **result files** | 40 | 16 | 16 |

Total **144 result files**, each containing IOR's own 10 repetitions.

**Why intra-node sweeps configuration rather than rank count.** This follows the convention used across the project: intra-node fixes concurrency and varies a workload dimension; inter-node varies node count. For I/O the interesting variable within one node is the *access pattern*, not how many ranks — a single client saturates its path to Lustre quickly, so rank count tells you little, while API and access model change the pattern fundamentally.

## 2. The dimensions, and what each probes

| dimension | values | mechanism it targets |
|---|---|---|
| **API** | `POSIX`, `MPIIO` | the I/O library path — POSIX goes straight to the filesystem, MPI-IO adds collective buffering and aggregation |
| **Access model** | `shared` (one file), `fpp` (`-F`, one file per rank) | how the container's filesystem view maps onto storage |
| **Stripe count** | `1`, `8` (intra-node only) | Lustre-specific behavior — how many OSTs the data spreads across |
| **Transfer size** | 64k, 256k, 1m, 4m, 16m (intra-node only) | separates per-call overhead from bulk throughput |
| **Node count** | 1, 2, 4, 8 (inter-node) | how many Lustre *clients* are involved |

These map onto the project's three mechanisms: API is the runtime/library path (#1), access model is the storage-mounting question (#2), and stripe count plus node count probe Lustre interaction (#3).

## 3. Every IOR parameter

The invocation is identical in all three studies apart from `-t`, `-b` and `-F`:

```bash
ior -a "$API" $FPP_FLAG -t "$T" -b "$B" -e -C -i 10 -o "$TEST_FILE"
```

| flag | value | why |
|---|---|---|
| `-a` | `POSIX` / `MPIIO` | the API under test |
| `-F` | set when `MODEL=fpp` | file-per-process; absent means a single shared file |
| `-t` | intra: 64k…16m sweep<br>inter: **4m fixed** | transfer size — the per-call I/O size |
| `-b` | intra: **64m**<br>weak: **128m**<br>strong: **64 GiB ÷ NP** | block size per rank |
| `-e` | always | **`fsync` before close.** Without it, write bandwidth measures the page cache, not Lustre — this single flag is what makes the numbers mean anything |
| `-C` | always | reorder tasks so a rank does not read back the block it just wrote |
| `-i` | **10** | 10 repetitions *inside* IOR. This is where the statistics come from |
| `-o` | per-config path | output file, on Lustre |

**Note the repetition model differs from OSU and h5bench.** Those run the whole job 10 times (`REPS=10`), producing 10 files. IOR uses its own `-i 10` and writes **one** file containing all 10 iterations plus a `Summary of all tests` block with mean and standard deviation. The analysis reads that summary. Same sample size, different mechanism.

### The block-size rule is what distinguishes weak from strong

```bash
# weak scaling -- per-rank work fixed, total grows with nodes
B=128m                                    # 16 GiB per node

# strong scaling -- total fixed, per-rank work shrinks
TOTAL_GLOBAL_MB=$((64 * 1024))            # 64 GiB total, always
B_MB=$((TOTAL_GLOBAL_MB / NP))            # 1 node -> 512m/rank ... 8 nodes -> 64m/rank
```

Weak asks *can Lustre absorb more total load*; strong asks *does splitting a fixed job across more clients still help*. They fail differently, which is why both are run.

## 4. Lustre striping is pinned and verified

```bash
lfs setstripe -c "$STRIPE_COUNT" -S 1m "$PAYLOAD_DIR"
lfs getstripe "$PAYLOAD_DIR"      # echoed into the job log
```

**This is not optional.** Lustre's default striping is not guaranteed stable, so without pinning it a native run and a container run could be writing to differently-striped directories and the comparison would be meaningless. Setting it *and reading it back into the log* is what makes the two variants provably comparable.

`-S 1m` fixes the stripe size at 1 MiB everywhere, so only the stripe **count** varies. Inter-node uses `STRIPE_COUNT=8` throughout; the 1-vs-8 comparison is made intra-node where it can be isolated.

## 5. Resources and placement

| | intra-node | inter-node |
|---|---|---|
| select | `1:ncpus=64:mpiprocs=64:mem=32gb` | `${NODES}:ncpus=128:mpiprocs=128:mem=64gb` |
| place | `excl` | **`scatter:excl`** |
| walltime | `00:30:00` | per study |
| mapping | `--map-by ppr:64:node --bind-to core` | `--map-by ppr:128:node --bind-to core` |

**`ncpus` always equals `mpiprocs`** — declare the cores you launch on. Exclusivity comes from `place=excl`, not from inflating the request.

**`place=scatter:excl` is what makes inter-node genuinely inter-node.** Without `scatter`, PBS could pack several chunks onto one host and an "8-node" job would quietly run on fewer, inflating the result.

**64 ranks intra-node, not 128** — deliberately half a node, leaving headroom so the measurement is not simultaneously contending for every core while still loading the filesystem.

## 6. MPI flags, and one that was a bug fix

**Native:**
```bash
--mca btl ^openib
--mca opal_common_ucx_opal_mem_hooks 1
-x UCX_LOG_LEVEL=ERROR
```

**Container:** `--mca btl vader,self` (no UCX in the apt build).

**`--mca btl ^openib` is a workaround, not tuning.** This system has no InfiniBand, so OpenMPI's default probe of the `openib` BTL always fails and every rank prints a `no cpcs for port` warning. With 64 ranks emitting the same warning, OpenMPI's help-message aggregation path hits an internal bug (`Data unpack would read past end of buffer` in `show_help.c`) and **aborts the run** — this is exactly what killed the c8/MPIIO/FPP/16m iteration before the flag was added. Excluding `openib` from the probe removes the trigger because the warning never fires.

Worth recording: the symptom looked like an I/O failure and was actually an MPI error-reporting bug.

## 7. Output layout

```
<study>/logs/<job>.out                                   PBS output
intra: <variant>/<api>/<model>/stripe_c<N>/ior_t<T>.txt
inter: <variant>/<api>/<model>/ior_n<N>.txt
```

Every path carries variant, API, access model and the study variable, so jobs write to disjoint trees and cannot overwrite one another.

**Payload (the test files) is written to `<variant>/stripe_c<N>/<api>_<model>/` on Lustre and deleted on exit** (`trap ... EXIT`). Only the `.txt` result files are kept and copied back.

## 8. Running it

```bash
cd intra_node                   && ./submit_native_job.sh        && ./submit_container_job.sh
cd inter_node/weak_scaling      && ./submit_native_weak_job.sh   && ./submit_container_weak_job.sh
cd inter_node/strong_scaling    && ./submit_native_strong_job.sh && ./submit_container_strong_job.sh
```

**Queue routing.** PBS routes on ncpus *and* walltime. 64 ncpus with ≤2 h → `qdev` (256-ncpu cap shared cluster-wide). 128 ncpus needs walltime > 02:00:01 for `q4`; ≥129 → `q5`.

## 9. Two things to know before reading the results

**Report write bandwidth only.** IOR reads back what it just wrote, so reads are served from the client page cache rather than Lustre — the inflation is about **27×** (1188 MiB/s write vs 32678 read in the same run). This is a measurement artifact, not a read advantage.

**The container effect is below this experiment's noise floor.** Across all 72 comparisons the median is 1.01–1.07×, and run-to-run variation on shared Lustre is CV 14–25% (up to 69% for FPP). The experiment resolves differences of roughly 20–30% and larger, so it **bounds** the container penalty rather than proving it zero. What *is* resolvable is the access model — FPP is ~3.5× faster than shared-file — which is a filesystem result, not a container one.

Full analysis: [`../results/`](../results/) and [`../analysis/README.md`](../analysis/README.md).
