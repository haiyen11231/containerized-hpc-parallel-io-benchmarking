# Results — IOR inter-node, weak scaling

1, 2, 4, 8 nodes at 128 ranks per node (128 → 1024 ranks), per-rank data held constant. 16 configurations per variant, 10 IOR iterations each.

**Same verdict as intra-node: no consistent container effect.** 5 of 16 configurations are statistically resolvable, but they point in both directions (0.75× to 1.41×) with a median of 1.01×. The real result here is **how far Lustre falls short of linear scaling, and that it depends on access model**.

Setup: [`../../../scripts/inter_node/weak_scaling/README.md`](../../../scripts/inter_node/weak_scaling/README.md).

---

## 1. Scaling efficiency — the actual finding

Per-rank work is constant, so 8 nodes should deliver 8× the bandwidth of 1 node. Native write bandwidth, MiB/s:

| config | n1 | n2 | n4 | n8 | 8-node gain | efficiency |
|---|---|---|---|---|---|---|
| posix / shared | 1184 | 2233 | 4428 | 9040 | **7.64×** | **95%** |
| mpiio / shared | 1120 | 1815 | 3313 | 6179 | 5.52× | 69% |
| posix / fpp | 8181 | 12162 | 21873 | 38057 | 4.65× | 58% |
| mpiio / fpp | 6107 | 10236 | 20843 | 33385 | 5.47× | 68% |

**The counter-intuitive result: shared-file scales best, file-per-process scales worst.**

POSIX shared-file reaches 95% of ideal at 8 nodes, while FPP manages 58% — despite FPP being **6.9× faster in absolute terms at one node** (8181 vs 1184 MiB/s).

The explanation is that the two are limited by different things. Shared-file starts slow because 128 ranks per node contend on Lustre's lock manager, but that cost is already paid at n1 and barely grows — so adding nodes adds bandwidth almost linearly. FPP starts fast because each rank owns its file and skips the locking, but at 1024 nodes×ranks it is creating and fsyncing 1024 separate files, and **MDT (metadata server) load grows with rank count**. FPP runs out of metadata headroom before it runs out of OST bandwidth.

**For the thesis this is the useful statement:** the fastest access model at small scale is not the best-scaling one, and the crossover is a metadata limit, not a bandwidth limit.

## 2. Container comparison — nothing resolvable in a consistent direction

| | |
|---|---|
| configurations compared | 16 |
| resolvable at 95% | 5 |
| direction of those 5 | **mixed** — 0.75, 0.91 (container faster); 1.09, 1.09, 1.41 (slower) |
| **median slowdown** | **1.01×** |
| CV | median 18% |

With effects scattered on both sides of parity and a median of 1.01×, there is no evidence of a container penalty in bulk parallel I/O at any scale tested. The mpiio/fpp 8-node point (1.41×, CV 17–29%) is the largest gap but is not corroborated by its neighbors at 1, 2 or 4 nodes.

## 3. Reads are cache-inflated

As with intra-node, IOR reads back what it just wrote, so read figures are served largely from client page cache and are not Lustre read bandwidth. **Write bandwidth only** — see `../../intra_node/README.md` section 4.

## 4. Why these numbers are trustworthy

**`place=scatter:excl`** guarantees chunks land on distinct hosts, so an "8-node" job really used 8 nodes. Without `scatter` PBS could pack them and the scaling curve would be fiction.

**Striping pinned and verified** (`lfs setstripe -c 8 -S 1m`, then `lfs getstripe` into the log) identically for both variants.

**`-e` (fsync)** so writes are timed to durable storage, and **`-i 10`** for the statistics, taken from IOR's own `Summary of all tests`.

**The caveat:** CV of ~18% means this experiment resolves differences of roughly 20% and larger. It bounds the container effect rather than proving it absent.

## 5. Compare with strong scaling

[`../strong_scaling/README.md`](../strong_scaling/README.md) holds the *total* problem fixed instead, asking whether splitting fixed work across more clients still helps. Together they separate "Lustre cannot absorb more data" from "per-rank I/O became too small to be efficient".
