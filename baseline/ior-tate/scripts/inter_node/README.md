# IOR — inter-node weak and strong scaling (TATE)

Node count is the scaling variable: **1, 2, 3 nodes at 16 ranks per node** (16 → 48 ranks), writing to NFS `/home`. Native vs container, Combo A (MPI-IO + Shared + `-c`) vs Combo B (POSIX + FPP + `-e --posix.odirect`). Port of `../../../ior-backup-latest-aspire2a/scripts/inter_node/`; TATE has only 3 nodes, so the sweep is 1/2/3 instead of 1/2/4/8.

## Design

| dimension | weak scaling | strong scaling |
|---|---|---|
| Nodes | 1, 2, 3 | 1, 2, 3 |
| Ranks | 16/node → 16, 32, 48 | same |
| Transfer size (`-t`) | `1m` (fixed) | `1m` (fixed) |
| Block size (`-b`, per rank) | **`16m` fixed** | **768 MiB ÷ NP** → `48m`, `24m`, `16m` |
| Total data per repetition | 256, 512, 768 MiB (grows) | **768 MiB (fixed)** |
| Repetitions (`-i`) | 5 | 5 |
| Runs per data point | 1 | 1 |
| Ideal result | Bandwidth grows with nodes (time per repetition stays flat) | Time per repetition shrinks with nodes |

At 3 nodes the two studies run the exact same configuration (48 ranks × 16m), which gives a built-in consistency check between them. B = 16m also matches the intra-node study.

IOR flags: `-w -t 1m -b $B -m -g -d 5 $API_EXTRA_FLAGS -i 5`.

## One node count per job

Each job requests exactly the nodes it uses (`--nodes`, `--nodelist`, `--exclusive`, 16 tasks/node); the submit scripts set these per node count:

| Nodes | Node list | why |
|---|---|---|
| 1 | `tate01` | Same node as the intra-node study |
| 2 | `tate01,tate03` | Skips `tate02`, which had another user's non-Slurm load on 2026-10-31 |
| 3 | `tate01,tate02,tate03` | All three |

The job checks that Slurm granted `NODE_COUNT` nodes, and logs each node's load before and after the run, so runs affected by background load can be identified.

Time limit: 20 min for every job.

## MPI, network and MPI-IO settings (identical for native and container)

```bash
export OMPI_MCA_pml=ucx                  # UCX or fail
export UCX_POSIX_USE_PROC_LINK=n         # Apptainer userns workaround (intra-node shm)
export UCX_NET_DEVICES=ibp134s0:1        # the only active EDR InfiniBand port
mpirun -np $NP --map-by ppr:16:node --bind-to core -x UCX_POSIX_USE_PROC_LINK -x UCX_NET_DEVICES \
       --mca fs_ufs_lock_algorithm 3 ...
```

- Ranks on the same node talk through shared memory; ranks on different nodes talk over InfiniBand through UCX → libibverbs → mlx5 (`rc_mlx5`, confirmed in `diag/`).
- **`fs_ufs_lock_algorithm 3`**: OpenMPI's MPI-IO layer (OMPIO) by default locks the whole file around every write when the file is on NFS. Writes then take turns, blocked locks are retried with back-off up to 30 s, and across nodes MPI-IO shared runs hang (no repetition finished in 60 min). Algorithm 3 locks only writes that start or end partway through a block; IOR's per-rank blocks are aligned and non-overlapping, so data stays correct. Bisected in `diag/diag_multinode.sbatch` and `diag/diag_mpiio_fix.sbatch`. POSIX runs are unaffected.
- NFS traffic (IOR's file data) also goes over IPoIB on the same `ibp134s0` port, so MPI and file traffic share one 100 Gb/s link per node.
- `mpirun` launches its helper daemons on the other nodes through Slurm, so no hostfile is needed.
- Container runs need `apptainer` on every node; the container script checks this and stops with `FATAL` otherwise. Apptainer 1.4.5 is on all three nodes since 2026-11-01 (verified in `diag/diag_container_multinode.sbatch`, job 152).

## Output

```
logs/ior_<variant>_<weak|strong>_<N>n_<api>_<model>_<jobid>.out/.err
<variant>/<api>/<model>/ior_n<N>.txt              one IOR result per node count
payload/<variant>_<api>_<model>_n<N>_<jobid>/     test files, deleted on exit
```

A job refuses to start if its `ior_n<N>.txt` already exists; move it away to re-run.

## Running it

```bash
cd weak_scaling   && ./submit_weak_jobs.sh          # 1, 2, 3 nodes: 12 jobs
cd strong_scaling && ./submit_strong_jobs.sh        # 12 jobs
./submit_weak_jobs.sh 2                             # one node count only (4 jobs)
```

Native and container for the same (nodes, combo) are submitted back to back.

## Caveats to state in the thesis

- 3 nodes is a very short scaling curve; it can show the trend and whether the container gap changes with node count, not asymptotic scaling.
- All nodes write to one NFS server (`dsaihn01`), which is likely the bottleneck at 2–3 nodes. Flat bandwidth beyond 1 node is a property of the storage, not of MPI or the container.
- MPI-IO results use `fs_ufs_lock_algorithm 3`, not OpenMPI's default; the default-locking behaviour is documented separately (intra-node runs 1–3 and `diag/`).
- `tate01` is also the login node and `tate02` may carry non-Slurm load; `--exclusive` blocks neither.
- Transfer size is fixed at `1m` here, unlike the intra-node sweep (`64k`–`4m`), to keep the scaling variable isolated.
