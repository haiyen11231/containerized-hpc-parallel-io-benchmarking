# h5bench experiment design

## Shared setup, true everywhere

- **64 ranks/node**. Set by `intra_node/write` and carried through to `inter_node`, so one inter-node tier reproduces the intra-node job exactly.
- **Toolchain differs between native and container, deliberately**: native uses a locally-built HDF5 1.10.7 (`build_hdf5_1107` driver, `intel/2022.0.2` + `openmpi/4.1.2-hpe`, HDF5 lib on `LD_LIBRARY_PATH`). Container uses the native driver's `-p <container-bin-dir>` dispatch into Apptainer, running the container's own generic OpenMPI.
- **The container's OpenMPI genuinely has working UCX for this image** (`--mca pml ucx -x UCX_TLS=^cma`; the `UCX_TLS=^cma` works around Apptainer's user-namespace breaking the CMA single-copy transport). Don't assume "container = no UCX" — verify per image rather than carrying that assumption forward.
- **`place=excl` / `place=scatter:excl` always** — this is a shared, `sharing=default_shared` cluster; without it, results are contaminated by noisy neighbors.
- **Walltime must be `> 2:00:00`** for anything non-trivial, or PBS routes the job into the small, congested `qdev`/`gdev` dev queues regardless of node count requested. Confirmed the hard way: a container job left at `01:00:00` was killed mid-run (`walltime 3622 exceeded limit 3600`) — always check native and container headers actually match.
- **Lustre striping is always explicit** (`lfs setstripe -c <count> -S 1m` on the payload dir, verified after with `lfs getstripe`) — default striping isn't guaranteed stable, and native vs container must see the same layout to be comparable.
- **REPS=10, validated every repetition**: each generated JSON is checked with `python3 -m json.tool` and grepped for leftover `@PLACEHOLDER@` tokens before the driver runs, with `sleep 5` between reps to let I/O settle.
- **Write only, by default.** Write-then-read in the same h5bench config reads from page cache (the file was written on the same node(s) milliseconds earlier), not Lustre — measured rates have hit 100+ GB/s, physically impossible for this filesystem. Treat any read-after-write-in-one-config number as suspect until proven otherwise.

## 1. Intra-node (`scripts/intra_node/`)

- Single node, `select=1`, 64 ranks, `place=excl`.
- `write/contig_contig` and `write/interleaved_contig`: fixed 2D dataset (2048×2048, 10 timesteps, 80 GB total), isolating `MEM_PATTERN`/`FILE_PATTERN` (contiguous vs. interleaved) from every other variable.
- At any moment the 64 ranks are only actively pushing one timestep's worth of data (~8 GB, ~125 MB/rank) — comfortably inside the 64 GB job memory limit, so memory pressure never confounds the measurement.

## 2. Inter-node (`scripts/inter_node/`)

Both studies below reuse `intra_node/write/contig_contig`'s exact per-node job (2048×2048, `CONTIG`/`CONTIG`, 10 timesteps) as their 1-node baseline — one node running either script **is** that intra-node job.

### Weak scaling
Per-node workload held constant; 1/2/4/8 nodes → 80/160/320/640 GB total. Tests whether the native/container gap widens as the job scales out.

### Strong scaling
Total problem size held constant at 80 GB; `DIM_1` halves as node count doubles (2048→1024→512→256), keeping `ranks × DIM_1 × DIM_2` fixed. Tests whether added parallelism actually speeds up a fixed-size job, and whether that holds the same way for both variants.

### Both studies
- Lustre stripe count doubles with node count (2/4/8/16) — rank count (concurrent writers) doubles each tier even for strong scaling, where total bytes don't.
- Submit scripts (`submit_*_job.sh`) chain the four node-count tiers **serially** (`-W depend=afterok:<prev job id>`) — running them concurrently means multiple multi-hundred-GB writes contending for the same OSTs, contaminating every tier's measurement. Don't run the native and container chains at the same time either, for the same reason.
- `REPS=10` and walltime are hardcoded inside each `.pbs` file itself, not passed at submission — single source of truth, nothing to keep in sync per tier.
