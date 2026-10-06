# Cold-read validation results

A **methodology control**, not a case study. It establishes that the in-job read figures from the scaling studies were served from page cache, and gives the true cold-cache read bandwidth.

Method: `../../../scripts/inter_node/cold_read_validation/README.md`

---

## 1. What is usable

**Two of four configurations.** The other two are void — the read job landed on the same nodes as its write job, so those ranks read from cache.

| config | node overlap | cold GiB/s | warm (in-job) | inflation | usable |
|---|---|---|---|---|---|
| container n1 | **0** | **2.13 ± 0.18** | 65.50 | **31×** | ✅ |
| container n2 | **0** | **3.31 ± 0.23** | 3.88 | 1.2× | ✅ |
| native n1 | 1 | 6.67 ± 7.47 | 71.57 | 11× | ❌ void |
| native n2 | 2 | — | — | — | ❌ void |

`node_overlap.txt` must read 0. Anything else means some ranks had the data in local memory.

## 2. The finding — warm reads were never touching Lustre

Container n1, same run, same 20 GiB:

```
write (cold by definition)      1.096 GiB/s
read, in-job (warm)            65.50  GiB/s     <- 60x the write rate
read, separate job (cold)       2.13  GiB/s
```

A read cannot be 60× faster than the write that just produced it on the same hardware. **65.5 GiB/s is memory bandwidth, not storage bandwidth.**

The cold figure (2.13 GiB/s) sits sensibly just above the write rate, which is what you would expect from Lustre.

### The inflation collapses with scale — which is the proof

| nodes | data | warm | cold | inflation |
|---|---|---|---|---|
| 1 | 20 GiB | 65.50 | 2.13 | **31×** |
| 2 | 40 GiB | 3.88 | 3.31 | **1.2×** |

At one node, 20 GiB fits comfortably in a single node's ~440 GB of RAM, so essentially the whole file is still cached. At two nodes the file is 40 GiB and the ranks reading it are spread across twice the memory, so far less of it survives — and the inflation nearly vanishes.

That dependence on *cache capacity* rather than on *node count per se* is the signature of a cache effect. A genuine I/O measurement would not behave this way. **One data point could not have shown this; two can.**

## 3. The failure the control caught

Both native configurations were invalidated by the node-overlap check, twice — the original submission and a resubmission both landed the read job on the write job's nodes:

```
native n1 (attempt 2):  wrote x1001c0s6b1n0    read x1001c0s6b1n0
native n2 (attempt 2):  wrote x1003c4s1b0n0 + x1003c7s1b1n0
                        read  x1003c4s1b0n0 + x1003c7s1b1n0
```

The void native n1 measurement reported **6.67 ± 7.47 GiB/s** — a confidence interval wider than the mean, because some repetitions hit cache and some did not. Without the overlap check that number would have entered the results as
"native reads 3× faster than container", a complete artefact.

**This is not bad luck, it is systematic.** The write job releases its nodes, PBS then releases the read job from its `afterok` hold, and the just-freed nodes are the most available ones. The `afterok` dependency cannot guarantee
disjoint placement.

**The robust fix, not implemented here:** run both phases in a *single* job with 2N nodes, writing on the first N and reading on the last N via explicit hostfiles. That makes disjointness structural rather than probabilistic. It is recorded as the correct approach for anyone repeating this.

## 4. What this supports, and what it does not

**Supported:**

> In-job reads reached 65.5 GiB/s against a write rate of 1.1 GiB/s on the same runs, exceeding what the storage system can deliver and confirming they were served from page cache. A cold-cache measurement on provably disjoint nodes gave 2.13 GiB/s (1 node) and 3.31 GiB/s (2 nodes). In-job read figures are therefore reported as a methodological observation only.

**Not supported:**

- A native-vs-container *cold read* comparison — the native side is void.
- Cold read bandwidth at 4 or 8 nodes, or for strong scaling or collective I/O. Those configurations were not run (see §5).

The methodological claim stands on its own; the read *results* do not.

## 5. Scope, and why it is small

Deliberately 2 node counts × 2 variants. An earlier attempt at full coverage (12 configurations, 48 jobs, 10.5 TiB) failed: the 8-node jobs wrote 1.56 TiB each, 19 ran concurrently, throttled each other on the shared filesystem, and 13 were killed on walltime.

The calibration needs two points that bracket the effect, not scale coverage. A backup script for full coverage exist (`submit_coldread_full.sh`, batched and with 4 h walltime) but is not the default.

## 6. What this hands to the next phases

| observation | Phase 2 question | Phase 3 action |
|---|---|---|
| Cold read (2.13) sits just above write (1.10) at 1 node | Is read genuinely symmetric with write on this filesystem, or is the cold figure still partly cached? Darshan can count actual OST reads | — |
| Native cold reads never obtained (§3) | — | Re-run with the single-job disjoint-node design if a native/container read comparison is needed |
| Inflation 31× at n1, 1.2× at n2 | Does the crossover point track node memory? Worth one more node count to confirm | — |

**For the thesis:** the honest framing is that reads were measured, found to be cache-dominated, and are reported as such — with the cold calibration given for the configurations where it could be verified. That is stronger than silently omitting reads, and stronger than reporting 65 GiB/s.
