# Setup on TATE cluster

Setup IOR native
```bash
# Check dependencies version
gcc --version
# gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
ldd --version
# ldd (Ubuntu GLIBC 2.39-0ubuntu8.7) 2.39
mpicc --version
# gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
mpirun --version
# mpirun (Open MPI) 4.1.6
dpkg -l | grep -E "libucx|rdma-core|libibverbs1|libpmix|libopenmpi-dev|openmpi-bin" | awk '{print $2, $3}'
# libibverbs1:amd64 50.0-2ubuntu0.2
# libopenmpi-dev:amd64 4.1.6-7ubuntu2
# libpmix-dev:amd64 5.0.1-4.1build1
# libpmix2t64:amd64 5.0.1-4.1build1
# libucx0:amd64 1.16.0+ds-5ubuntu1
# openmpi-bin 4.1.6-7ubuntu2
# rdma-core 50.0-2ubuntu0.2
apptainer --version
# apptainer version 1.4.5


# Install IOR
wget https://github.com/hpc/ior/releases/download/4.0.0/ior-4.0.0.tar.gz
tar -xvf ior-4.0.0.tar.gz
cd ior-4.0.0
./configure CC=mpicc --prefix=$(pwd)/install
make
make install
```

Package: libopenmpi-dev
What it is: OpenMPI headers (mpi.h) and the mpicc compiler wrapper
Why IOR needs it: Build time. Lets you compile IOR against MPI.
────────────────────────────────────────
Package: openmpi-bin
What it is: OpenMPI programs: mpirun, ompi_info
Why IOR needs it: Run time. Tools to launch MPI jobs and inspect the
MPI build. On TATE you launch with srun, but ompi_info is still
useful for checks.
────────────────────────────────────────
Package: libpmix
What it is: PMIx: the link between Slurm and MPI
Why IOR needs it: When srun --mpi=pmix starts 32 copies of IOR, PMIx
tells each one its rank and how to reach the others. Without it,
ranks don't know they belong to one job.
────────────────────────────────────────
Package: libucx
What it is: UCX: a fast network library that OpenMPI uses underneath
(pml ucx)
Why IOR needs it: Picks the fastest way to move data: shared memory
between ranks on the same node, InfiniBand between nodes.
────────────────────────────────────────
Package: libibverbs1
What it is: The verbs API, the basic interface to an InfiniBand card
Why IOR needs it: UCX uses it to talk to the Mellanox card (ibp134s0).
────────────────────────────────────────
Package: rdma-core
What it is: The InfiniBand system software (drivers' user-space side,
device setup)
Why IOR needs it: Makes the card usable at all. ibv_devinfo and the
card's drivers come from here.
How they connect at run time:

IOR
 └─ OpenMPI (libopenmpi)        ← compiled in via mpicc
     ├─ PMIx (libpmix)          ← srun --mpi=pmix: "you are rank 5 of 32"
     └─ UCX (libucx)            ← moves the data
         ├─ shared memory       (same node)
         └─ libibverbs + rdma-core → InfiniBand card (between nodes)
## Access

`ssh tate` (alias in `~/.ssh/config` → `haiyen02@10.96.183.230:40001`, password auth, no jump host). Needs the NTU network/VPN. ControlMaster keeps the connection for 4h, so later `ssh`/`scp`/`rsync` calls reuse it without a password.

## Architecture

| Layer | TATE | ASPIRE 2A (for contrast) |
|---|---|---|
| Nodes | 3 (`tate01`–`tate03`); **`tate01` is both the login node and a compute node** | 768 CPU + 64 GPU nodes |
| CPU | 2× Intel Xeon Gold 6148 (Skylake-SP), 2×20 cores, SMT on → 80 threads, 2 NUMA nodes | 2× AMD EPYC 7713, 128 cores |
| Usable by Slurm | 76 CPUs/node: 2 cores (CPUs 38-39,78-79) are reserved by `CoreSpecCount=2`, so **38 physical cores** | — |
| Memory | 192 GB/node (8 GB held back by `MemSpecLimit`), `DefMemPerCPU=2000` MB | 512 GB |
| GPU | 2× Tesla V100-PCIe 16GB/node (`gpu:v100:2`) | 4× A100 40GB |
| Interconnect | Mellanox ConnectX-5 (MT4119), **EDR InfiniBand 100 Gb/s**, only `ibp134s0` up (IPoIB `10.128.10.111–113`); `eno1` 1GbE management (`192.168.88.x`) | Slingshot (`hsn0`) |
| OS | Ubuntu 24.04.3, kernel 6.8, glibc 2.39 | RHEL-based + Cray PE |
| Scheduler | **Slurm 23.11.4**, one partition `teaching` (default, max 8h, default 30 min), no accounting DB (`sacctmgr` unusable), `select/cons_tres` + `CR_CORE_MEMORY`, cgroup task binding | PBS Pro |
| PMI | `srun --mpi=pmix` (pmix_v5) or `pmi2`; `MpiDefault` unset, so pass `--mpi=pmix` explicitly | — |
| MPI (native) | **Distro OpenMPI 4.1.6** (`/usr/bin/mpirun`), built `--with-ucx --with-pmix --with-slurm`; UCX 1.16.0, PMIx 5.0.1, libfabric 1.17, rdma-core 50.0. No `module` command (no Lmod) | Cray `openmpi/4.1.2-hpe` + UCX/Slingshot |
| Container runtime | Apptainer 1.4.5 (setuid allowed, overlay/underlay on, user bind on, `mount home = yes`) | Apptainer 1.5.0 |
| Storage | **No Lustre, no `/scratch`, no `lfs`.** `/home` = NFSv4.2 from `dsaihn01:/mnt/tate-home` (3.7 TB, shared with other users, TCP over IPoIB, rsize/wsize 1 MB). Local: 218 GB SATA SSD ext4 on `/` (also `/tmp`), 94 GB `/dev/shm` per node | Lustre `/scratch` |
| Tools on host | git, cmake, wget, curl, python3, strace, perf. No `ucx_info`, Darshan or `quota` | — |

## Implications for porting IOR

1. **Native and container MPI can be identical.** The host runs the stock Ubuntu 24.04 OpenMPI 4.1.6, and the container installs the same apt packages from `ubuntu:24.04`. This removes ASPIRE 2A's main confounder (Cray UCX build vs generic apt build), so any native-vs-container gap here is closer to pure container overhead.
2. **Lustre striping methodology doesn't apply.** Drop `lfs setstripe`/`lfs getstripe`. The I/O targets available are NFS `/home` (shared, the only filesystem visible from all nodes) and the node-local SSD (file-per-process only, never shared across nodes). Results describe NFS/local-disk behaviour, not Lustre, so they are not directly comparable to the ASPIRE 2A numbers.
3. **Rank counts must shrink.** At most 38 cores per node (the ASPIRE 2A runs used 64), and at most 3 nodes for scaling, or 2 if `tate01` is avoided because it is also the login node.
4. **PBS → Slurm mapping.** `place=excl` → `#SBATCH --exclusive`; `select=1:ncpus=N:mpiprocs=N` → `--nodes=1 --ntasks-per-node=N`; `qsub -v A=x` → `sbatch --export=ALL,A=x`; `$PBS_O_WORKDIR` → `$SLURM_SUBMIT_DIR`; `-q`/`-P` → `-p teaching` (no project code). The walltime trick from ASPIRE 2A isn't needed (single partition, max 8h).
5. **Contention.** The NFS server is shared with other users and `tate01` hosts interactive logins, so repeated runs and run-to-run variance matter more here than on ASPIRE 2A.
6. **Image.** `deployment/ior/ior_benchmarks_tate_cluster.def` uses `From: ubuntu:24.04` (the earlier `ubuntu:24.04.3` tag doesn't exist on Docker Hub) and adds `libucx0`, `ucx-utils` and `ibverbs-providers` so the container can drive the InfiniBand HCA.
