# OSU collectives — inter-node scaling

Allreduce and Alltoall across **2, 4, 8 nodes at 128 ranks per node** (256 → 1024 ranks). Collectives now cross the Slingshot fabric, so this measures shared memory **and** network together.

```
weak_scaling/     message size per peer fixed at 64 KiB   (same as intra-node)
strong_scaling/   total problem fixed at 8 MiB            (same as intra-node)
diagnostics/      controlled test of the Alltoall failure (see section 6)
```

24 jobs (2 modes × 2 variants × 2 benchmarks × 3 node counts), 10 repetitions each.

---

## 1. Continuity with intra-node — deliberate

Both message-size rules are **identical** to the intra-node study, so the two join into one curve rather than being separate experiments:

| | intra (8→128 ranks) | inter (256→1024 ranks) |
|---|---|---|
| weak | 64 KiB/rank | 64 KiB/rank |
| strong | 1024 → 64 KiB/rank | 32 → 8 KiB/rank |

Strong scaling therefore runs one continuous 8 MiB problem from 8 ranks (1 MiB each) to 1024 ranks (8 KiB each). The intra-node 128-rank point and the inter-node 256-rank point sit either side of the node boundary, which is exactly where the most important result appears — the container's Allreduce advantage inverting.

## 2. The configuration choice that matters most

The container needs **both** transports here, and this differs from the pt2pt inter-node study:

```bash
# collective inter-node, container:
--mca btl vader,tcp,self                   # BOTH paths
--mca btl_vader_single_copy_mechanism none
--mca btl_tcp_if_include hsn0
--mca oob_tcp_if_include hsn0

# pt2pt inter-node, container (1 rank/node):
--mca btl tcp,self                         # tcp alone was correct there
```

With 128 ranks per node a collective uses shared memory **and** the network simultaneously. pt2pt inter-node ran one rank per node, so TCP alone was right.

**Omitting `vader` here would force on-node rank pairs through TCP loopback and massively overstate the container's cost** — producing a dramatic result that was really a configuration error. Native needs no equivalent change because UCX covers both paths in one stack.

The `hsn0` pins stop OpenMPI selecting `docker0`, which carries an identical IP on every node and makes the job hang rather than fail cleanly.

## 3. Resources

```bash
-l select=${NODES}:ncpus=128:mpiprocs=128:mem=64gb
#PBS -l place=scatter:excl
#PBS -l walltime=02:30:00
```

| choice | why |
|---|---|
| `place=scatter:excl` | **what makes this inter-node** — without `scatter`, PBS could pack chunks onto one host and an "8-node" job would quietly run on fewer |
| `ncpus` = `mpiprocs` = 128 | project convention; the full node is genuinely used here |
| `mem=64gb` | worst case is Alltoall weak at 8 nodes, ~16 GiB/node |
| `walltime=02:30:00` | worst cell is ~26 min of data movement (container Alltoall, 8 nodes, 64 GiB/iteration). ≥256 ncpus routes to **q5**, which has no walltime floor, so the long walltime costs nothing in queue placement |

## 4. Guards

Six, plus divisibility in strong scaling. The inter-node-specific one:

```bash
UNEVEN=$(awk '{c[$1]++} END {for (h in c) if (c[h] != 128) print h, c[h]}' "$PBS_NODEFILE")
```

An uneven rank split would load one node's shared memory more than another and distort the collective — the multi-node analogue of pt2pt's "both ranks on one host" trap. Combined with `ACTUAL_NODES -ne NODES` and `SLOTS -ne NP`, a job cannot silently measure a different scale than its own label claims.

**A failing run is still recorded.** The `rows -lt 1` guard is what caught the Alltoall failures described below — those cells produced 0 data rows and were excluded from analysis rather than averaged in as zeros.

## 5. Expect four cells to fail — this is a result, not a bug

**Container Alltoall fails at 4 and 8 nodes** with `bind … Address already in use (98)`.

Alltoall requires every rank to connect to every peer, and all 128 ranks on a node share that node's single `hsn0` IP:

| nodes | ranks | conns/node | vs ~28,232 ephemeral ports |
|---|---|---|---|
| 2 | 256 | 32,640 | 1.16× — survives via `tcp_tw_reuse=2` |
| 4 | 512 | 65,408 | **2.32× — fails** |
| 8 | 1024 | 130,944 | **4.64× — fails** |

Allreduce is unaffected at every scale because it needs `O(log P)` connections, not all-pairs. Native is unaffected because UCX/RDMA opens no per-peer sockets.

**Do not "fix" this by reducing ranks per node.** The failure is the most consequential finding in the OSU work — the container's lack of UCX is a *hard scalability ceiling*, not a slowdown. Lowering concurrency until it works would delete that result and break comparability with every other 128-rank study in the project.

## 6. `diagnostics/` — proving the cause

`port_exhaustion_diag.pbs` runs three arms **inside one allocation**, on the same four nodes within ~51 seconds:

| arm | conns/node | result |
|---|---|---|
| container, 128 ranks/node (512 total) | 65,408 | **FAIL**, 512 port errors |
| container, **64** ranks/node (256 total) | 16,320 | **PASS** |
| native, 128 ranks/node (512 total) | 65,408 | **PASS** |

Arm 2 changes only the connection count. Arm 3 runs the *same 512 ranks* that broke the container. Together they exclude "the scale is too large" and "those nodes were unhealthy", leaving the TCP transport as the only remaining explanation.

The job also records `ip_local_port_range` from a compute node, so the 28,232-port figure the argument rests on is measured rather than assumed.

## 7. Output

```
<mode>_scaling/logs/<job>.out
<mode>_scaling/<variant>/<bench>/n<N>/osu_<bench>_rep<R>.txt
<mode>_scaling/<variant>/<bench>/n<N>/nodes.txt          hosts used
<mode>_scaling/<variant>/<bench>/n<N>/bindings.txt       rank -> core placement
<mode>_scaling/<variant>/<bench>/n<N>/ranks.txt          total rank count
<mode>_scaling/<variant>/<bench>/n<N>/msgsize_bytes.txt
```

## 8. Running it

```bash
cd weak_scaling   && ./submit_native_collective_inter_weak_job.sh   && ./submit_container_collective_inter_weak_job.sh
cd strong_scaling && ./submit_native_collective_inter_strong_job.sh && ./submit_container_collective_inter_strong_job.sh
```

All jobs route to **q5**, whose per-user `max_run` is 20 — submitting all 24 means the last four wait for a slot. q5 is also heavily contended (100+ queued is normal), and the 8-node jobs are the slowest to schedule. Expect hours, not minutes.

## 9. Results

[`../../../results/collective/inter_node/README.md`](../../../results/collective/inter_node/README.md) — the Allreduce sign flip (0.78× intra → 3.52× inter), the Alltoall ceiling, and why native's own scaling curve is not smooth.
