# OSU pt2pt — inter-node

Two MPI ranks on **different** nodes. Every message crosses the Slingshot fabric, so this measures the network transport directly.

Compare with `../intra_node/`, which puts both ranks on one node and measures shared memory instead.

---

## 1. What this measures

This is the most direct measurement in the whole project of the difference the project is about:

| | native | container |
|---|---|---|
| transport | **UCX over Slingshot** (`--mca pml ucx`) | **TCP over `hsn0`** (`--mca btl tcp,self`) — the apt OpenMPI has no UCX |

Nothing else differs. No files are touched, no storage is involved, both ranks run the identical binary on identical hardware. Any gap is the cost of the container's MPI stack on the network path — **mechanism #1 in isolation, at its most exposed**.

The intra-node study removes the network to isolate everything else; this one removes everything else to isolate the network. Together they bracket the problem.

**This is where the largest container gap in the project is expected.** The h5bench studies found no measurable write penalty because bulk data transfer dominated and diluted the transport difference. Here there is nothing to dilute it.

## 2. The one thing that makes this inter-node

```bash
-l select=2:ncpus=1:mpiprocs=1:mem=8gb       # 2 chunks, ONE rank each
-l place=scatter:excl                         # chunks must land on different hosts
--map-by ppr:1:node                           # exactly one rank per node
```

All three are needed, and the failure mode if any is missing is **silent**: OpenMPI fills a node's cores before moving to the next, so without `ppr:1:node` both ranks would land on the same host. The benchmark would run fine and report shared-memory latency — a spectacularly good "network" result that is simply measuring the wrong thing.

The script therefore verifies the allocation before running:

```bash
ACTUAL_NODES=$(sort -u "$PBS_NODEFILE" | wc -l)
[ "$ACTUAL_NODES" -ne 2 ] && exit 1
```

and writes the two hostnames to `<variant>/<bench>/nodes.txt` so the result carries its own proof.

## 3. MPI flags, and why the container's differ from intra-node

**Native:**

| flag | purpose |
|---|---|
| `--mca pml ucx` | UCX point-to-point layer — the Slingshot-native path |
| `--mca btl ^openib` | disable the obsolete InfiniBand BTL |
| `--map-by ppr:1:node --bind-to core` | one rank per node, pinned to a core |

**Container:**

| flag | purpose |
|---|---|
| `--mca btl tcp,self` | no UCX available, so TCP carries the traffic; `self` handles loopback |
| `--mca btl_tcp_if_include hsn0` | **pin data traffic to the Slingshot interface** |
| `--mca oob_tcp_if_include hsn0` | pin the out-of-band wire-up traffic too |

The `hsn0` pins are not cosmetic. Without them the container's OpenMPI can select `docker0`, which has an **identical IP address on every node** — the job then hangs rather than failing cleanly. This was diagnosed empirically earlier in the project.

**Note what is absent:** `btl_vader_single_copy_mechanism none` appears in the intra-node container script but **not** here. With one rank per node no shared-memory transfer ever occurs, so Apptainer's CMA breakage is irrelevant to this case. The two container configurations legitimately differ, and that difference is itself worth stating in the write-up.

## 4. Why the driver runs on the host

Same hybrid model as everywhere else in this project: host `mpirun` fans the ranks out via PBS, each rank enters the container through `apptainer exec`.

It is **mandatory** here rather than merely consistent. The container's generic OpenMPI has no PBS `tm` support and no working ssh path between compute nodes, so it cannot spawn a rank on a second node at all. Running the benchmark entirely inside the container would simply fail.

## 5. The two kernels

| binary | measures | what to watch |
|---|---|---|
| `osu_latency` | round-trip time, 1 B → 4 MB | **small messages** — where per-message overhead dominates and the UCX/TCP gap should be largest |
| `osu_bw` | sustained bandwidth with a window of outstanding sends | **large messages** — where the fabric's raw throughput matters |

Expect these to tell different stories. TCP's per-message cost is far higher than UCX's, but at multi-MB messages both may approach the link limit.

## 6. Guards

| guard | catches |
|---|---|
| `: "${BENCH:?…}"`, `: "${REPS:?…}"` | job submitted without required variables |
| `test -x` on the binary (inside the `.sif` for the container) | wrong path or missing build |
| **`ACTUAL_NODES -ne 2`** | **both ranks landed on one node — would silently measure shared memory** |
| `grep -cE '^[0-9]'` on the output | a run that exits 0 but prints no data table |

The node-count check is the important one here. It is the inter-node equivalent of the cold-read study's node-overlap check: a guard against a plausible-looking number that measures the wrong thing.

## 7. Output

```
logs/osu_<variant>_pt2pt_inter_<bench>.out    PBS job output
<variant>/<bench>/osu_<bench>_rep<N>.txt      one OSU table per repetition
<variant>/<bench>/nodes.txt                   the two hosts used — proof it was inter-node
```

Every path carries the variant and the benchmark, so the four jobs write to disjoint trees. This directory is separate from `../intra_node/`, so the two studies cannot mix either.

`REPS=10`, matching h5bench and IOR.

**On a rerun:** `.txt` files and `logs/*.out` are overwritten. Wipe `native/`, `container/` and `logs/*.out` first, after copying anything worth keeping.

## 8. Running it

```bash
./submit_native_pt2pt_inter_job.sh       # 2 jobs (latency, bw)
./submit_container_pt2pt_inter_job.sh    # 2 jobs
REPS=1 ./submit_native_pt2pt_inter_job.sh   # smoke test
```

`ncpus` matches `mpiprocs` (project convention), so this is 2 ncpus in total rather than 256 — which means it fits `qdev`, where the old 128-per-chunk request did not. Exclusivity still comes from `place=scatter:excl`, verified to yield `state = job-exclusive`.

Walltime is a fixed `00:30:00`, set in the `.pbs`, same as intra-node. Each job takes a couple of minutes once scheduled.
