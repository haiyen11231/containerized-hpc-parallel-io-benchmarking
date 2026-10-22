# IOR Baseline Experiment Guide — Native vs. Apptainer Container

This guide documents the full IOR benchmarking pipeline built for this FYP: what each
test tier is for, how every parameter was chosen (and why), the system facts behind
those choices, and the bugs that shaped the final scripts. It answers, inline, the
raw questions originally jotted down while building this (kept in context rather than
deleted, since they were the actual reasoning trail).

---

## 1. System facts this whole pipeline is built around

**Aspire 2A CPU node:** 2× AMD EPYC 7713 ("Milan"), **128 physical cores / 256 with
SMT**, ~440GB usable RAM. `simple_test/` and `intra_node/` request `ncpus=16`/`64`
respectively (smoke test and half-node); `inter_node/{weak,strong}_scaling` request
the **full physical node** (`ncpus=128`, changed from an earlier `ncpus=64` half-node
choice on 2026-10-02 to better reflect realistic full-node HPC usage) — see §2 for why.

**Storage:** Lustre, mounted at `/scratch`, 2 MDTs + 17+ OSTs, ~10.4PB total. This is
the filesystem every test writes to — confirmed by `df -T /scratch` / `lfs df` showing
filesystem type `lustre`, and by `lfs getstripe` succeeding on files under it (a
non-Lustre path would error with "not on a Lustre filesystem").

**place=excl vs place=exclhost:** Checked via `system_diagnose.pbs`'s vnode-granularity
check — querying `pbsnodes -v <hostname>` from inside a running job and counting how
many vnode blocks come back for that one physical host. Result: **1 vnode per physical
host** on this cluster. So "exclusive at the vnode level" (`excl`) already *is*
"exclusive at the whole physical host level" — there's no second physical host hiding
behind the same vnode that `exclhost` would additionally protect against. Conclusion:
`place=excl` is sufficient everywhere in this project; `exclhost` would be a no-op.

**Container runtime:** Apptainer 1.5.0. Native MPI = OpenMPI 4.1.2-hpe (Cray build,
UCX + Slingshot `hsn0`). Container MPI = generic OpenMPI 4.1.2 from Ubuntu 22.04 `apt`
— no UCX support, no Slingshot awareness. This mismatch is the single biggest reason
native and container MPI need *different* `--mca` flags throughout (§5).

---

## 2. PBS directive reference (answers to "why put walltime=00:05:00 / place= / how
define mem?")

```
#PBS -l select=1:ncpus=64:mpiprocs=64:mem=32gb   (intra_node; inter_node uses 128/128/64gb)
#PBS -l walltime=00:30:00
#PBS -l place=excl
#PBS -q normal
```

- **`select=N:ncpus=X:mpiprocs=X:mem=Ygb`** — `N` = number of chunks (= number of
  nodes needed, one chunk per node in every script here). `intra_node` uses
  `ncpus=64` (half a physical node, kept as-is — this tier isn't about full-node
  saturation); `inter_node/{weak,strong}_scaling` use `ncpus=128` (the **full**
  physical node, one rank per physical core, no SMT oversubscription) so the
  multi-node tier reflects how a real HPC job would actually use allocated nodes,
  rather than leaving half of every node idle. `mpiprocs` is always matched 1:1 with
  `ncpus` so every rank gets its own physical core. `mem=32gb` (intra) / `mem=64gb`
  (inter, doubled alongside the rank-count doubling) is a conservative headroom
  request — large enough for IOR's largest per-rank block in this project plus the
  OS/MPI runtime, small enough not to make the job harder to schedule by over-asking
  on a resource that isn't actually the bottleneck (cores are, and `place=excl`
  already reserves the whole node regardless of the `mem` number requested). It is
  **not** derived from a hard calculation — it's set generously above the actual need
  (confirmed empirically: no run has ever shown memory-pressure symptoms, see the
  memory-sufficiency check in project history) and never came close to being hit.

- **`walltime`** — this is PBS's hard kill timer for the job, and it also determines
  **which queue the job routes into** (see §9 for the full routing table discovered
  during queue-congestion debugging). The simple smoke test uses `00:05:00` because
  it's a tiny, single-iteration sanity check (just confirm the toolchain works end to
  end); the sweep scripts use `00:30:00`–`01:00:00` because they run many iterations
  (5 transfer sizes × 10 repetitions for intra-node, for example) back to back in one
  job. Walltime is sized to the *heaviest* combo in a given script's sweep, not the
  average — see §9's walltime-overrun incident for a concrete case where this bit us.

- **`place=excl`** — reserves the whole physical node exclusively for this job, so no
  other job's processes can land on the same host and contaminate CPU/memory/cache
  measurements. Necessary for any benchmark result to be trustworthy on a
  `sharing=default_shared` cluster where nodes are shared by default. For multi-node
  jobs this becomes **`place=scatter:excl`** — see §9 for why plain `excl` silently
  broke multi-node allocation.

- **`-q normal`** — submits to the `normal` *routing* queue, which PBS then
  auto-routes into one of `q1`–`q6`/`qdev`/`qlong` based on the job's `ncpus` and
  `walltime` (not something we pick directly). See §9.

---

## 3. Experiment structure (three tiers, each probing something different)

```
scripts/
  simple_test/              -- toolchain smoke test (1 node, 16 ranks, POSIX only)
  intra_node/                -- 1-node parameter sweep (stripe x API x model x transfer size)
  inter_node/
    weak_scaling/            -- self-contained working dir: scripts, submit drivers, logs/
    strong_scaling/          -- self-contained working dir: scripts, submit drivers, logs/
results/
  intra_node/{native,container}/{posix,mpiio}/...
  inter_node/
    weak_scaling/{native,container}/{posix,mpiio}/...
    strong_scaling/{native,container}/{posix,mpiio}/...
```

Note: `inter_node/{weak,strong}_scaling/` as the top split (regime first) rather than
nesting regime under variant/API/model was a deliberate reorganization (2026-10-02) —
see §9.1's "Regime instance" for the directory-collision bug this also closes. Each
regime subdirectory is now fully self-contained on the remote cluster side too (its
own `.pbs` scripts, submit drivers, `logs/`, and working data all live together),
mirroring the same "one self-contained directory per tier" pattern `simple_test/` and
`intra_node/` already used.

### 3.1 `simple_test/` — toolchain validation, not a real data point

Purpose: confirm the whole chain works (IOR binary runs, Lustre striping applies,
container binds `/scratch` correctly, MPI launches cleanly) **before** trusting any
numbers from the larger sweeps. 16 ranks, `-b 1G -t 4M`, both shared-file and
file-per-process, POSIX only. `system_diagnose.pbs` alongside it dumps CPU topology,
cluster-wide node availability, the vnode-granularity check (§1), and confirms which
MPI/Lustre/kernel versions are actually in effect — a one-time environment fingerprint,
not something rerun per experiment.

### 3.2 `intra_node/` — 1-node sweep: probes mechanism #1 (runtime overhead) in
isolation

Single node, 64 ranks, **no inter-node network path at all** — this isolates pure
MPI-runtime and shared-memory-transport differences between native (UCX-capable) and
container (generic TCP/vader-only) OpenMPI, without any Slingshot fabric variable
mixed in. If container is slower here, the cause has to be the MPI stack or local
shared-memory mechanism, not the network.

**Sweep dimensions:**
- `STRIPE_COUNT ∈ {1, 8}` — two Lustre striping anchors (§6).
- `API ∈ {POSIX, MPIIO}` — two different I/O backends IOR supports, each with
  different cache-bypass mechanics (§7).
- `MODEL ∈ {shared, fpp}` — shared-file (`-F` absent) vs file-per-process (`-F`
  present) access patterns, which stress Lustre locking very differently (shared file
  → lock contention across ranks; fpp → metadata-server load from many small files).
- `T ∈ {64k, 256k, 1m, 4m, 16m}` (inner loop, same job) — transfer-size sweep at fixed
  `B=64m` block size, to find where overhead from small I/O calls disappears as
  transfer size grows.

16 combos total (2 stripe × 2 API × 2 model) × 2 runtimes (native/container) = 32
submitted jobs, each internally sweeping 5 transfer sizes × 10 repetitions.

### 3.3 `inter_node/` — multi-node weak AND strong scaling: probes mechanisms #2+#3
(storage mounting + Lustre interaction) plus reintroduces mechanism #1 over a real
network path

`NODE_COUNT ∈ {1, 2, 4, 8}`, same `API × MODEL` sweep as intra-node, same two
runtimes. **This is the key fact answering "is the core count the same in strong vs.
weak scaling": yes — both sweeps use the identical node-count tiers (1/2/4/8 →
128/256/512/1024 cores, using the full physical node per `NODE_COUNT` — see §1/§2).
The difference is never how many cores are requested; it's how the *data volume* is
distributed across them:**

- **Weak scaling** (`ior_*_inter_weak.pbs`) — fixed **per-rank** block,
  `B=128m` regardless of `NODE_COUNT`. Total dataset *grows* with core count (8× more
  total data at 8 nodes than at 1 node; 16 GiB/node total with the full-node 128
  ranks/node). Tests: does per-rank throughput hold steady as you add more concurrent
  ranks hitting Lustre? (The scaling question "can the system sustain the same
  per-worker rate as it grows".)
- **Strong scaling** (`ior_*_inter_strong.pbs`) — fixed **total** dataset,
  `TOTAL_GLOBAL_MB = 64 * 1024` (64 GiB) regardless of `NODE_COUNT`; per-rank block
  shrinks as `NP` grows (`B_MB = TOTAL_GLOBAL_MB / NP`). Heaviest per-rank case is
  `NODES=1` (512m/rank at `NP=128`); lightest is `NODES=8` (64m/rank at `NP=1024`).
  Tests: does wall-clock time for a *fixed* amount of work shrink proportionally as
  you throw more nodes at it? (The classic "speedup" scaling question.)

Both use `T=4m` fixed (not swept — the transfer-size sweep was already covered
intra-node; inter-node's job is to vary node count, not repeat the transfer-size
sweep) and `STRIPE_COUNT=8` fixed (the "high-bandwidth parallel streaming" anchor from
§6, since multi-node runs are exactly the regime where striping across many OSTs
matters).

32 combos total per scaling type (4 node-counts × 2 API × 2 model × 2 runtimes) = 64
jobs across weak + strong scaling.

---

## 4. Why `--map-by ppr:N:node --bind-to core` (answers "`--map-by core --bind-to
core`???")

`--map-by ppr:N:node` (N=64 for `intra_node`, N=128 for `inter_node`) explicitly
places exactly N ranks per node (matches `mpiprocs`) — this is more explicit/robust
than `--map-by core`, which infers placement from the *detected* core count and can
behave unexpectedly when SMT is enabled (128 physical cores show up as 256 logical
ones) or when `ncpus` requested is less than the node's full core count, as it is for
`intra_node` (64 of 128; `inter_node` requests the full 128, so this particular
ambiguity doesn't apply there, though the explicit `ppr:` form is kept for the same
robustness reasons regardless). `--bind-to core`
pins each rank to one specific physical core for its whole lifetime, preventing the OS
scheduler from migrating ranks between cores mid-run — migration would add
non-deterministic jitter to I/O timing measurements, exactly the kind of noise a
benchmark needs to eliminate.

---

## 5. MPI transport flags — why native and container need different ones

**Native (`ior_native_*.pbs`):**
```
--mca btl ^openib --mca opal_common_ucx_opal_mem_hooks 1 -x UCX_LOG_LEVEL=ERROR
# inter-node adds: --mca pml ucx --mca orte_base_help_aggregate 0
```
- `^openib`: this cluster has **no InfiniBand fabric** at all, so OpenMPI's default
  probe of the `openib` BTL always fails, and every one of the 64 (or more) ranks
  prints a "no cpcs for port" warning. Under many-rank load, OpenMPI's own
  help-message *aggregation* path (meant to collapse duplicate warnings into one) has
  a confirmed internal bug — `ORTE_ERROR_LOG: Data unpack would read past end of
  buffer` in `show_help.c` — that can abort the entire run. Excluding `openib` from
  the probe entirely removes the trigger. This is exactly what crashed the
  `c8/MPIIO/FPP/16m` intra-node iteration before the fix.
- `--mca pml ucx` (inter-node only): forces genuine UCX transport over the real
  Slingshot fabric for actual cross-node communication — meaningful only once there's
  a real network path to use, hence inter-node-only (intra-node traffic never leaves
  shared memory, so there's nothing for UCX to accelerate there).
- `--mca orte_base_help_aggregate 0` (inter-node only): disables the buggy
  aggregation path directly as a second, defensive layer — kept inter-node-only since
  larger rank counts + a genuine network path (vs. intra-node's shared-memory-only
  traffic) has more surface area for some other duplicate-warning trigger beyond the
  one `^openib` already fixes.

**Container (`ior_container_*.pbs`):**
```
# intra-node:
--mca btl vader,self --mca btl_vader_single_copy_mechanism none
# inter-node adds tcp + fabric pinning:
--mca btl vader,tcp,self --mca btl_tcp_if_include hsn0 --mca oob_tcp_if_include hsn0
```
- `vader,self` (intra) / `vader,tcp,self` (inter): the container's generic `apt`
  OpenMPI build has no UCX support at all, so it must fall back to basic BTLs.
  `vader` = shared memory (same-host only); `self` = loopback. **`tcp` must be added
  for inter-node** — `vader,self` alone silently blocks all cross-node
  communication, since vader only ever handles same-host shared memory and there's no
  other transport without it.
- `--mca btl_vader_single_copy_mechanism none`: Apptainer's user-namespace isolation
  breaks OpenMPI's CMA (Cross Memory Attach) single-copy mechanism for intra-node
  shared memory — without this flag, the container run hangs instead of falling back
  to a slower-but-working copy method cleanly. **Required** for any container run to
  complete at all, not just an optimization.
- `--mca btl_tcp_if_include hsn0` / `--mca oob_tcp_if_include hsn0` (inter-node): pins
  all inter-node traffic to the real Slingshot fabric interface. Without this, the
  container's generic OpenMPI can silently try to route over `docker0` — which has an
  **identical IP address on every node** — causing a hang instead of a clean error.
  Confirmed empirically during OSU inter-node container debugging earlier in this
  project; applied here proactively since the failure mode is a silent hang, not a
  fast, diagnosable error.

---

## 6. Lustre striping strategy — two fixed anchors, not a free sweep

```
┌───────────────────────────────────────────────────────────────────┐
│ Fix Stripe Count to 2 Anchor Cases:                                │
│   1. Single Target (-c 1) → Low-bandwidth / metadata-bound baseline│
│   2. Multi Target  (-c 8) → High-bandwidth parallel streaming      │
└───────────────────────────────────────────────────────────────────┘
```
Intra-node sweeps both anchors (`STRIPE_COUNT ∈ {1, 8}`) since it's cheap (1 node) and
the comparison itself — does striping matter more/less under container vs native — is
a direct probe of mechanism #3 (filesystem interaction). Inter-node fixes
`STRIPE_COUNT=8` only: at `NP ≥ 512` (the 8-node strong/weak-scaling case), a large
number of concurrent ranks hitting a single OST (`-c 1`) would bottleneck on that one
storage target's bandwidth/lock contention regardless of node count — `-c 1` was never
going to be a meaningful multi-node data point, so only the "high-bandwidth parallel
streaming" anchor was kept for the node-count sweep (where the actual scaling question
lives). Applied via `lfs setstripe -c <count> -S 1m <dir>` on the payload directory
**before every run**, verified immediately after with `lfs getstripe` printed to the
job log — this is what makes native vs. container results directory-for-directory
comparable (same striping guaranteed, not just assumed from a cluster default that
could silently differ).

Note on the *stripe size* (`-S 1m`, fixed everywhere) vs. **transfer size** (`-t`,
swept 64k→16m intra-node): `-t` is the size of each individual write/read syscall IOR
issues; `-S` is how Lustre physically splits a file's bytes across OSTs. When `-t`
matches or cleanly divides the stripe size, each syscall lands within (or evenly
across) stripe boundaries — e.g. `-t 4M` against `-S 1M` means one 4MiB write call
fills exactly 4 complete, unfragmented stripes. Misaligned sizes (e.g. `-t 1.5M`
against `-S 1M`) cause a single write to straddle a stripe boundary, which can trigger
extra network round-trips to a second OST for a single logical operation. This is why
the intra-node transfer-size sweep was deliberately chosen as a set of sizes (`64k,
256k, 1m, 4m, 16m`) that are all clean multiples of or divisors of the 1m stripe size.

Key relationships:
- **`-np`** determines how many client processes concurrently compete for storage
  locks/bandwidth against the fixed set of OSTs the stripe count spans.
- **`-b`** sets how much data each rank handles; must be large enough that the total
  dataset (`-np × -b`) exceeds node RAM, otherwise the *read* phase measures the Linux
  page cache instead of real Lustre read bandwidth (see §7 for how caching is actually
  bypassed here).
- **`-t`** sets the syscall granularity; larger `-t` means fewer, bigger syscalls
  (less OS/context-switch overhead) and better stripe alignment (above), hence the
  sweep to find where this overhead stops mattering.

---

## 7. Cache bypass: POSIX vs MPI-IO (answers "how do I bypass caching when reading
back a file I've just written")

Every script uses **`-e`** (fsync after write, forces write-phase data to actually
hit disk rather than staying in the write-back cache) and **`-C`** (reorderTasks —
each rank reads back a *different* rank's file/offset than it wrote, specifically so
the read phase can't be silently served from that same rank's own fresh write-back
page cache). This combination is IOR's own documented mechanism for making the read
phase measure real storage, not memory.

An additional O_DIRECT-style bypass exists but is **deliberately disabled** in every
sweep script right now (`DIRECT_IO_FLAG=""`, with the real flags present only as
comments):
```bash
# if [ "$API" == "POSIX" ]; then
#     DIRECT_IO_FLAG="--posix.odirect"
# elif [ "$API" == "MPIIO" ]; then
#     DIRECT_IO_FLAG="-U direct_io=true"
# fi
```
POSIX and MPI-IO bypass caching through genuinely different mechanisms: POSIX has a
real, working flag (`--posix.odirect`, confirmed against `ior -h` on this IOR 4.0.0
build). The MPI-IO equivalent (`-U direct_io=true`) is **not a valid flag at all** in
this build — confirmed empirically, it caused immediate exit-code-1 failures for every
MPIIO combo until removed. There may be a correct ROMIO-hint-based equivalent for
MPI-IO direct I/O, but it hasn't been identified yet, so both are left disabled for
now so native/container and POSIX/MPI-IO stay comparable on equal footing (relying on
`-e -C` alone for cache bypass, which is the same mechanism for both). This is flagged
as a genuinely open item, not a forgotten one — revisit if finer cache-bypass control
turns out to matter during profiling (Darshan/Recorder may show whether `-e -C` alone
is leaving residual cache effects).

---

## 8. `-C` (reorderTasks) combined with shared-file vs. file-per-process — how a
crash was avoided

`-C` makes each rank read back a different rank's data than it wrote — this works
identically under both `MODEL=shared` (one file, ranks read different *offsets* within
it) and `MODEL=fpp` (`-F`, separate files, ranks read a different rank's *file*).
Neither combination is inherently unsafe on its own. The crash this project actually
hit was **not** `-C` interacting with `shared`/`fpp` directly — it was a **directory-
scoping bug** (next section) that happened to surface most visibly in `MODEL=shared`
combos, because shared-file mode means all ranks contend for one file's locks/metadata
at once, making concurrent cross-combo directory contamination fail faster and more
visibly than fpp's many-small-files pattern did.

---

## 9. Bugs found and fixed (the real debugging history — not hypothetical)

### 9.1 `PAYLOAD_DIR` directory-contention bug (found twice, two different scopes)

**The rule:** `PAYLOAD_DIR` must include **every variable the submit script loops
over**, not just some of them. Missing even one dimension lets two concurrently
-submitted jobs share one Lustre directory, so their ranks contend for the same file
locks/metadata path — producing non-deterministic `MPI_ABORT` crashes on random ranks
that look like flaky, unrelated failures.

- **Intra-node instance:** `submit_*_job.sh` loops over `(STRIPE_COUNT, API, MODEL)`,
  but the directory was originally scoped only by stripe count
  (`native/stripe_c${STRIPE_COUNT}`) — every API/model combo at the same stripe count
  shared one directory. Fixed: scope by all three —
  `native/stripe_c${STRIPE_COUNT}/${API_LOWER}_${MODEL}`.
- **Inter-node instance (caught live via `qstat` showing two different node-count
  jobs of the same combo running against the same directory simultaneously):** the
  submit script also loops over `NODE_COUNT`, which wasn't in the path yet. Fixed:
  `native/stripe_c${STRIPE_COUNT}/${API_LOWER}_${MODEL}_n${NODE_COUNT}`.

- **Regime instance (flagged as a latent risk earlier in this project, fixed
  2026-10-02 before it was ever actually hit):** weak and strong scaling computed the
  *same* `PAYLOAD_DIR` pattern for a given `(API, MODEL, NODE_COUNT)` — safe only
  because the two sweeps had never actually been run concurrently. First patched with
  a `_weak`/`_strong` filename suffix, then superseded the same day by a cleaner fix:
  `inter_node/` was reorganized so `weak_scaling/` and `strong_scaling/` are each a
  fully separate, self-contained working directory (own scripts, submit drivers,
  `logs/`, and — since each has its own `PBS_O_WORKDIR` — its own physically separate
  `native/stripe_c.../...` payload tree on Lustre too). With that structural
  separation in place, the filename suffix became redundant and was dropped; the
  directory boundary itself now does the job that string-tagging was working around.
  See §3's directory tree and §11 for the resulting layout.

### 9.2 `place=excl` node-collapse bug (multi-node only)

This was discovered back when `inter_node` requested `ncpus=64` — **half** a physical
128-core node. Under the default `free` placement arrangement, PBS can and did pack
**two** such half-node chunks onto **one** physical host — so every `NODE_COUNT > 1`
job silently got exactly half the distinct physical nodes requested (caught by the
script's own `ACTUAL_NODES` check before any bad data was recorded — no corrupted
results, but the multi-node sweep never actually tested genuine multi-node behavior
until fixed). Fix: `place=excl` → **`place=scatter:excl`**, which forces one chunk per
distinct physical host. Rule going forward: **`scatter` is required whenever a
chunk's `ncpus` is less than the physical node's full core count** — `excl` alone is
not sufficient in that situation.

Note: now that `inter_node` requests the **full** `ncpus=128` per chunk (§1/§2), this
specific collapse mechanism is structurally impossible there regardless of `place`
arrangement — a chunk asking for all 128 cores physically cannot be packed two-per-host
on a 128-core host. `place=scatter:excl` is kept anyway (harmless, still correct, and
`intra_node` isn't affected by this note since it's always single-node).

### 9.3 Invalid `-U direct_io=true` MPI-IO flag

Covered in §7 — confirmed invalid via `ior -h`, caused immediate failures, removed.

### 9.4 Strong-scaling walltime marginal overrun

`NODES=1` + `MODEL=shared` combos (the heaviest per-rank case in strong scaling,
1024m/rank at the original 128GiB total) overran a 30-minute walltime by ~19–21
seconds. Resolved by halving the fixed total dataset to **64 GiB** (→ 1024m/rank at
`NODES=1` becomes the lightest *reduction*, still the heaviest case overall but with
real headroom) and raising walltime to **1 hour**. Confirmed fix: all three previously
-failing combos passed cleanly afterward.

### 9.5 The `NODES=8` strong-scaling queue stall (ongoing, separate from script bugs)

Eight `NODES=8` strong-scaling jobs sat queued in `q5` for 10+ hours with zero
movement, *not* because of anything wrong in the scripts. Root-caused via
`qstat -f <jobid>`'s own `comment` field:
```
comment = Not Running: Insufficient amount of resource: node_pool
```
Cross-checked against `pbsnodes -a` filtered specifically by the
`resources_available.node_pool = ex` resource (the pool `q5`'s
`default_chunk.node_pool = ex` actually draws from — a cluster can show nodes idle
cluster-wide while the *specific pool* a queue draws from is saturated, so always
filter by this resource, not raw idle-node count). This is a genuine, external
scheduling-priority/fairshare condition — other users' jobs ahead of ours for the same
pool — not fixable from our side; the fix is to wait, or submit a smaller interim
ask, not to change our own job's configuration.

**Queue routing fact relevant to this (confirmed directly via `qmgr -c 'print queue
<q>'`):** the `normal` routing queue dispatches into `q1`–`q6`/`qlong`/`qdev` purely by
`ncpus`, **not** walltime, for any job whose `ncpus` falls outside `q1`–`q4`'s ranges:

| Queue | ncpus range | min walltime |
|---|---|---|
| q1 | 1 | > 2h |
| q2 | 2–64 | > 2h |
| q3 | 65–127 | > 2h |
| q4 | 128 | > 2h |
| **q5** | **129–2048** | **none** |
| q6 | 2049+ | none |
| qlong | ≤128 | > 24h |

A 512-ncpus job (8 nodes × 64 cores) only ever fits `q5`'s range — changing its
walltime cannot route it to a different, less congested queue, because `q5` has no
walltime floor to begin with and no other queue's ncpus range covers 512. The only
real effect of a shorter walltime here is a *marginal* scheduling-backfill advantage
(a short job can slot into a gap a long job wouldn't fit), which is why these 8 jobs
were resubmitted with a `-l walltime=00:30:00` **qsub-time override** (not an edit to
the `.pbs` file itself) rather than left at 1 hour — safe specifically because
`NODES=8` is the lightest per-rank case in the whole strong-scaling matrix (least risk
of hitting any walltime ceiling).

Also confirmed directly via `qmgr -c 'print server'`:
```
query_other_jobs = False
```
This cluster does not expose other users' queue position to regular users at all —
`qstat` only ever shows our own jobs, by design (privacy/security policy), so "how many
jobs are ahead of us" / a precise ETA is not something obtainable from user-level
tools on this system. The best available signal is the `comment` field plus
`qstat -B -f`'s server-wide `state_count` (aggregate totals only, no individual job
detail).

---

## 10. Analysis & plotting

Scripts live in `analysis/` (`common.py` holds shared parsing/CI code,
`plot_ior.py` generates the figures into
`analysis/figures/`). Both are safe to re-run at any point during data
collection — a result file with no completed `Summary of all tests:` block
(job still queued, still running, or crashed) is silently skipped, never
faked, so the same script produces a sparse-but-honest set of figures now and
a fuller one later with no code changes.

### 10.1 Why parse IOR's own Summary block, not the per-iteration rows

Every run uses `-i 10` (10 repetitions). Earlier in this project, the parser
used elsewhere (`experiments/ior/analysis/*.py`, an older iteration of this
pipeline) took only the *last completed iteration's* raw row — a single
sample, chosen deliberately at the time to tolerate partially-crashed runs.
That approach cannot support a confidence interval: one sample has no
variance information.

IOR's own `Summary of all tests:` block already reports, per operation
(`write`/`read`): `Mean(MiB)`, `StdDev`, and `reps` (the actual completed
repetition count) — computed by IOR itself across every repetition that
finished. `common.parse_ior_summary()` reads these three columns directly
rather than re-deriving them from the raw rows above. Trade-off made
consciously: if a run was killed before printing this block, that file
now contributes **nothing** (not even a recovered single-sample point),
because a single sample could never support a CI anyway, and mixing
"full 10-rep statistic" points with "one surviving row" points on the same
plot would be misleading rather than honest. This is an acceptable trade-off
now that every known crash cause (§9) has been fixed and the sweeps are
completing cleanly.

### 10.2 Confidence interval method

95% CI half-width = `t(0.975, df=n-1) × StdDev / √n`, where `n` = `reps` from
IOR's own Summary row (always 10 in this project, so `df=9`, `t=2.262`).
`common.t_crit_95()` holds a small lookup table (df 1–30, falling back to the
normal approximation 1.96 beyond that) rather than depending on `scipy`
(not installed in this project's `.venv`) — the project's `-i 10` never
changes, so this table is more than sufficient and keeps the analysis
scripts dependency-free beyond `numpy`/`matplotlib`. A point with `n < 2`
gets a zero-width error bar, which signals "no CI available," never "exact."

Note the read-bandwidth numbers in these result files are frequently
implausibly high (tens of GiB/s on a single rank) despite `-e -C` — this is
very likely page-cache contamination that `-e -C` isn't fully eliminating,
not a measurement bug in the plotting code. §7 already flags the
`O_DIRECT`/MPI-IO cache-bypass gap as open; Darshan/Recorder (Phase 2) are
the intended tools to confirm this root cause before trusting read-bandwidth
figures in the thesis write-up.

### 10.3 Figures and their purpose

**Intra-node (`plot_ior.py`, probes mechanism #1 in isolation — no
network path exists at this tier):**

| Figure | X-axis | Purpose |
|---|---|---|
| `1node_transfer_sweep_stripe{1,8}_{write,read}.png` | Transfer size (64k→16m), 2×2 grid (API×model), native vs container | Finds where per-syscall overhead stops dominating. If container tracks native closely at large `T` but lags badly at small `T`, the gap is a per-syscall/transport overhead (mechanism #1) rather than a hard throughput ceiling. |
| `1node_stripe_bar_t4m.png` | Stripe count (1 vs 8), grouped bars (variant×model), fixed `t=4m` | Direct probe of mechanism #3 — does container benefit from added OST parallelism (`c=1→c=8`) the same way native does, or does striping behave differently under the container's bind-mounted view of `/scratch`? |
| `1node_overhead_heatmap_t4m.png` | Stripe count rows × API/model columns | One-glance comparative summary: container write-overhead % everywhere at once. Means only — a heatmap cell can't legibly show a mean *and* a CI, so this is explicitly a summary view, not the figure to cite for interval precision. |

**Inter-node (`plot_ior.py`, probes mechanisms #2+#3, and reintroduces
#1 over a genuine network path):**

| Figure | X-axis | Purpose |
|---|---|---|
| `multinode_weak_scaling.png` | Node count (1/2/4/8), 2×2 grid (API×model), color=variant, linestyle=write/read | Does per-rank throughput hold steady (ideal = flat line) as concurrent ranks increase? A container line that droops relative to native's flat line as node count grows points at the container's MPI/network path or its Lustre access degrading disproportionately once a real inter-node path is exercised — something the intra-node tier structurally cannot show. |
| `multinode_strong_scaling_bandwidth.png` | Node count, same grid convention | The primary strong-scaling data figure — fixed 64GiB total, does aggregate throughput actually rise as nodes are added, and where does container's curve diverge from native's. |
| `multinode_strong_scaling_efficiency.png` | Node count | The classic HPC "speedup" question in relative terms: each variant's own 1-node run as 100% baseline. **Deliberately has no CI** — efficiency is a ratio of two noisy means, and propagating an honest interval through that ratio needs more care than a quick formula; showing one would overstate precision. Read the raw bandwidth figure above for the real, directly-measured CI on every point this one derives from. |
| `multinode_overhead_heatmap.png` | Regime×node-count rows, API/model columns | Same summary-heatmap purpose as the intra-node version, extended across both scaling regimes — directly comparable side by side. |

---

## 11. Where things stand / data layout reference

- `scripts/simple_test/`, `scripts/intra_node/` — the PBS job scripts and their
  `submit_*.sh` drivers, each tier self-contained with its own `logs/`.
- `scripts/inter_node/{weak_scaling,strong_scaling}/` — same pattern, split one level
  further by regime: each subdirectory holds its own `.pbs` scripts, `submit_*.sh`
  drivers, and `logs/`.
- `results/intra_node/{native,container}/{posix,mpiio}/{shared,fpp}/...` — actual IOR
  output data, organized to mirror the sweep structure exactly.
- `results/inter_node/{weak_scaling,strong_scaling}/{native,container}/{posix,mpiio}/
  {shared,fpp}/ior_n{1,2,4,8}.txt` — same, regime-first to match the scripts layout.
- `analysis/` — `common.py` (shared parsing + 95% CI utilities), `plot_ior.py`,
  and the `figures/` directory it writes into (§10).
