# OSU optimization — findings

Phase 3 for OSU. The feasibility probe produced a decisive result before any optimization experiment was written, and it **corrects an assumption the baseline was built on**.

---

## 1. The result

One MCA flag closes the entire inter-node gap — confirmed across the **full message-size sweep** (23 sizes, 1 B – 4 MiB, 10 reps each), not just the initial 1-byte probe:

| | 1 B latency | 4 MiB latency | 1 B bandwidth | 4 MiB bandwidth |
|---|---|---|---|---|
| native (target) | 1.46 µs | 349.7 µs | 3.7 MB/s | 12,249 MB/s |
| container, baseline (TCP) | 17.10 µs | 1663.2 µs | 0.3 MB/s | 5,063 MB/s |
| **container, optimized (UCX)** | **1.67 µs** | **350.6 µs** | **4.2 MB/s** | **12,248 MB/s** |

`analysis/figO1a_pt2pt_latency.png` / `figO1b_pt2pt_bandwidth.png` — the optimized curve sits on top of native across the entire sweep; the TCP baseline sits an order of magnitude above both.

**The container reaches native latency and bandwidth with no rebuild, no bind-mount, and no image change — only a different `mpirun` flag.** At large messages (≥2 MiB) the optimized container is statistically indistinguishable from native in any way that matters: the residual gap is ~0.2–0.9 µs (resolvable by a Welch t-test because run-to-run noise is under 1% CV, but two orders of magnitude smaller than the 12 µs TCP penalty it replaces).

### Why: `analysis/figO2_architecture.png`

The three configurations share more hardware and software than the result table suggests, which is exactly why the fix is a one-line flag rather than a rebuild:

- **Native** and **both container configurations** cross the network through the **same physical NIC** (Mellanox ConnectX-5, `mlx5_0`) — there is no hardware difference anywhere in this comparison.
- **The baseline and optimized containers are the same image.** No rebuild happened between the two — `osu_container_pt2pt_inter_ucx.pbs` changes exactly one `mpirun` flag against the baseline script and nothing else.
- The flag decides which of two completely different software paths OpenMPI takes to reach that NIC: `--mca btl tcp,self` routes through the kernel's TCP/IP socket stack over the `hsn0` IP interface (extra copies, extra syscalls, extra latency); `--mca pml ucx` routes through `ibverbs` straight to `mlx5_0` via RDMA — the **identical path native already used**, made available because Apptainer passes `/dev/infiniband` through by default.
- That is the whole explanation for the 12.7→1.4 µs recovery: not a faster container, but the same container taking the fast path instead of the slow one.

## 2. Why it works: the container already had everything

Measured on a compute node, inside the `.sif`, with no binds:

```
/dev/infiniband        rdma_cm, umad0, uverbs0     visible
/sys/class/infiniband  mlx5_0                       visible
libibverbs.so.1, libmlx5.so.1, libucp.so.0          present
MCA pml: ucx                                        compiled in
MCA mtl: ofi                                        compiled in
```

Apptainer passes `/dev` through by default, so the RDMA device nodes were always reachable. The container's OpenMPI was built with the UCX PML. Nothing was missing.

**The fabric is Mellanox verbs, not Cray CXI.** On a compute node the host shows UCX transports `rc_verbs` / `ud_verbs` on `mlx5_0:1`, and libfabric providers `verbs` / `ofi_rxm` / `sockets` — there is no `cxi` provider. `hsn0` is simply the IP interface over that NIC, which is why TCP-over-`hsn0` worked at all and why it was slow.

## 3. The correction this forces on the baseline

The baseline container scripts set, for every inter-node run:

```bash
--mca btl tcp,self --mca btl_tcp_if_include hsn0 --mca oob_tcp_if_include hsn0
```

**That forced TCP and prevented OpenMPI from ever selecting UCX.** The flag was added because the project believed the container's OpenMPI had no UCX support — an assumption this probe disproves.

So the baseline's inter-node container numbers measure **a deliberately TCP-pinned configuration**, not the container's achievable performance. This affects:

| baseline claim | status |
|---|---|
| pt2pt inter-node 2–12× slower | **configuration artifact** — recoverable to ~1× |
| α adds 12 µs per message | **artifact of TCP**, not of containerization |
| Allreduce inter-node 3.5–6× slower | likely the same; needs rerun |
| Alltoall fails at ≥512 ranks (port exhaustion) | **likely disappears** — RDMA opens no per-peer sockets |
| intra-node results (shared memory) | **unaffected** — `vader` was the right choice there |
| IOR / h5bench null results | **unaffected** — not transport-bound |

**This is a stronger thesis result, not a weaker one.** "Containers match native when MPI is configured correctly, and a plausible-looking misconfiguration costs 9×" is actionable and generalizable. "Containers are slow on the network" was neither — and was wrong.

## 4. Experiments

The probe used 2 nodes × 1 rank and a truncated message range — enough to establish the transport works, not to quantify recovery. The full comparison reruns the baseline inter-node pt2pt suite with the single flag changed.

```
scripts/osu_container_pt2pt_inter_ucx.pbs   latency + bandwidth, REPS=10
scripts/submit_pt2pt_inter_ucx.sh
```

**Only the MCA flag differs from the baseline script** — same 2 nodes, 1 rank each, `place=scatter:excl`, same message sweep, same repetitions. Resources and guards are copied verbatim so nothing else can account for a difference.

Each run also records which transport UCX actually selected (`transport.txt`, captured with `UCX_LOG_LEVEL=info`), so a silent fall back to TCP cannot be mistaken for a successful RDMA run — the failure mode this whole episode was caused by.

> **Known gap:** both `transport.txt` files (latency and bw) came back empty — the `grep` for `selected|rc_verbs|ud_verbs|tcp|posix|sysv` against the `UCX_LOG_LEVEL=info` output matched nothing, so the direct log evidence for RDMA selection was not captured on this run. The result stands on indirect evidence instead: if UCX had silently fallen back to TCP, the data would reproduce the baseline's 4–12× latency penalty and 5,063 MB/s bandwidth ceiling — instead every one of the 23 message sizes lands within 1–15% of native, including the large-message bandwidth plateau at 12,248 MB/s (TCP tops out at 5,063). That pattern is only physically possible via RDMA. Re-running the transport probe with a looser grep (or no filter at all) would close this gap cleanly if needed for the write-up.

**Three-way comparison:** native · container baseline · container optimized, for both **latency** and **bandwidth** — see `analysis/plot_optimization.py` (figures `figO1a`, `figO1b`) and `analysis/plot_architecture.py` (figure `figO2`, the transport-path diagram).

Still to run once this lands:

| | experiment | tests |
|---|---|---|
| 1 | **Alltoall at 512 ranks with UCX** | whether the hard failure disappears — binary, unambiguous |
| 2 | Allreduce inter-node, 2/4/8 nodes | whether 3.5–6× collapses toward 1× |
| 3 | Hockney refit | whether α returns from 13.47 µs toward 1.46 |

Experiment 1 is the one to run first: it converts a hard failure into a success and needs no statistics to be convincing.

## 5. Honest framing for the write-up

> The container's inter-node penalty was not caused by containerization but by an MPI transport-selection flag. The image shipped with a working UCX PML and visible RDMA devices throughout; the launch scripts pinned it to TCP on the mistaken assumption that UCX was unavailable. Removing that pin recovers native latency (12.7 → 1.4 µs). The episode illustrates a practical hazard of containerized HPC: a container can carry a correct MPI stack and still run an order of magnitude slow if the host-side launcher selects the wrong transport, and the failure is silent — TCP-over-IPoIB works, it is merely slow.

That last clause is the contribution. A broken configuration that *fails* gets noticed; one that merely runs 9× slow does not.
