# IOR — intra-node

64 ranks on a single node writing to Lustre. Native vs container, Combo A
(MPI-IO + Shared) vs Combo B (POSIX + FPP).

## Redesigned from a 2×2×2×5 sweep to a focused 2-combo comparison

The earlier version of this study swept API (`POSIX`/`MPIIO`) × access model
(`shared`/`fpp`) × stripe count (`1`/`8`) × transfer size (5 values) — 8 jobs
per variant, 40 measurements each. That full sweep already answered the
broad question: **the container effect was below the experiment's noise
floor** (median 1.01–1.07×, run-to-run CV 14–25%), while access model
dominated everything else (FPP ≈ 3.5× shared-file). See
`../../ior-backup/scripts/README.md` for the full writeup.

Given that, sweeping every dimension again adds cost without adding
information. This version instead **fixes stripe count/size and narrows to
the two most different combos**, while still sweeping transfer size within
each:

| dimension | value | why |
|---|---|---|
| Stripe count | `4` (fixed) | one representative value, not a 1-vs-8 sweep |
| Stripe size | `1m` (fixed) | matches the `1m` convention used everywhere else in this repo |
| Transfer size (`-t`) | **`1m, 4m` (swept)** | two values for both combos and both variants — the actual variable of interest alongside API+model |
| Block size (`-b`) | `64m` (fixed) | same value for both combos, both variants, every transfer size — reverted back to `64m` from `128m` on 2026-10-25 |

**Combo A: MPI-IO + Shared** (`API=MPIIO`, no `-F`) — the collective,
single-shared-file path.
**Combo B: POSIX + FPP** (`API=POSIX`, `-F`) — the simplest, one-file-per-rank
path. These are the two combos the earlier sweep's own corners suggested are
most different from each other, so they're the clearest place to look for
whether containerization changes the picture.

Dropped from the earlier design: `POSIX+shared` and `MPIIO+fpp` (the other
two cells of the 2×2). Transfer size narrowed further on 2026-10-25, from
`256k`/`1m`/`4m`/`16m` down to just `1m`/`4m` — the 4-value sweep at the
current `128m` block size was hitting `walltime=00:30:00` before finishing
(see "Resources and MPI flags" below): both native and container
`posix_fpp` jobs got killed mid-sweep (native died during `t1m`, container
during `t4m`), never reaching `t16m` at all. Rather than open-endedly bump
walltime for an untested size, the sweep is narrowed to the two values that
already have partial evidence of completing. If this comparison turns up
something worth digging into further, `256k`/`16m`/the dropped combos are
the dimensions to bring back.

## Striping is still pinned explicitly

```bash
lfs setstripe -c 4 -S 1m "$PAYLOAD_DIR"
lfs getstripe "$PAYLOAD_DIR"      # verified, kept in the log
```

Same reasoning as before: Lustre's default striping isn't guaranteed stable,
so without pinning it, native and container runs could silently be writing
to differently-striped directories and the comparison would be meaningless.

## IOR flags

```bash
ior -a "$API" $FPP_FLAG -w -t "$T" -b 64m -m -g -d 5 $API_EXTRA_FLAGS -i 10 -o "$TEST_FILE"
```

| flag | why |
|---|---|
| `-w` | **write test only** — without it, IOR defaults to write *and* read back-to-back; see below for why that matters |
| `-t` | transfer size, swept over `1m, 4m` inside each job |
| `-b 64m` | block size per rank, fixed so only transfer size (and the combo) changes |
| ~~`-C`~~ | **removed 2026-10-25** — `reorderTasks` only affects *readback* ordering, and this benchmark is `-w` (write-only, no read phase), so it was a no-op all along |
| `-m` | `multiFile` — each of the 10 `-i` repetitions gets its own freshly-created file (`..._rep0`, `..._rep1`, ...) instead of all 10 repeating against the same reused file, avoiding any block-allocation-reuse artifact from writing to identical blocks 10 times in a row |
| `-g` | `intraTestBarriers` — all ranks barrier between open/write/close phases, so a straggler rank doesn't skew the measured timing window |
| `-d 5` | `interTestDelay` — 5s pause between each of the 10 repetitions, matching the project's existing `sleep 5`-between-phases convention (not the `30s` sometimes recommended elsewhere — with `-i 10` that's 9 gaps × 30s = 270s/transfer size, which would eat back into the walltime margin `T_SIZES` was just narrowed to protect) |
| `$API_EXTRA_FLAGS` | **API-specific, not the same for both combos.** `MPIIO` gets `-c` (collective I/O). `POSIX` gets `-e --posix.odirect` (`-e` fsync before close, paired here with O_DIRECT rather than applied globally, plus the page-cache bypass). |
| `-i 10` | 10 repetitions inside IOR — this is where the statistics come from |
| `-F` (via `$FPP_FLAG`) | file-per-process for Combo B; absent (Combo A) means single shared file |

**Why `-c` for MPI-IO shared specifically**: independent I/O from 64 ranks to
one shared file is a known worst-case pattern for lock contention — real
applications using MPI-IO's shared-file mode almost always pair it with
collective I/O for exactly this reason. Without `-c`, the measured variance
may partly reflect uncoordinated lock contention rather than the
container/native comparison this study is actually about.

**Why `--posix.odirect` for POSIX+FPP specifically**: without it, writes go
through the local page cache and the only point the data is actually forced
to Lustre is the final `-e` fsync — meaning most of a transfer's measured
"raw write time" is really just a memory copy, with the real storage cost
concentrated (and hidden) in that one final flush. O_DIRECT makes each
write go straight to Lustre, so the measured time reflects actual storage
throughput throughout, not just at close. Verified against a real Lustre
path before adopting (`/tmp` fails `Cannot create file` with O_DIRECT since
tmpfs doesn't support it — not a concern for the actual `/scratch` payload
dirs this script uses).

**`-w` was added after checking an actual prior result file.** Without it,
IOR runs write *and* read in the same invocation, and a real result showed
exactly the cache-inflation artifact the earlier sweep's README already
flagged: `write 2421.71 MiB/s` next to `read 125310.00 MiB/s` — the read
is ~50× the write, served from this node's page cache since the file was
written milliseconds earlier in the same job, not from Lustre. No amount of
`sync`/`rm` timing around the call fixes this, since it happens *inside* the
IOR invocation before any cleanup code runs. `-w` sidesteps it entirely by
never running that read. If a real cold-cache read number is ever needed,
treat it with the same skepticism documented for h5bench
(`../../../h5bench/scripts/intra_node/README.md`'s read-after-write-in-one-job
warning applies identically to IOR's default read).

## Resources and MPI flags

Unchanged from the earlier design — `select=1:ncpus=64:mpiprocs=64:mem=32gb`,
`place=excl`, `walltime=00:30:00`.

**Native MPI_CONFIG now matches h5bench's intra-node write combos exactly**:
`--mca btl ^openib --mca pml ucx --mca orte_base_help_aggregate 0 --mca
opal_common_ucx_opal_mem_hooks 1 -x UCX_LOG_LEVEL=ERROR`. `^openib` excludes
the InfiniBand BTL probe (this system has no InfiniBand; the probe's failure
warning triggers an OpenMPI help-message-aggregation bug at 64 ranks that
aborts the run — confirmed, not speculative) and `pml ucx` forces the
Slingshot-aware UCX point-to-point layer rather than leaving PML selection to
OpenMPI's default, which this script previously omitted.

**Container now uses `--mca pml ucx -x UCX_TLS=^cma`, matching h5bench's
container exactly.** Note this overrides the stance above: `ior-backup`'s
own `scripts/README.md` documented this IOR container's `apt` OpenMPI build
as having *no* UCX ("`--mca btl vader,self` (no UCX in the apt build)"),
based on testing under the old 2×2×2×5 design. If that finding still holds
for this SIF, forcing `pml ucx` here would make OpenMPI fail outright at
startup rather than silently run slower — so a successful run is itself
evidence the earlier finding doesn't (or no longer) applies to this image.
Worth confirming on the first real run rather than assuming either
direction.

**A `sleep 5` now runs between transfer sizes** in both scripts, matching
h5bench's `sleep 5` between reps ("let I/O buffers drain") — the earlier
version of this sweep had no pause between the separate `mpirun` invocations
for each `-t` value.

## Output

```
logs/<job>.out                         PBS job output
<variant>/<api>/<model>/ior_t<T>.txt   one result file per (combo, transfer size)
```

**Payload directory is now per-transfer-size** (`<variant>/<api>_<model>_t<T>/`,
changed 2026-10-25 from a single shared `<variant>/<api>_<model>/` directory
reused across all transfer sizes) — each `-t` value gets its own freshly
`lfs setstripe`'d directory rather than reusing the same one. Each is
`rm -rf`'d immediately after that transfer size's run completes, and the
`EXIT` trap globs away any that are still present if the script exits early
(e.g. a walltime kill mid-sweep) — only the `.txt` result files are kept
long-term.

## Running it

```bash
./submit_native_job.sh       # 2 jobs: MPIIO+shared, POSIX+fpp
./submit_container_job.sh    # 2 jobs
```

64 ncpus with walltime ≤ 2h routes to `qdev`; this study's `00:30:00` stays
there, now narrowed to a 2-value transfer-size sweep per combo (`1m`, `4m`)
instead of the earlier 4-value one. That narrowing was a direct response to
real walltime-exceeded failures at `128m` block size with 4 values (see
above) — `00:30:00` is **still not independently re-verified** for the
2-value sweep specifically; it's a reasonable bet given both failed runs
got at least as far as finishing `1m` before dying, but hasn't been
confirmed to fit cleanly end-to-end. Per `CLAUDE.md`, `qdev` is also a
small/congested dev queue regardless of job size — if `00:30:00` still
proves tight, bumping past 2h would both add margin and move this off
`qdev` onto a production queue.
