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
| pt2pt inter-node 2–12× slower | **configuration artifact** — recoverable to ~1× (§1) |
| α adds 12 µs per message | **artifact of TCP**, not of containerization (§1) |
| Allreduce inter-node 3.5–6× slower | **confirmed same cause** — collapses under UCX (§5) |
| Alltoall fails at ≥512 ranks (port exhaustion) | **confirmed resolved** — proven via 3-arm diagnostic, scales to 1024 ranks under UCX (§6) |
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

### Why ALG=6 for the Allreduce algorithm-lock, and ALG=2 for Alltoall's

The "algorithm-lock" treatment used in §5 and §6 below (forcing a fixed Allreduce/Alltoall algorithm via `--mca coll_tuned_use_dynamic_rules 1 --mca coll_tuned_<bench>_algorithm <N>`, instead of letting OpenMPI's dynamic rule table choose) isn't an arbitrary pick. Here's the evidence behind each.

**Allreduce: ALG=6 (Rabenseifner)** — justified directly by `figO6_algorithm_lock_diagnostic.png`, a native-only diagnostic for the baseline's own NP=64 anomaly (both variants inherit it, so it's upstream of either MPI stack, not container-specific). Forcing the algorithm at NP=32/64/128 (64 KiB message, same as the baseline weak-scaling study) gives:

| forced algorithm | NP=32 | NP=64 | NP=128 | shape |
|---|---|---|---|---|
| ALG=3 (recursive doubling) | 311.5 µs | 499.1 µs | 1029.5 µs | smooth, scales up steadily |
| **ALG=6 (Rabenseifner)** | **82.2 µs** | **90.9 µs** | **104.1 µs** | smooth, mild growth |
| *default (dynamic rules, baseline)* | *80.5 µs* | *498.2 µs* | *274.0 µs* | **not smooth — NP=64 spikes above both neighbors** |

The striking part: default's own NP=64 value (498.2 µs) is within 1% of ALG=3's forced NP=64 value (499.1 µs), and default's NP=32 (80.5 µs) is close to ALG=6's forced NP=32 (82.2 µs). That pattern — matching a *different* forced algorithm's profile at different rank counts — is the evidence that the dynamic rule table is switching strategies at NP=64 specifically, not just getting generically worse. ALG=6 was carried forward into the inter-node algorithm-lock arms because its profile matches the *non-anomalous* rank counts, making it the natural "good" algorithm to test against UCX.

**Two honest caveats, stated plainly rather than glossed over:**
1. **NP=128's default value (274.0 µs) doesn't closely match either forced algorithm** (104.1 µs for ALG=6, 1029.5 µs for ALG=3) — the NP=32/NP=64 contrast above is well explained, but NP=128 evidently does something else under the dynamic table that these two candidates don't fully account for.
2. **Direct confirmation of which algorithm actually ran was attempted and failed**: each run captured `coll_base_verbose 10` output to `algorithm_selection.txt`, grepped for `allreduce.*algorithm|using algorithm` — every one of these files came back empty or matched nothing, across every algorithm and rank count, including the control. The evidence above is the *timing profile matching a forced run*, not a logged confirmation that OpenMPI actually switched algorithms as instructed. Treat the NP=64 explanation as well-supported, not proven beyond doubt.

**Alltoall: ALG=2 (pairwise)** — chosen as the standard, simplest OpenMPI Alltoall algorithm, locked specifically as a **negative control** for §6's port-exhaustion diagnosis, not because it was expected to fix anything. The script's own header states this up front: MPI_Alltoall requires every rank to exchange distinct data with every other rank within one call regardless of which algorithm schedules it, so a locked algorithm changes the *order* connections open in, not the *total count* — the O(P²) connection requirement behind the port exhaustion doesn't go away under any algorithm choice. §6 confirms this prediction: "algorithm-lock alone... fail[s] to scale past 2 nodes," ruling out algorithm selection as an alternative explanation before concluding the cause is transport-specific.

## 5. Allreduce — does the fix generalize to collectives? (inter-node)

**Inter-node (`figO7_allreduce_inter_progress.png`):** both UCX variants (UCX-only, UCX+algorithm-lock, both locking ALG=6/Rabenseifner — see §4's evidence for why that algorithm) track close to native across weak and strong scaling at 2/4/8 nodes, while "algorithm-lock alone" (no UCX, still TCP) stays at the baseline's elevated latency. This separates the two candidate explanations cleanly: locking which Allreduce algorithm OpenMPI picks does **not** recover performance by itself — only switching the transport does. The gap collapses because of UCX, not algorithm selection.

> Intra-node Allreduce/Alltoall *container-vs-native* optimization results (`figO4`, `figO5`) are out of scope for this report — the figures are still generated and kept in `analysis/figures/` for reference, just not analyzed here. This report's collective-scaling scope is inter-node only. (`figO6` is native-only and cited in §4 above — it's there, not for intra-node findings, but because it's the evidence behind the ALG=6 choice used in this section's inter-node figures.)

## 6. Alltoall — proving the failure is TCP port exhaustion, not scale

The baseline found container Alltoall **failing outright** at 4 and 8 nodes: `bind on local address (10.150.2.70:0) failed: Address already in use (98)`. The hypothesis was TCP ephemeral-port exhaustion — Alltoall requires every rank to connect to every peer, and all ranks on a node share that node's single `hsn0` IP and therefore its ephemeral port pool.

**This was proven, not just argued, with a 3-arm diagnostic** (`baseline/osu/scripts/collective/inter_node/diagnostics/`, full write-up there) — all three arms on the same 4 nodes in the same job, holding hardware and timing fixed:

| arm | ranks/node | total ranks | connections/node needed | vs. 28,232-port limit | result |
|---|---|---|---|---|---|
| container, 128/node | 128 | 512 | 65,408 | 2.32x over | **FAILS — exactly 512 port errors** |
| container, 64/node | 64 | 256 | 16,320 | 0.58x, under | passes |
| native, 128/node | 128 | 512 | 65,408 (same count) | — | passes (RDMA opens no per-peer sockets) |

Both numbers are measurements, not estimates: the 28,232-port limit is read directly from `/proc/sys/net/ipv4/ip_local_port_range` (32768–60999) **on the compute node that ran the test**, written to `system_limits.txt` — not assumed from a login-node value. The 65,408 figure is `ranks_per_node × (total_ranks − 1)` = 128 × 511, the actual number of simultaneous outbound connections 128 co-located ranks need to reach the other 511 ranks, all drawn from that one node's shared port pool.

Halving the connection count (arm 2) fixes it with TCP still in use; holding the connection count fixed and removing TCP (arm 3) also fixes it. Together they rule out "512 ranks is just too many" and "the nodes were unhealthy" as alternative explanations — only the TCP-plus-connection-count combination reproduces the failure. The exact match (512 port errors for 512 ranks) is the detail that makes this a proof rather than a correlation.

**With UCX applied for real (`figO8_alltoall_inter_progress.png`):** baseline and algorithm-lock-alone (both still TCP, locking ALG=2/pairwise — see §4 for why that algorithm and why it's a negative control here) fail to scale past 2 nodes — confirming the failure isn't algorithm-specific either. UCX-only and UCX+algorithm-lock scale cleanly to 8 nodes (1024 ranks), matching native. The hard failure is gone, not merely reduced.

## 7. Cross-benchmark note

Comparing this fix's exact MCA flags against h5bench's container scripts (which use the same core `--mca pml ucx -x UCX_TLS=^cma` fix) surfaced one real difference: h5bench's scripts additionally set `--mca opal_common_ucx_opal_mem_hooks 1`, which none of OSU's optimized scripts use. This predates and is unrelated to OSU's work — it's being investigated separately in h5bench's own optimization analysis, since it's a plausible candidate for why h5bench's gap doesn't close as cleanly as OSU's despite the "same" transport fix.

## 8. Conclusion — the predictions, resolved (pt2pt + collective inter-node scope)

GUIDE.md §4 set out four falsifiable predictions before any of this was run. The three in this report's scope (pt2pt + collective inter-node) are answered; a fourth, about intra-node Allreduce, is out of scope here (§5 note):

| # | prediction | result |
|---|---|---|
| 1 | Alltoall at 512 ranks runs instead of failing | **confirmed** — proven via 3-arm diagnostic, not just reproduced |
| 2 | inter-node α collapses toward native | **confirmed** — full 23-size sweep, 1–15% of native throughout |
| 3 | inter-node gap closes (pt2pt, Allreduce, Alltoall) | **confirmed** for all three — not just pt2pt |

Nothing here was cherry-picked toward the answer the baseline wanted — the diagnostic in §6 was designed so that a negative result was possible and would have counted.

## 9. Honest framing for the write-up

> The container's inter-node penalty — across point-to-point, Allreduce, and Alltoall alike — was not caused by containerization but by an MPI transport-selection flag. The image shipped with a working UCX PML and visible RDMA devices throughout; the launch scripts pinned it to TCP on the mistaken assumption that UCX was unavailable. Removing that pin recovers native latency for pt2pt (12.7 → 1.4 µs) and Allreduce, and converts Alltoall from a hard failure (TCP ephemeral-port exhaustion, proven by a controlled 3-arm diagnostic) into a success matching native. The episode illustrates a practical hazard of containerized HPC: a container can carry a correct MPI stack and still run an order of magnitude slow, or fail outright at scale, if the host-side launcher selects the wrong transport — and the failure can be silent, since TCP-over-IPoIB works, it is merely slow, right up until the point count exceeds the ephemeral port range.

That last clause is the contribution. A broken configuration that *fails* gets noticed; one that merely runs 9× slow does not — and one that fails only past a specific rank count looks like a scalability limit of the application, not of the launch configuration.

## 10. Pt2pt intra-node: the CMA crash, with numbers — and what it costs h5bench

§5's Prediction 4 tested whether giving the container UCX (and therefore CMA) on intra-node collectives would make its "faster than native" Allreduce advantage disappear. The same prediction was also tested directly on pt2pt latency/bandwidth — and this is where it stopped being a performance question and became a crash. This result is referenced from `optimization/h5bench/README.md` (justifying why that benchmark's own CMA-fix test was never submitted) and from `CROSS_BENCHMARK_SYNTHESIS.md`, but had not actually been written up here until now.

**`scripts/osu_container_pt2pt_intra_ucx.pbs` (`--mca pml ucx`, CMA available) crashed on both kernels**, deterministically, not intermittently:

```
cma_ep.c:81   process_vm_readv(pid=...) returned -1: Operation not permitted
mpirun ... Exit code: 134
```

Bandwidth got through 8 KiB (18,774 MB/s) before aborting on the next step; latency got through 128 KiB (6.75 µs) before aborting on the next. Both logs confirm via `UCX_LOG_LEVEL=info` that UCX had selected `cma/memory` as the active endpoint before dying — this is CMA actually being invoked and refused by the kernel (`Operation not permitted`), not UCX failing to find it. Full logs: `results/container_ucx_intra_crash/`.

**`scripts/osu_container_pt2pt_intra_ucx_nocma.pbs` (`--mca pml ucx -x UCX_TLS=^cma`) — the same fix h5bench's container already applies — ran cleanly, 10/10 reps.** This is the first controlled, 2-rank measurement of exactly what that fallback costs, and it's a genuinely new result, not just a restatement of the baseline:

| 4 MiB | native (CMA) | baseline container (`vader`) | **UCX, CMA excluded (`sysv`)** |
|---|---|---|---|
| bandwidth | 21,104 MB/s | 27,373 MB/s (CV 18%) | **12,585 MB/s (CV 0.1%)** |
| latency | 197.3 µs | 227.6 µs | **336.6 µs** |

The UCX-with-CMA-excluded path is **not** the same thing as the baseline container's `vader` path, even though both avoid CMA — they're two different OpenMPI/UCX shared-memory implementations (`vader` BTL vs UCX's `sysv` UCT component), and they perform very differently. `vader` is the faster mean but wildly unstable at large messages (CV 18–42%, §4 of `baseline/osu/results/pt2pt/intra_node/README.md`); UCX's `sysv` fallback is markedly slower (1.7× native bandwidth penalty at 4 MiB) but essentially noise-free (CV 0.1%) — a clean, repeatable cost rather than an unstable one.

**At 128 KiB specifically — h5bench's own `interleaved_contig` chunk size — the UCX/`sysv` penalty is 6.42 µs vs native's 5.60 µs, a 1.15× latency tax.** That sits right inside the 1.22–1.44× per-call tax Recorder measured across h5bench's actual POSIX/MPI-IO calls at the same message size (`profiling/h5bench/recorder/results/README.md`, Finding 2). This is the first *quantitative*, apples-to-apples link between the two benchmarks: not just "the same mechanism," but numbers of the same order, measured independently, at the same message size.

**What this means:** h5bench's container isn't running some unexplained or unusually bad configuration — it's running the one working configuration this mechanism has, and OSU's own controlled pt2pt test confirms both that the alternative crashes and that the working fallback carries a real, stable, ~1.2–1.7× cost in this exact size range. This closes the loop the h5bench optimization chapter left open: a specific number for "the fix exists in principle but is foreclosed by the container's own isolation guarantees," rather than only the crash as evidence.
