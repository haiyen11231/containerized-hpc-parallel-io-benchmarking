# Results — IOR inter-node, strong scaling

1, 2, 4, 8 nodes at 128 ranks per node (128 → 1024 ranks), **total** problem held constant so per-rank work shrinks as nodes are added. 16 configurations per variant, 10 IOR iterations each.

**Same container verdict as the other two IOR studies: nothing consistent.** 6 of 16 configurations resolve at 95%, in both directions (0.69× to 1.42×), median 1.03×. The substantive result is **where strong scaling stops paying off, and that MPI-IO shared-file collapses while POSIX does not**.

Setup: [`../../../scripts/inter_node/strong_scaling/README.md`](../../../scripts/inter_node/strong_scaling/README.md).

---

## 1. Where adding nodes stops helping

Native write bandwidth, MiB/s, total problem fixed:

| config | n1 | n2 | n4 | n8 | 8-node gain |
|---|---|---|---|---|---|
| posix / shared | 1260 | 2344 | 3923 | 7417 | 5.89× |
| posix / fpp | 10840 | 15066 | 15563 | 33467 | 3.09× |
| mpiio / fpp | 9523 | 14796 | 14637 | 23946 | 2.51× |
| **mpiio / shared** | **1284** | **2066** | **2802** | **2896** | **2.26×** |

**MPI-IO shared-file stops scaling entirely past 4 nodes** — 2802 → 2896 MiB/s from 4 to 8 nodes is a 3% gain for twice the hardware. POSIX shared-file on the same problem keeps climbing (3923 → 7417, a 1.89× gain).

That contrast is the clearest API-level result in the IOR work. Both are writing one shared file with the same striping; the difference is the MPI-IO layer. As the total is split across more ranks, each rank's contribution shrinks, and MPI-IO's collective buffering and two-phase aggregation stop being able to assemble usefully-sized writes. POSIX, with no aggregation layer, degrades more gracefully.

**POSIX/FPP shows a plateau too** — 15066 → 15563 from 2 to 4 nodes (3%) — before recovering at 8. With CV of 18–37% in that region, that dip should be read cautiously rather than as a firm feature.

## 2. Container comparison — mixed and unresolved

| | |
|---|---|
| configurations compared | 16 |
| resolvable at 95% | 6 |
| direction of those 6 | **mixed** — 0.69, 0.78, 0.83, 0.87 (container faster); 1.10, 1.12, 1.13, 1.42 (slower) |
| **median slowdown** | **1.03×** |
| CV | median 14% |

The largest single gap is mpiio/shared at 8 nodes, where the container is **0.69×** — i.e. 45% *faster* (4170 vs 2896 MiB/s). Rather than a container advantage, the likelier reading is that this is exactly the configuration where native MPI-IO collapsed (section 1), and that collapse is unstable: native CV there is 29% against the container's 18.5%. Two measurements of a badly-behaving configuration need not agree.

Taken as a whole, with effects on both sides of parity and a median of 1.03×, **no container penalty is demonstrated**.

## 3. Reads are cache-inflated

Same caveat as the other IOR studies — IOR reads back what it just wrote. **Write bandwidth only.**

## 4. Why these numbers are trustworthy

**`place=scatter:excl`** so an N-node job genuinely used N distinct hosts. **Striping pinned and verified** identically in both variants. **`-e`** so writes are fsynced to Lustre, not just to page cache. **`-i 10`** for the statistics via IOR's `Summary of all tests`.

**Caveat:** CV of ~14% bounds the resolvable effect at roughly 15%. This experiment constrains the container penalty rather than proving it zero.

## 5. What the three IOR studies say together

Across intra-node (40 configs), weak (16) and strong (16) — **72 comparisons in total** — the container slowdown has a median of 1.01–1.07× and no consistent direction among the handful that resolve.

That is a substantive negative result, and it is consistent with h5bench reaching the same conclusion independently. Put beside OSU, where the container was up to 12× slower on the network, the combined claim is: **containerization's cost is concentrated in the MPI transport, and bulk parallel I/O is not transport-bound enough to expose it.** The bottleneck for writes is Lustre — locking, metadata, OST bandwidth shared with other users — and the container and native variants hit that same wall.
