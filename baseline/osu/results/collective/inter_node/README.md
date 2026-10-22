# Results — OSU collectives, inter-node scaling

2, 4, 8 nodes at 128 ranks per node (256 → 1024 ranks), continuing the intra-node study's message sizes so the two join into one curve. 10 repetitions per configuration.

**Two findings, both strong:**

1. **The container's Allreduce *advantage* reverses at the node boundary** — 0.74–0.91× (faster) intra-node becomes 3.5–6.1× (slower) the moment the network is involved.
2. **Container Alltoall does not merely slow down — it fails outright** at ≥512 ranks, through TCP ephemeral-port exhaustion, confirmed by a controlled diagnostic.

Setup: [`../../../scripts/collective/inter_node/`](../../../scripts/collective/inter_node/). Diagnostic: [`../diagnostics/`](../diagnostics/).

---

## 1. Allreduce — the sign flip

Weak scaling, 64 KiB per rank throughout:

| scope | ranks | native µs | container µs | slowdown |
|---|---|---|---|---|
| intra | 32 | 82.05 | 60.86 | **0.74×** |
| intra | 128 | 273.51 | 212.30 | **0.78×** |
| **inter** | **256** | 133.67 | 470.70 | **3.52×** |
| inter | 512 | 150.72 | 860.58 | 5.71× |
| inter | 1024 | 164.55 | 1005.83 | **6.11×** |

Between 128 ranks (one node) and 256 ranks (two nodes), the container goes from **22% faster to 3.5× slower**. Nothing changed except that messages now cross the fabric.

This resolves the question the intra-node study left open. The container's Allreduce advantage was never a general property — it was specific to shared memory, where its bounce-buffer copy beats native's CMA syscall path at these message sizes. Once UCX-over-Slingshot replaces CMA on the native side, the container's TCP fallback has no answer, and the penalty grows with scale (3.5× → 6.1×) as more ranks mean more inter-node messages.

**For the thesis this is the cleanest single demonstration that the container's handicap is specifically a *network transport* handicap**, not a general containerization cost.

## 2. Alltoall — a hard ceiling, not a slowdown

| scope | ranks | native µs | container |
|---|---|---|---|
| intra | 128 | 9 800.83 | 21 031.37 (2.15×) |
| inter | 256 | 100 551.57 | 154 782.67 (1.54×) |
| **inter** | **512** | 340 293.19 | **FAILED** |
| **inter** | **1024** | 1 005 207.13 | **FAILED** |

Both failed cells produced **0 data rows** — pure error output, excluded from analysis rather than averaged in.

The cause is TCP ephemeral-port exhaustion. Alltoall requires every rank to connect to every peer, and all 128 ranks on a node share that node's single `hsn0` IP:

| nodes | ranks | conns/node | vs 28 232 ports |
|---|---|---|---|
| 2 | 256 | 32 640 | 1.16× — survived via `tcp_tw_reuse=2` |
| 4 | 512 | 65 408 | **2.32× — failed** |
| 8 | 1024 | 130 944 | **4.64× — failed** |

**This was confirmed causally, not inferred.** A single diagnostic job ran three arms on the same four nodes within 51 seconds:

| arm | conns/node | port errors | verdict |
|---|---|---|---|
| container, 128 ranks/node (512 total) | 65 408 | 512 | **FAIL** |
| container, **64** ranks/node (256 total) | 16 320 | 0 | **PASS** |
| native, 128 ranks/node (512 total) | 65 408 | 0 | **PASS** |

Arm 2 changes only the connection count and succeeds. Arm 3 runs the *same 512 ranks* that broke the container and succeeds, because UCX/RDMA opens no per-peer sockets. Together these exclude both "the scale is too large" and "the nodes were unhealthy".

> **The container's lack of UCX imposes a hard scalability ceiling on all-to-all communication, not merely a performance penalty.**

That is a qualitatively different claim from "the container is slower", and it is the strongest result in the OSU work.

## 3. Native's own anomaly persists — and it is not the container's

Native Allreduce is **faster at 256 ranks across two nodes (133.67 µs) than at 128 ranks on one node (273.51 µs)**, despite moving twice the total data under weak scaling.

That is physically backwards unless the two cases use different algorithms, and it matches the non-monotonicity already documented intra-node (the NP=64 spike at 493.80 µs, ~4× its neighbors). The consistent reading across both studies is that **OpenMPI's tuned collective selection makes poor choices at certain rank counts on this hardware**, and the hierarchical algorithm it picks for multi-node runs is better than whatever it uses at 64–128 ranks on a single node.

Both variants inherit this, so the native/container comparison stays valid — but the *native* scaling curve should not be presented as smooth. See [`../intra_node/README.md`](../intra_node/README.md) section 6.

## 4. Alltoall's container penalty is milder inter-node — and why

| | container penalty |
|---|---|
| intra, 32 ranks | 4.92× |
| intra, 128 ranks | 2.15× |
| inter, 256 ranks | **1.54×** (weak), 1.73× (strong) |

The penalty *shrinks* once the network is involved, which is not the container improving. At 256 ranks both variants are bottlenecked by the fabric, and native's own Alltoall cost explodes (9 800 → 100 551 µs, a 10× jump for 2× the ranks). The container is still absolutely slower; the ratio compresses because the common bottleneck grows faster than the container-specific one.

Reporting the falling ratio without this context would misrepresent it — the same trap as the intra-node weak Alltoall curve.

## 5. Why these numbers are trustworthy

**Node counts verified per job.** Each writes `nodes.txt` and aborts unless PBS granted exactly the requested count, plus an `awk` check that every host received exactly 128 ranks — an uneven split would load one node's shared memory more than another.

**Failures are recorded as failures.** The four broken cells hold 0 data rows and are excluded, not averaged. The job scripts' row guard is what caught them.

**Variance is low** — CV 0.1–7.0% across every surviving cell, far tighter than the IOR studies, because these runs touch no filesystem.

**Bindings and message sizes recorded** (`bindings.txt`, `msgsize_bytes.txt`, `ranks.txt`) so placement and workload are evidence rather than assumption.

## 6. What this adds to the project

Combined with intra-node, the collective studies now say:

- **Shared memory**: the container is ~20% *faster* for Allreduce, 1.7–4.9× slower for Alltoall — the penalty tracks message *count*, not bytes.
- **Across the network**: the Allreduce advantage inverts to 3.5–6.1× slower, and Alltoall becomes **impossible** beyond 256 ranks.

Set against IOR and h5bench finding no measurable I/O penalty, the thesis claim is now precise and well-evidenced:

> *Containerization's cost is concentrated entirely in the MPI network transport. It is invisible to I/O-bound workloads, can be favorable for latency-bound shared-memory collectives, and becomes a hard functional limit — not just a slowdown — for communication-heavy patterns at scale.*

For **Phase 3**, this makes the bind-mounted-MPI optimization measurable in a new way: it should not merely speed up Alltoall at 512+ ranks, it should make it **run at all**. That is a binary, unambiguous success criterion.
