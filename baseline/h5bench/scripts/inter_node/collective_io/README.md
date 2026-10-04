# Collective I/O — inter-node

Scale is **fixed at 2 nodes / 256 ranks**. This case study does not vary scale; it varies the two HDF5 collective-I/O switches to isolate their effect.

| `COLLECTIVE_DATA` | `COLLECTIVE_METADATA` | Combo dir |
|---|---|---|
| NO | NO | `dno_mno` |
| NO | YES | `dno_myes` |
| YES | NO | `dyes_mno` |
| YES | YES | `dyes_myes` |

Workload fixed: `DIM_1 = "1 M"` particles/rank × 32 B = 32 MiB per rank per timestep, × 5 timesteps × 256 ranks = **40 GiB per repetition**, 400 GiB per
job at `REPS=10`.

## Why the full 2×2 rather than one on/off switch

The two flags exercise **different mechanisms**, and collapsing them into a
single "collective on/off" would conflate the two:

- **`COLLECTIVE_DATA=YES`** routes data through MPI collective I/O
  (`MPI_File_*_all`). Ranks must communicate to aggregate and reorder writes
  before they reach the filesystem. This is the path where native's
  UCX+Slingshot OpenMPI and the container's generic TCP-over-`hsn0` build
  should diverge most — the direct bridge from the OSU Allreduce findings to
  the I/O benchmarks.
- **`COLLECTIVE_METADATA=YES`** consolidates HDF5 metadata operations through
  one rank instead of all 256 hitting the MDT. This targets Lustre
  metadata-server contention — the mechanism IOR's strong-scaling results
  pointed at when FPP degraded faster than shared-file.

Running all four cells lets you attribute an observed change to the
communication path, the metadata path, or an interaction between them.

## What to look for

The interesting comparison is not any single cell but the **difference of
differences**: how much `COLLECTIVE_DATA=YES` helps (or hurts) natively versus
in the container. If the container gains less from collective data aggregation,
that is direct evidence the MPI transport is the bottleneck — the strongest
result this case study can produce.

## Shared conventions

Access pattern fixed at `CONTIG`/`CONTIG`; `READ_OPTION=FULL`; write and read in
one config so the read finds the file the write just produced; Lustre striping
`-c 4 -S 1m`; hybrid launch model (host `mpirun` + per-rank `apptainer exec`).

Same caveats as the scaling studies — see `../weak_scaling/README.md` for
read-cache inflation, the binary-units-labelled-as-decimal trap, and why CSVs
land under `payload/<variant>/<combo>/<uuid>/`.

 "collective" is doing a lot of hidden work.

Independent vs collective I/O

Independent (the default, COLLECTIVE_DATA=NO): every rank writes on its own, whenever it's ready. 256 ranks → 256 separate streams arriving at Lustre in whatever order they happen to arrive.

rank 0  ──write(32MiB)──→ ╮
rank 1  ──write(32MiB)──→ ├─→  Lustre sees 256 scattered,
  …                       │    possibly unaligned requests
rank 255 ──write(32MiB)──→ ╯

Collective (COLLECTIVE_DATA=YES): all ranks make the call together. Because MPI-IO now knows every rank's intent at once, it can reorganise before touching disk. This is two-phase I/O:

Phase 1 — COMMUNICATION (over the network)
  256 ranks shuffle their data to a few "aggregator" ranks
      rank 0..255  ──MPI messages──→  rank 0, 16, 32, 48 (aggregators)

Phase 2 — I/O (to disk)
  only the aggregators write, each one a big contiguous block
      aggregator ──write(2 GiB contiguous)──→ Lustre

Lustre is fast at large contiguous stripe-aligned writes and slow at many small scattered ones. Two-phase converts the second into the first.

But look at what it costs: Phase 1 is pure network traffic. Collective I/O trades network communication for better disk access patterns.

Why that trade is exactly your thesis question

That trade-off has a completely different price on each side:

┌───────────┬───────────────────────────────────┬────────────────────────────────────────┐
│           │              Network              │           So collective I/O…           │
├───────────┼───────────────────────────────────┼────────────────────────────────────────┤
│ Native    │ UCX + Slingshot — fast            │ cheap trade, should help a lot         │
├───────────┼───────────────────────────────────┼────────────────────────────────────────┤
│ Container │ generic OpenMPI, TCP over hsn0 —  │ expensive trade, may help little or    │
│           │ slower                            │ even hurt                              │
└───────────┴───────────────────────────────────┴────────────────────────────────────────┘

This is the only case study that tests mechanism #1 (MPI runtime overhead) in an I/O context. Intra-node, weak, and strong scaling mostly probe mechanisms #2 and #3 — the storage path. This one takes the exact gap your OSU Allreduce results measured and asks: does it actually matter for real I/O?

The second switch is a different mechanism

COLLECTIVE_METADATA has nothing to do with bulk data. HDF5 metadata is the file's structural bookkeeping — where datasets live, their shapes, B-tree indices, the superblock.

- NO: all 256 ranks independently read the same metadata blocks → 256 requests to the Lustre MDT for identical information.
- YES: one rank reads it, then broadcasts → 1 MDT request + 1 MPI broadcast.

Same shape of trade (filesystem work → MPI communication), but a different stress: metadata is many small latency-bound messages, whereas collective data is few large bandwidth-bound messages. OSU measured both regimes, so both map onto findings you already have.

Why 2×2 instead of one on/off switch

If a single switch flipped both at once and the container looked worse, you couldn't say why — data path or metadata path? The factorial separates them by subtraction:

(NO ,NO )  ← baseline
(YES,NO ) − (NO,NO)  = effect of collective DATA alone
(NO ,YES) − (NO,NO)  = effect of collective METADATA alone
(YES,YES)            = do they interact, or just add up?

Four cheap cells, three independent answers.

What a result would actually look like

Say you get this (illustrative numbers, not predictions):

┌───────────┬──────────┬──────────┬───────────────────────────┐
│           │ (NO,NO)  │ (YES,NO) │ gain from collective data │
├───────────┼──────────┼──────────┼───────────────────────────┤
│ Native    │ 2.0 GB/s │ 3.0 GB/s │ +50%                      │
├───────────┼──────────┼──────────┼───────────────────────────┤
│ Container │ 1.8 GB/s │ 1.9 GB/s │ +6%                       │
└───────────┴──────────┴──────────┴───────────────────────────┘

Read it as a difference of differences. The headline isn't "container is 5% slower" — it's that native gains 50% from collective I/O while the container gains almost nothing. That says the container isn't slower at writing bytes; it's that it can't afford the communication collective I/O depends on. That's a mechanistic explanation tied to a specific root cause you've already independently measured with OSU.

And if the container came out slower with collective enabled — the trade costing more than it saves — that's an even sharper finding, plus a concrete recommendation: disable collective I/O in containerised runs unless the MPI stack is fixed. Which feeds straight into your Phase 3 optimisation (bind-mounting the host MPI).

So when you read these results, don't compare cells across the native/container tables. Compare the gains within each table. That's where the physics is.