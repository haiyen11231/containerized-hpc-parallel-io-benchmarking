# OSU Micro-Benchmarks — baseline experiment guide

Native vs Apptainer container on Aspire 2A. This file records **how everything was built, what was run, and why each choice was made**, so the work can be reproduced or defended without reading the scripts.

Per-study detail lives in the READMEs; this is the overview.

---

## 1. System

| | |
|---|---|
| Cluster | Aspire 2A (NSCC Singapore), PBS Pro |
| CPU nodes | 2× AMD EPYC 7713 — 128 physical cores (256 threads), 8 cores/CCD, 64/socket |
| Memory | 512 GB/node (~440 GB usable) |
| Interconnect | HPE Slingshot, interface `hsn0` |
| Storage | Lustre at `/scratch` (`~/scratch` is the symlink) |
| Container runtime | Apptainer 1.5.0 |

**The two MPI stacks being compared — this is the whole experiment:**

| | native | container |
|---|---|---|
| MPI | OpenMPI 4.1.2-hpe (Cray build) | OpenMPI 4.1.2 (generic `apt`, Ubuntu 22.04) |
| transport, on-node | **UCX shared memory** (CMA single-copy) | **vader**, CMA disabled → two-copy |
| transport, off-node | **UCX over Slingshot** (RDMA) | **TCP over `hsn0`** |

The container's OpenMPI has **no UCX support at all**. Everything measured follows from that.

## 2. Build — native

```bash
module purge
module load libfabric/1.11.0.4.125
module load openmpi/4.1.2-hpe

wget https://mvapich.cse.ohio-state.edu/download/mvapich/osu-micro-benchmarks-8.0rc.tar.gz
tar -xvf osu-micro-benchmarks-8.0rc.tar.gz
cd osu-micro-benchmarks-8.0rc
./configure CC=mpicc CXX=mpicxx --prefix=$(pwd)/install
make && make install
```

Two things that cost time and are worth recording:

**`libfabric` must be loaded BEFORE `openmpi`.** `mpicc` and `mpirun` are dynamically linked against `libfabric.so.1`; without it, `configure` fails with *"C compiler cannot create executables"* and the real error is only visible in `config.log` as `error while loading shared libraries`.

**`--prefix` is required.** The default `/usr/local` is not writable, so `make install` fails at the very end of an otherwise successful build.

**The toolchain is gcc, not icc.** `mpicc --version` under `openmpi/4.1.2-hpe` reports `gcc (GCC) 8.5.0`. Worth stating explicitly because the module list looks Intel-flavoured.

Installed binaries: `install/libexec/osu-micro-benchmarks/mpi/{pt2pt,collective}/`.

> OSU 8.0 symlinks every collective to a single `omb_coll` binary that dispatches on `argv[0]`, so `osu_allreduce` and `osu_alltoall` are the same file. This works correctly through `apptainer exec` as well.

## 3. Build — container

`deployment/osu/osu_micro_benchmarks.def`, built with Apptainer from an Ubuntu 22.04 base with `apt`-installed OpenMPI. Binaries land at `/opt/osu-micro-benchmarks-8.0rc/install/libexec/...`, mirroring the native layout.

**Launch model: host `mpirun` + per-rank `apptainer exec`.**

```bash
mpirun -np N <mpi flags> apptainer exec "$SIF" "$BIN" <args>
```

This is mandatory, not stylistic: the container's generic OpenMPI has no PBS `tm` support and no working inter-node ssh path, so it cannot spawn ranks across nodes from inside. The host `mpirun` fans ranks out via PBS; each rank then enters the container.

## 4. MPI flags, and why each is there

**Native (all studies):**
```bash
--mca btl ^openib          # disable the obsolete InfiniBand BTL
--mca pml ucx              # UCX handles shared memory AND Slingshot
-x UCX_LOG_LEVEL=ERROR
```

**Container — and the flags differ by study, which matters:**

| study | flags | why |
|---|---|---|
| pt2pt intra (2 ranks, 1 node) | `--mca btl vader,self`<br>`--mca btl_vader_single_copy_mechanism none` | shared memory only. CMA is disabled because Apptainer's user namespace breaks it |
| pt2pt inter (1 rank/node) | `--mca btl tcp,self`<br>`--mca btl_tcp_if_include hsn0`<br>`--mca oob_tcp_if_include hsn0` | network only — with one rank per node no shared-memory transfer occurs, so `vader` is unnecessary |
| collective intra (8–128 ranks) | `vader,self` + CMA disabled | as pt2pt intra, but now every rank does shared-memory transfers at once |
| **collective inter (128 ranks/node)** | **`--mca btl vader,tcp,self`** + CMA disabled + `hsn0` pins | **BOTH paths at once.** 128 ranks/node use shared memory *and* the network simultaneously |

**The `vader,tcp,self` case is the easiest thing to get wrong.** Omitting `vader` would push on-node rank pairs through TCP loopback and massively overstate the container's cost — a dramatic result that is really a configuration error.

**The `hsn0` pins are not cosmetic.** Without them OpenMPI may select `docker0`, which carries an identical IP on every node; the job then hangs rather than failing cleanly.

## 5. What was run

**684 result files across six studies, every configuration repeated 10×.**

| study | scale | varies | jobs |
|---|---|---|---|
| pt2pt intra | 2 ranks, 1 node | message size (OSU default sweep) | 4 |
| pt2pt inter | 2 ranks, 2 nodes | message size | 4 |
| collective intra, weak | 8→128 ranks, 1 node | rank count; 64 KiB/rank fixed | 20 |
| collective intra, strong | 8→128 ranks, 1 node | rank count; 8 MiB total fixed | 20 |
| collective inter, weak | 2/4/8 nodes @128 r/node | node count; 64 KiB/rank fixed | 12 |
| collective inter, strong | 2/4/8 nodes @128 r/node | node count; 8 MiB total fixed | 12 |
| port-exhaustion diagnostic | 4 nodes, 3 arms | ranks/node and transport | 1 |

Benchmarks: `osu_latency`, `osu_bw` (pt2pt); `osu_allreduce`, `osu_alltoall` (collective).

**Design decisions worth defending:**

**Rank count is the collective scaling variable** because a collective's cost is intrinsically a function of P — `O(log P)` rounds for Allreduce, `O(P)` traffic for Alltoall. pt2pt is always 2 ranks, so its only axis is message size.

**`ncpus` always equals `mpiprocs`** — the convention used across IOR and h5bench too. Exclusivity comes from `place=excl`, not from inflating `ncpus`. This was verified empirically: a probe job at `ncpus=2:place=excl` reported `state = job-exclusive`, and started in **16 s** versus **>25 min** for an otherwise identical `ncpus=128` request.

**Weak and strong overlap deliberately at NP=128**, where strong's per-rank size works out to exactly 65536 bytes — the same as weak. The two independent 20-job sets agree there to within **0.3%**, which validates both.

**Alltoall's weak/strong labels are effectively inverted** and must be reported as such. Per-rank traffic is `S × P`, so fixed-S ("weak") actually *grows* per-rank work 16× across the sweep, while `T/P` ("strong") pins it at 8 MiB — making strong-scaling Alltoall the sharper experiment.

## 6. Guards — what stops a silently-wrong result

Every job aborts rather than producing a plausible-looking number from the wrong configuration:

| guard | catches |
|---|---|
| `ACTUAL_NODES` vs expected | both pt2pt ranks landing on one host — would measure shared memory and report it as network |
| `SLOTS -ne NP` | `PBS_NODEFILE` holding a different rank count than the job's label |
| uneven ranks/node (`awk` count) | an unbalanced multi-node split distorting the collective |
| `TOTAL % NP` (strong only) | 8 MiB not dividing evenly, truncating per-rank size |
| `rows -lt 1` | a run that exits 0 but produced no data table |
| `test -x` inside the `.sif` | container binary missing or mispathed |

Each run also records `nodes.txt`, `bindings.txt` (actual rank→core placement) and `msgsize_bytes.txt`, so placement and workload are **evidence rather than assumption**.

## 7. Results in one page

| measurement | container vs native |
|---|---|
| pt2pt intra, 1 B latency | 1.14× |
| pt2pt intra, 4 MiB | 1.15× |
| **pt2pt inter, 1 B latency** | **~9–12×** |
| pt2pt inter, 4 MiB | 4.76× |
| Allreduce intra, 128 r | **0.78× — container FASTER** |
| Allreduce inter, 256 r | 3.52× |
| Alltoall intra, 128 r | 2.15× |
| Alltoall inter, 256 r | 1.54× |
| **Alltoall inter, ≥512 r** | **FAILS — TCP port exhaustion** |

**Three findings:**

**1. The penalty inverts at the node boundary.** Allreduce is ~20% *faster* in the container intra-node — native's UCX pays a CMA syscall that the container's cache-resident bounce-buffer copy avoids at these sizes. Cross to the network and the same benchmark becomes 3.5–6× slower.

**2. Alltoall hits a hard ceiling, not a slowdown.** At ≥512 ranks the container fails outright. Every rank must connect to every peer, and 128 ranks share one node IP: 65,408 connections against ~28,232 ephemeral ports. Proven causally by a three-arm diagnostic on identical nodes — halving ranks/node (16,320 conns) **passes**; native at the same 512 ranks **passes**.

**3. The cost is per-message, not per-byte.** Fitting `T(S) = α + S/B` inter-node gives α penalty **9.25×** against bandwidth penalty **4.74×** — roughly **12 µs of fixed cost added to every message** (1.46 → 13.47 µs). Intra-node both are ~1.2×, with no single culprit.

## 8. Caveats to state in the write-up

**Native's own scaling is not smooth.** Allreduce is non-monotonic — NP=64 costs ~4× its neighbors at 64 and 128 ranks, reproducibly (CV ~1%, six independent confirmations). `bindings.txt` rules out socket saturation: NP=64 puts 64 ranks on socket 0 while NP=128 puts 64 on *each*, so per-socket load is identical. The remaining explanation is OpenMPI's tuned-collective algorithm selection. Both variants inherit it, so the comparison holds — but do not present the native curve as clean.

**pt2pt intra large-message bandwidth is unstable in the container** — CV 19–42% against native's 2–10%. Its mean sits above native's, but a Welch test separates almost none of those points. Report as *instability*, not a 25% container win.

**Small-message inter-node latency is node-sensitive.** The 1-byte point drifted 18% between runs. Quote "roughly an order of magnitude", not a specific factor.

## 9. Layout

```
scripts/     pt2pt/{intra_node,inter_node}/
             collective/{intra_node,inter_node}/{weak_scaling,strong_scaling}/
             collective/inter_node/diagnostics/        port-exhaustion experiment
             <study>/logs/*.out                        PBS output lives with the scripts
results/     same tree, data only — no .out files
analysis/    common.py, plot_osu.py, figures/ (10 figures)
```

10 READMEs: one per study under `scripts/` (setup) and `results/` (analysis), plus `analysis/README.md`.

## 10. Reproducing

```bash
# native build: section 2. container: deployment/osu/osu_micro_benchmarks.def
cd scripts/pt2pt/intra_node          && ./submit_native_pt2pt_intra_job.sh && ./submit_container_pt2pt_intra_job.sh
cd scripts/collective/intra_node/weak_scaling && ./submit_native_collective_weak_job.sh && ./submit_container_collective_weak_job.sh
# ... same pattern for the other studies

cd analysis && ../../../.venv/bin/python plot_osu.py
```

**Queue notes.** PBS routes on ncpus *and* walltime. ≤128 ncpus with ≤2 h → `qdev` (256-ncpu cap **shared cluster-wide**, so a 128-core job takes half of it). >128 ncpus → `q5`, per-user `max_run` 20, typically 100+ jobs deep. 8-node jobs can wait hours.
