# Results — OSU collectives, intra-node scaling

Allreduce and Alltoall across 8 → 128 ranks, all on one node, so every message goes through shared memory and no network is involved. Two scaling studies, each run twice on independent allocations: **80 jobs, all `Exit_status=0`, 400/400 result files, no failures.**

| study | what is held fixed | per-rank message |
|---|---|---|
| **weak** | message size per peer = 64 KiB | constant |
| **strong** | total problem = 8 MiB | shrinks 1024 → 64 KiB |

**The headline is that the two collectives give opposite verdicts, and both are solid.** The container is *faster* on Allreduce at every rank count and 1.7–4.9× *slower* on Alltoall. That contrast is the most informative result in the OSU work, because it identifies **which communication pattern** the container's handicap actually damages.

Setup details: [`../../../scripts/collective/intra_node/`](../../../scripts/collective/intra_node/).

---

## 1. Container slowdown at a glance

Values are container ÷ native, so **>1 means the container is worse**.

| | NP=8 | NP=16 | NP=32 | NP=64 | NP=128 |
|---|---|---|---|---|---|
| weak allreduce | 0.79 | 0.79 | 0.74 | 0.91 | 0.78 |
| strong allreduce | 0.88 | 0.80 | 0.98 | 0.81 | 0.79 |
| weak alltoall | 1.01 | **4.02** | **4.92** | 2.53 | 2.15 |
| strong alltoall | 1.08 | 1.71 | 2.09 | 2.15 | **2.17** |

## 2. Allreduce: the container is consistently faster

Across both studies and all ten configurations, the container runs Allreduce at **0.74–0.98×** native — typically 20% faster. Variance is low on both sides (CV 0.5–5.4%), and the effect reproduced across independent runs, so this is not the unstable "container looks faster" artefact seen in the pt2pt large-message bandwidth.

The mechanism is the same one that makes Alltoall worse, acting in the opposite direction. Allreduce moves only `O(S)` per rank regardless of rank count, so per-message overhead barely matters. What does matter is that native's UCX uses rendezvous with CMA — a kernel-assisted single copy requiring `process_vm_readv` syscalls and control-message handshakes — while the container, having no CMA, simply copies through a shared buffer. At 64 KiB and smaller, the bounce-buffer copy is cache-resident and beats the syscall round trip.

**This is worth stating plainly in the thesis: the container's "broken" shared-memory path is not universally worse. For latency-bound collectives it is actually the faster option on this hardware.**

## 3. Alltoall: the container is 1.7–4.9× slower, and message size is why

Alltoall is the opposite case. Each rank sends a distinct buffer to every peer, so per-rank traffic is `S × P` — the container's per-message overhead is paid `P` times per rank instead of once.

The clearest evidence comes from comparing the two studies **at the same rank count**, where the peer count is identical and only the message size differs:

| at NP=16 | message per peer | container penalty |
|---|---|---|
| weak | 64 KiB | **4.02×** |
| strong | 512 KiB | **1.71×** |

Same 15 peers, same node, 8× larger messages — and the penalty more than halves. **The container's two-copy cost is dominated by per-message overhead, not by raw bytes moved.** That is why Alltoall's many-small-messages pattern is the worst case for it, and it explains why h5bench (large contiguous writes) saw no container penalty at all.

Note also the onset: at NP=8 there is **no penalty** (1.01×), then it jumps to 4.02× at NP=16. NP=8 fits inside a single CCD sharing one L3; NP=16 is the first point where data must cross L3 domains.

## 4. Scaling quality against ideal — native degrades too

Slowdown ratios alone are misleading, because native has its own scaling problems. Normalising each variant to its own NP=8 value:

| native, vs NP=8 | 8 | 16 | 32 | 64 | 128 |
|---|---|---|---|---|---|
| weak allreduce actual | 1.00 | 1.41 | 1.76 | **10.57** | 5.85 |
| *ideal (~log P)* | 1.0 | 1.3 | 1.7 | 2.0 | 2.3 |
| weak alltoall actual | 1.00 | 2.05 | 6.50 | **33.29** | **101.53** |
| *ideal (traffic = S×P)* | 1.0 | 2.0 | 4.0 | 8.0 | 16.0 |

Allreduce tracks its `log P` ideal closely to 32 ranks (1.41 vs 1.3, 1.76 vs 1.7) and then breaks down. Alltoall is near-perfect at 16 ranks (2.05 vs 2.0) and then degrades to **6.3× worse than its own traffic growth predicts** at 128 ranks — that excess is shared-memory contention, not data volume.

This also explains why the weak Alltoall container penalty *falls* from 4.92× at NP=32 to 2.15× at NP=128. The container does not improve: in absolute terms it degrades 215× from NP=8 while native degrades 101×. The ratio compresses only because **native is hitting its own contention wall**. Reporting the falling ratio without this context would badly misrepresent the result.

## 5. Strong Alltoall isolates coordination overhead

Under strong scaling, Alltoall's per-rank traffic works out to `(T/P) × P = T` — pinned at exactly 8 MiB regardless of rank count. A perfectly scaling implementation would therefore be a **flat line**.

| strong alltoall, native | 8 | 16 | 32 | 64 | 128 |
|---|---|---|---|---|---|
| vs NP=8 | 1.00 | 1.77 | 1.96 | 2.01 | 2.28 |

Native plateaus near 8500 µs from NP=32 onward. The residual **~2.3× rise with identical per-rank work is pure coordination overhead**, cleanly separated from data movement. The container shows the same shape at 1.08 → 2.17× the cost, so it pays the same coordination penalty *plus* its per-message copy cost.

## 6. The NP=64 Allreduce anomaly — reproducible, and not the container's fault

Allreduce is **non-monotonic at 64 ranks**, in both studies and both variants:

| | NP=32 | NP=64 | NP=128 |
|---|---|---|---|
| weak native | 82.05 | **493.80** | 273.51 |
| strong native | 265.26 | **1050.04** | 272.82 |
| strong container | 258.79 | **850.27** | 214.54 |

64 ranks costs roughly **4× what either 32 or 128 ranks cost**, with CV of 0.5–1.6%, confirmed across four separate 20-job batches. Under weak scaling NP=128 moves twice the total data in 60% of the time.

**Socket saturation is ruled out by the recorded bindings.** `bindings.txt` shows NP=64 places 64 ranks on socket 0, while NP=128 places 64 ranks on *each* socket — so the per-socket load is identical in both cases. Saturation would predict equal cost, not a 4× difference.

That leaves **OpenMPI's tuned-collective algorithm selection** as the likely cause: it appears to choose a poor Allreduce algorithm at 64 ranks, and both variants inherit it because both are OpenMPI 4.1.2. Confirming this needs an algorithm sweep (`--mca coll_tuned_use_dynamic_rules 1 --mca coll_tuned_allreduce_algorithm <n>`), which is a Phase 2 diagnostic rather than a baseline result.

**It does not compromise the native/container comparison** — both variants hit the same kink, so the ratio at NP=64 (0.81–0.91×) sits in line with every other rank count.

## 7. Why these numbers are trustworthy

**Every study run twice**, on independent allocations. Drift between runs: ≤4% for strong (mostly <2%), ≤1% for weak Alltoall. Slowdown factors reproduce to two decimals (alltoall strong 1.71→1.71, 2.15→2.15).

**The two studies cross-validate.** At NP=128 both use a 64 KiB message, so they must agree — and they do, to within 0.3%:

```
allreduce native     weak 273.51   strong 274.27   +0.3%
allreduce container  weak 212.30   strong 212.18   -0.1%
alltoall  native     weak 9800.83  strong 9782.90  -0.2%
alltoall  container  weak 21031.37 strong 20972.45 -0.3%
```

Two independent sets of 20 jobs landing within 0.3% is strong evidence both are measuring what they claim.

**Guards.** Each job verifies it got exactly one node, that `PBS_NODEFILE` holds exactly NP slots, that the benchmark name is valid, that the binary exists (inside the `.sif` for the container), and that the output contains a data row. Strong scaling additionally checks 8 MiB divides evenly by NP, so no per-rank size is silently truncated.

**Placement recorded, not assumed.** Every job writes `bindings.txt`, `msgsize_bytes.txt` and `nodes.txt`, which is what allowed the socket hypothesis in section 6 to be tested rather than argued.

## 8. What this means for the project

The pt2pt studies showed the container's MPI stack is badly handicapped on the network (2–12×) and only mildly so in shared memory (1.0–1.9×). These collective results sharpen that into a statement about **communication pattern**:

- **Latency-bound, small per-rank data (Allreduce)** — the container is *faster*, because it avoids native's CMA syscall path.
- **Bandwidth-bound, many messages per rank (Alltoall)** — the container is 1.7–4.9× slower, and the penalty scales with how many messages each rank must send.

So "container overhead" is not a single number. It depends on message size and message count, and for some real patterns the sign reverses. That nuance is what makes the h5bench result (no measurable write penalty) consistent with the pt2pt inter-node result (up to 12×) rather than contradictory.

For **Phase 3**, this predicts the bind-mounted-MPI optimisation should help Alltoall-style patterns substantially and may actually *hurt* Allreduce at these message sizes — a falsifiable prediction worth testing.
