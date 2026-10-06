# Results — OSU pt2pt, inter-node

Two ranks on different nodes, every message crossing the Slingshot fabric. 10 repetitions per configuration, all 4 jobs `Exit_status=0`, 40/40 result files, no failures.

**This is the largest container penalty measured anywhere in this project: 4.4–11.7× on latency and 2.4–11.2× on bandwidth.** Every point in both kernels is statistically resolvable at 95%.

For how the experiment is set up and what each flag means, see [`../../../scripts/pt2pt/inter_node/README.md`](../../../scripts/pt2pt/inter_node/README.md).

---

## 1. Headline numbers

| message size | native latency | container latency | container slower by |
|---|---|---|---|
| 1 B | 1.46 µs | 17.10 µs | **11.7×** |
| 1 KB | 2.64 µs | 15.23 µs | 5.8× |
| 64 KB | 11.32 µs | 86.12 µs | 7.6× |
| 4 MB | 349.73 µs | 1663.15 µs | 4.8× |

| message size | native bandwidth | container bandwidth | container slower by |
|---|---|---|---|
| 1 KB | 3004 MB/s | 362 MB/s | 8.3× |
| 64 KB | 11916 MB/s | 2937 MB/s | 4.1× |
| 4 MB | **12249 MB/s** | **5063 MB/s** | **2.4×** |

Native saturates at ~12.2 GB/s and holds it; the container plateaus at ~5.1 GB/s, roughly 41% of native's ceiling.

## 2. Why — the mechanism is unambiguous here

The two variants differ in exactly one thing, and it is the thing being measured:

| | native | container |
|---|---|---|
| transport | **UCX over Slingshot** (`--mca pml ucx`) | **TCP over `hsn0`** (`--mca btl tcp,self`) |

No files, no storage, identical binary, identical hardware, and the identical pair of nodes. Nothing else could produce a 2–12× gap.

**The shape of the curve shows a per-message cost, not a bandwidth ceiling.** The penalty is worst at the smallest messages (11.7× at 1 B) and falls steadily as messages grow (4.8× at 4 MB). That is the signature of a fixed per-message overhead amortised over more bytes: TCP traverses the kernel network stack on every message — syscalls, socket buffers, protocol processing — while UCX writes to the fabric from user space. At 1 B the message *is* the overhead; at 4 MB it is diluted but never gone.

**The 64 KB discontinuity is the TCP segmentation boundary.** Container latency jumps from 41.01 µs at 32 KB to 86.12 µs at 64 KB — a 2.1× step for a 2× size increase — while native rises smoothly (8.22 → 11.32 µs). The container's slowdown factor spikes back up to 7.6× there after falling to 5.0×. Above this point messages are being fragmented and reassembled by the kernel, a cost native never pays.

**Bandwidth tells the same story from the other side.** The container's slowdown falls monotonically from 11.2× at 1 B to 2.4× at 4 MB, exactly as a fixed per-message cost would predict. Native reaches 97% of its ceiling by 64 KB; the container is still climbing at 512 KB.

## 3. Native's stability is itself evidence

| | native CV | container CV |
|---|---|---|
| bandwidth, ≥64 KB | **0.0%** | 2.0–8.5% |
| latency, ≥256 KB | **0.0–0.3%** | 2.2–7.3% |
| latency, 1–2 B | 0.7–0.9% | **35–37%** |

Native's coefficient of variation is literally 0.0% across 10 independent repetitions at large messages — a hardware-offloaded path with no kernel involvement returns the same answer every time. The container never does better than ~2%, and reaches 35–37% at the smallest latency points, where it is most exposed to kernel scheduling and socket-buffer state.

So the gap is not merely large: native is also far more *predictable*, which matters for any application doing synchronous communication. Note the 1–2 B latency points are the one place the container's own numbers are shaky (CV 35%), so quote the small-message penalty as "roughly an order of magnitude" rather than as 11.7× precisely.

## 4. Why this result is trustworthy

**All four jobs ran on the same node pair** — `x1001c2s2b1n1` and `x1001c2s7b1n1`. Both latency and bandwidth are therefore fully controlled comparisons, with node-to-node variation eliminated rather than argued away.

**Both ranks verified to be on distinct hosts.** Every job wrote `nodes.txt` listing 2 distinct hostnames, and the script aborts if PBS granted fewer. Without that guard, both ranks landing on one host would have silently measured shared memory and reported a spectacularly fast "network" — the failure mode this study is most exposed to.

**Allocation verified.** `place=scatter:excl`, `ncpus` matching `mpiprocs` (project convention), `Exit_status=0` on all four, no `FATAL`/`FAILED` in any log, 40/40 result files.

## 5. What this means for the project

This directly confirms **leading hypothesis #1** from the research plan: the container's generic apt-built OpenMPI has no UCX support and falls back to TCP, and the cost of that fallback on the network path is severe.

It also sets up the contrast with the I/O benchmarks. h5bench found **no measurable container write penalty**, because bulk data transfer to Lustre dominates and dilutes the transport difference. Here, with nothing but transport, the same underlying defect costs 2–12×. Those results are not in conflict — together they say *the container's MPI stack is badly handicapped, but most I/O workloads are not transport-bound enough to expose it.*

That framing is what makes **Phase 3's bind-mount optimisation** worth doing and worth measuring: this study gives the upper bound on how much it could recover.

## 6. Compare with intra-node

Intra-node ([`../intra_node/README.md`](../intra_node/README.md)) removes the network entirely, and the container penalty collapses from 2–12× to 1.0–1.9× — reversing sign at large messages. The network path, not containerisation as such, is where the damage is.
