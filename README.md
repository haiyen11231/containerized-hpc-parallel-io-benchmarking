# Containerized HPC Parallel I/O Benchmarking

This repository contains the implementation, experiments, and analysis for my FYP project **“Evaluation of Parallel I/O Performance in Containerized HPC Environments.”**

The goal of the project is to benchmark and evaluate **parallel I/O performance** across different **container runtimes** (Docker, Podman, Singularity) and multiple **storage backends** (local FS, NFS, distributed FS like Lustre if available).

We investigate:

- How containerization impacts **I/O throughput, latency, and scalability**
- Runtime overheads introduced by different container engines
- Effects of mount methods, file system types, caching layers, and concurrency
- Optimization opportunities for HPC container workflows

---

## 📁 Project Structure

## Set up

After ssh into Supercomputer ASPIRE 2A.


## OSU
Native:
Install MPI --> Build OSU --> Run OSU natively
```
brew install open-mpi
mpirun --version
# mpirun (Open MPI) 5.0.9
mpicc --version
# Apple clang version 21.0.0 (clang-2100.1.1.101)
```

Container:
Build OSU container --> Run OSU in Apptainer
