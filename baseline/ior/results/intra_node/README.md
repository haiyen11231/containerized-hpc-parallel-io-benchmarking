# Results — IOR intra-node

64 ranks on one node writing to Lustre, across API × access model × stripe count, each sweeping five transfer sizes. 40 configurations per variant, 10 IOR iterations each.

**The headline is a negative result, and it is a real finding: the container effect is below this experiment's noise floor.** Only 3 of 40 configurations are statistically resolvable at 95%, and two of those three point in *opposite directions* — which is what chance produces across 40 comparisons. The dominant effect in the data is the **access model**, not containerization.

Setup: [`../../scripts/intra_node/README.md`](../../scripts/intra_node/README.md).

---

## 1. What the data actually supports

| | |
|---|---|
| configurations compared | 40 |
| statistically resolvable at 95% | **3** |
| …of which consistent in direction | **no** — 0.90×, 1.42×, 1.55× |
| container slowdown range | 0.78× – 1.55× |
| **median slowdown** | **1.07×** |
| coefficient of variation | **median 25%, max 69%** |

At 40 comparisons with a 95% threshold you expect roughly 2 false positives by chance. Three, with inconsistent direction, is indistinguishable from that. **No container penalty is demonstrated by this experiment.**

The reason is the CV column. Lustre is a shared resource with other users' traffic on the same OSTs, and run-to-run variation of 25% swamps any effect of order 10%. This is a limit of the measurement, not evidence that the container is free — the honest statement is *"any container effect here is smaller than ~25%, which is all this experiment can resolve."*

## 2. What IS resolvable: the access model dominates

| | mean write (MiB/s) |
|---|---|
| **file-per-process** | **4424** |
| **single shared file** | **1277** |
| ratio | **3.5×** |

This is far larger than any container effect and completely consistent across API and stripe count. With one shared file, all 64 ranks serialize on Lustre's distributed lock manager for overlapping extents; with file-per-process each rank owns its file outright and the locking disappears.

**This is the finding IOR contributes to the thesis** — and it is about mechanism #3 (filesystem interaction), measured cleanly, rather than about containers at all.

## 3. Transfer size and stripe count

Neither moves the needle much against 25% noise. Shared-file writes sit between ~1130 and ~1470 MiB/s across all five transfer sizes and both stripe counts — a spread comparable to the variance within a single configuration.

FPP is noisier still (CV up to 69%), which is itself informative: 64 ranks each creating and fsyncing their own file puts heavy, bursty load on the Lustre metadata servers, and MDT response time varies with whatever else is running on the cluster.

## 4. The read numbers are cache-inflated — do not use them

```
same file, same run:   write 1188 MiB/s     read 32678 MiB/s     ->  27x
```

IOR reads back data it has just written, so the reads are served from the node's page cache rather than from Lustre. `-C` reorders tasks so a rank does not read its *own* block, but on a single node every block is still in that node's cache.

**Report write bandwidth only.** A 27× "read advantage" is a measurement artifact, and this is the same trap the h5bench cold-read study was built to address.

## 5. Why the numbers are trustworthy as far as they go

**Striping verified, not assumed.** Every job runs `lfs setstripe -c <N> -S 1m` and then echoes `lfs getstripe` into its log, so native and container provably wrote to identically-striped directories. Without this the comparison would be meaningless.

**`fsync` enforced.** IOR runs with `-e`, so writes are timed to durable storage rather than to the page cache. Without it the write numbers would have the same problem the reads do.

**Node contention removed.** `place=excl` keeps other jobs off the hardware. Filesystem contention cannot be removed on a shared cluster, and section 1's variance is largely that.

**Statistics come from IOR's own `-i 10`**, with mean and standard deviation taken from its `Summary of all tests` block — not from re-running the job, which is how h5bench and OSU do it. Same sample size, different mechanism.

## 6. What this means for the project

This result is **consistent with h5bench**, which also found no measurable container write penalty, and with the OSU findings rather than contradicting them.

The OSU studies showed the container's MPI stack is badly handicapped — up to 12× on the network, 1.7–4.9× for Alltoall-style many-small-message patterns. IOR shows that handicap **does not surface in bulk parallel I/O**, because the bottleneck is Lustre: lock contention, MDT response, and OST bandwidth shared with other users. The MPI transport simply is not on the critical path for writes of this shape.

Stated together, the three benchmarks give the thesis its central claim: *containerization's cost is concentrated in the MPI transport, and is only visible in workloads that are transport-bound. I/O-bound workloads are dominated by the filesystem and show no measurable penalty.*

**A limitation worth stating plainly:** this experiment cannot resolve effects below ~25%, so it establishes an upper bound on the container penalty rather than proving it is zero. Narrowing that bound would need many more repetitions or a quieter filesystem, neither of which is available on a shared production cluster.
