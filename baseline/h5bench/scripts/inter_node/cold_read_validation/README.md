# Cold-read validation

A **methodology control**, not a case study. It answers one question: *are the read numbers from the main experiments real?*

Answer: no. This measures the real ones.

---

## 1. The problem, in one table

Every inter-node case study runs `write` then `read` in the same h5bench config. The read starts milliseconds after the write, **on the same nodes**, so Linux serves it from page cache — it never reaches Lustre:

| measured | data | time | implied rate |
|---|---|---|---|
| strong n8 read | 20 GB | 0.12 s | **167 GB/s** |
| weak n1 read | 20 GB | 0.20 s | **98 GB/s** |
| *write, same runs* | *20 GB* | *~18 s* | *~1.1 GB/s* |

Aspire 2A's Lustre cannot deliver 167 GB/s. That is memory bandwidth.

**Re-running the case studies cannot fix this** — it is inherent to write-then-read in one config, and h5bench has no equivalent of IOR's `-C` to defeat caching.

## 2. The fix, in three sentences

1. The **write job** creates N files and leaves them on Lustre.
2. A **separate read job**, submitted with `-W depend=afterok`, reads them. PBS schedules it independently, so it normally lands on **different nodes** whose page cache has never seen this data.
3. It reads **each file exactly once** — reading one file N times would only be cold on the first pass, because that pass fills the cache for the rest.

```
  Job A (write)  ──N files──→  Lustre          [nodes X]
        │ depend=afterok
        ▼
  Job B (read)   ──each file once──→ cold      [nodes Y, disjoint from X]
```

### It checks its own assumption

"Different nodes" is PBS's normal behaviour, not a guarantee. Both jobs dump `$PBS_NODEFILE`; the read job compares them:

```
=== node overlap check ===
  shared     : 0
  OK: no shared nodes, page cache is cold.
```

**`node_overlap.txt` must read 0.** Anything else means some ranks read from cache and that measurement is void. This is the most important output here.

## 3. Scope — deliberately small

Two node counts, both variants. The calibration needs to establish only two things: that warm reads exceed physical capability, and what the true rate is.

| config | nodes | GiB/file | why this one |
|---|---|---|---|
| weak n1 | 1 | 20 | most inflated — 20 GiB fits easily in one node's 440 GB RAM |
| weak n2 | 2 | 40 | less inflated — shows the effect tracks cache capacity |

**4 configs → 8 jobs → ~1.2 TiB** transient at `FILES=10`. Payload is deleted by the read job's `EXIT` trap even on failure.

Two points are enough because the *trend* is the evidence: inflation is largest where the data fits most comfortably in node memory and shrinks as the file spreads across more nodes. That pattern is a cache signature, not an I/O one.

### Why not every configuration

An earlier version covered all 12 configs from all three case studies — 48 jobs and 10.5 TiB. The 8-node jobs wrote 1.56 TiB each, 19 ran concurrently, throttled each other on the shared filesystem, and 13 were killed on walltime. The calibration does not need scale coverage; it needs two points that bracket the effect.

## 4. Output

Per config, under `<variant>/weak_n<N>_dno_mno/`:

| file | meaning |
|---|---|
| `node_overlap.txt` | **0 = trustworthy.** Check this first. |
| `write_nodes.txt` / `read_nodes.txt` | the node lists being compared |
| `read_<i>.log` / `write_<i>.log` | driver output per file |

Measurements are the CSVs under
`payload/weak_n<N>_dno_mno_<variant>/<uuid>/read_<i>.csv`.

## 5. Running it

```bash
./submit_coldread_jobs.sh            # 8 jobs, FILES=10, ~1.2 TiB
FILES=3 ./submit_coldread_jobs.sh    # cheaper check, ~350 GiB
```

Read jobs sit in state `H` until their write partner succeeds — that is the dependency working, not a stall.

The n1 jobs request `walltime=02:30:00` so they reach `q4`. At ≤2 h a 128-core job falls into `qdev`, whose 256-core cap is shared across the whole cluster.

**Run it in the same session as the warm reads it calibrates.** Absolute bandwidth varies ~15% between sessions on this shared cluster, so a cold number from one day against a warm number from another adds avoidable noise.

## 6. How to report it

These are a **calibration**, not a replacement for the warm reads:

> In-job reads measured up to 167 GB/s, exceeding the storage system's physical capability, confirming they were served from page cache. A separate cold-cache measurement on provably disjoint nodes gave X GB/s, which we report as the true read bandwidth.

That turns an artifact into a demonstrated understanding of the methodology — stronger than silently dropping the read results.

**One lesson worth carrying forward:** a tight confidence interval is not evidence of validity. The warm collective-read cells had the tightest CIs in the entire dataset (±0.4 on 4.3) and were still ~4× cache-inflated. Low variance means *consistent*, not *correct*.
