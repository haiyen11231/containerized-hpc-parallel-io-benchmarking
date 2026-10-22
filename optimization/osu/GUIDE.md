# OSU — optimization stage (Phase 3)

Baseline established *what* the container costs and *why*. This stage tests whether the cause can be removed, and whether removing it produces the predicted effect.

---

## 1. The target is one defect, not a search

The baseline did not leave an open question about OSU. The container's OpenMPI is a generic `apt` build with **no UCX support compiled in** — that is a property of the build, verifiable with `ompi_info`, not something inferred from timings. Everything measured follows from it:

| baseline finding | follows from |
|---|---|
| inter-node 2–12× slower | TCP instead of UCX/RDMA |
| α adds 12.0 µs to every message | TCP syscall + kernel stack per message |
| Alltoall **fails** at ≥512 ranks | TCP needs a socket per peer; 65,408 > 28,232 ports |
| Allreduce intra-node 20% *faster* | container avoids native's CMA syscall |

So Phase 3 is not an open-ended optimization search. It is one intervention: **give the container the host's UCX-enabled MPI** and check the four predictions it implies.

## 2. The intervention

**Bind-mount the host MPI at runtime** (CLAUDE.md's named candidate; standard practice — NERSC Shifter, E4S).

```bash
apptainer exec \
  --bind /app/apps/openmpi/4.1.2-hpe:/opt/host-ompi \
  --bind <libfabric path>:/opt/host-libfabric \
  --env LD_LIBRARY_PATH=/opt/host-ompi/lib:/opt/host-libfabric/lib:$LD_LIBRARY_PATH \
  "$SIF" "$BIN" ...
```

**Why this can work:** OpenMPI maintains ABI compatibility within the 4.1.x series, so `libmpi.so.40` from the host satisfies the container binary's link requirement by soname. The binary was compiled against the container's OpenMPI headers but loads whichever `libmpi.so.40` the loader finds first.

**Why it might not — verify before building anything on top:**

| risk | check |
|---|---|
| host libs need deps not present in the container | `ldd` the host `libmpi.so.40`, bind every directory it names |
| glibc mismatch — container is Ubuntu 22.04 (≈2.35), host RHEL 8.5 (≈2.28) | usually fine in this direction (newer glibc runs older libs), but must be tested |
| OpenMPI loads its MCA components from a compiled-in path | may need `OPAL_PREFIX=/opt/host-ompi` |

**Why the simpler alternatives do not work:**

- *Install UCX into the container.* You cannot add UCX to an OpenMPI that was not built with it — the `pml_ucx` component simply does not exist in that build.
- *Rebuild the container's OpenMPI with `--with-ucx`.* Gives UCX, but generic UCX has no Slingshot (CXI) provider, so you would get UCX-over-TCP, not RDMA. Only the host stack has the Slingshot path.

## 3. Step 0 — feasibility, before any benchmarking

Do not write experiment scripts until this passes. One interactive job:

```bash
# A. confirm the defect is where we think it is
apptainer exec "$SIF" ompi_info | grep -c 'MCA pml: ucx'        # expect 0
module load libfabric/1.11.0.4.125 openmpi/4.1.2-hpe
ompi_info | grep -c 'MCA pml: ucx'                               # expect >=1

# B. sonames must match
apptainer exec "$SIF" bash -c 'ls /usr/lib/x86_64-linux-gnu/libmpi.so.*'
ls /app/apps/openmpi/4.1.2-hpe/lib/libmpi.so.*

# C. what else must be bound
ldd /app/apps/openmpi/4.1.2-hpe/lib/libmpi.so.40

# D. does the container see UCX once bound?
apptainer exec --bind /app/apps/openmpi/4.1.2-hpe:/opt/host-ompi \
  --env LD_LIBRARY_PATH=/opt/host-ompi/lib \
  "$SIF" /opt/host-ompi/bin/ompi_info | grep -c 'MCA pml: ucx'   # expect >=1

# E. does a 2-rank job actually run, and on which transport
mpirun -np 2 <bind-mount wrapper> osu_latency -m 1:1024
#   with -x UCX_LOG_LEVEL=info, the log should name a UCX transport
```

**D and E are the gate.** If the container cannot load the host MPI, the whole approach is dead and the fallback is documenting *why* (a legitimate negative result about container portability on Cray systems).

## 4. Four predictions — the actual deliverable

Phase 3's value is not "the container got faster". It is that the baseline's explanation **predicted in advance** what would change, including one counter-intuitive case.

| # | prediction | baseline | optimized | why it matters |
|---|---|---|---|---|
| **1** | **Alltoall at 512 ranks RUNS** | FAILS (port exhaustion) | completes | binary, unambiguous. RDMA needs no per-peer socket |
| **2** | inter-node α collapses | 13.47 µs | → toward 1.46 µs | quantifies how much of the 12 µs was TCP |
| **3** | inter-node gap largely closes | 2–12× | → toward 1× | the headline improvement |
| **4** | **intra-node Allreduce advantage DISAPPEARS** | 0.78× (faster) | → ~1.0× | the container was faster only because it skipped CMA. Give it CMA and the advantage must vanish |

**Prediction 4 is the strongest test.** It predicts the optimization makes the container *worse* at one thing. If the 20% advantage survives, the explanation in the baseline is wrong. A prediction that can embarrass you is worth more than three that cannot.

## 5. Experiments to run — a subset, not the suite

CLAUDE.md says "re-run the full suite". For OSU that is unnecessary: four targeted experiments test all four predictions, and the baseline already holds the comparison data.

| experiment | config | tests |
|---|---|---|
| pt2pt inter-node | 2 nodes, 1 rank/node, full size sweep | 2, 3 |
| Alltoall inter-node | 4 nodes, 128 ranks/node (512 total) | **1** |
| Allreduce inter-node | 2 nodes, 128 ranks/node | 3 |
| Allreduce intra-node | 1 node, 128 ranks | **4** |

**Three-way comparison**: native · container-baseline · container-optimized. The first two already exist — only the third arm is new, so this is ~8 jobs, not 80.

Keep everything else identical to the baseline: `REPS=10`, same message sizes, same `place=excl` / `scatter:excl`, same `ncpus=mpiprocs`. The optimization must be the **only** variable, or the comparison means nothing.

## 6. Reporting

Extend the baseline figures with a third series rather than making new ones:

- **Fig 1A/1C** — add container-optimized; the α plateau should collapse toward native's
- **Fig 2B** — the 512-rank point changes from an X to a data point. That single mark is the clearest result in the project
- **Fig 4** — α and B penalties, three bars per group, before and after

One new figure is justified: **a before/after summary** showing each prediction and whether it held.

## 7. If the bind-mount fails

That is still a result, and worth reporting properly rather than as a gap:

> *Bind-mounting the host MPI is the standard remedy for this defect, but [specific reason — glibc mismatch / MCA path / missing dependency] prevents it on this system. The container's MPI limitation is therefore not trivially removable here, which strengthens rather than weakens the case for building site-specific container images with the vendor MPI stack compiled in.*

Record the exact failure. "We tried X, it failed because Y" is a contribution; "we did not get to it" is not.

## 8. Honest scoping

The one experiment to run if time allows only one is **Alltoall at 512 ranks** (prediction 1). It converts a hard failure into a success, is binary rather than a percentage, and needs no statistics to be convincing.

Prediction 4 is the most intellectually interesting and costs one single-node job — cheap, and it tests whether the baseline's reasoning was actually right.
