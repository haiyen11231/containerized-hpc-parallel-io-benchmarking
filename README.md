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

Benchmarks:
- OSU
- IOR
- Flash-X
- MLPerf Llama 3.1 8B

ASPIRE 2A
  HPC System
  - 768 CPU nodes: 2 × AMD EPYC 7713, 128 cores / node, 512 GB RAM
  - 64 GPU nodes: 4 × NVIDIA A100 40 GB, 64 CPU cores, 512 GB RAM
  - Shared national resource: Up to 10 PFLOPS aggregate
    • ASPIRE 2A is designed for large-scale scientific and engineering workloads.
    • The current NSCC documentation lists CPU, GPU, large-memory and AI GPU resources.


IOR:
go to `scratch` --> mkdir ior
```
wget https://github.com/hpc/ior/releases/download/4.0.0/ior-4.0.0.tar.gz
tar xzf ior-4.0.0.tar.gz
cd ior-4.0.0
find . -maxdepth 1 -iname "configure"
./configure
make
```
build image
for MacOS: using Lima --> consistent with architecture of HPC amd64 (or x86_64)

`sudo apptainer build ior_benchmarks.sif ior_benchmarks.def`
then scp 
`scp ior_benchmarks.sif haiyen02@aspire2antu.nscc.sg:/home/users/ntu/haiyen00/scratch/ior/container`

`#PBS -l place=[arrangement][:sharing][:grouping]`

place=excl --> no other job shares the node/ for testing can removing to queue faster instead of waiting for exclusive node
place=scatter:excl 
when to use and why need to use that? multinode, 1node, container or native

place=excl (single node) 
place=scatter:excl (multi-node)
OSU measures MPI latency/bandwidth
IOR measures Lustre I/O throughput
h5bench measures HDF5 I/O patterns 

excl vs scatter:excl for multi-node: both guarantee no other job shares your nodes; scatter additionally tells PBS to spread the nodes across different physical switches/chassis rather than letting them land on nodes that happen to be topologically adjacent. Your OSU inter-node scripts use scatter:excl because that test is specifically about real network-fabric traversal (hsn0 routing), so topological spread matters. Your IOR multi-node scripts use plain excl — for I/O throughput, "no other job on the node" is the dominant concern, and PBS's select=N (N>1) already forces N distinct physical nodes regardless of scatter, so the extra topology guarantee matters less there. For h5bench, when you build its multi-node scripts, I'd follow the same logic as IOR (plain excl) unless you're specifically testing network-fabric-sensitive collective HDF5 operations, in which case scatter:excl would be the safer default.


need to check in script pbs, how many gb is enough for mem? what are the factors that mem depends on?
- check config
- check mpi version
- number of ost


References
HPC
https://help.nscc.sg/aspire2a/about/ 
https://centers.hpc.mil/users/docs/erdc/carpenterPbsGuide.html 


OSU
https://mvapich.cse.ohio-state.edu/benchmarks/ 
https://ulhpc-tutorials.readthedocs.io/en/latest/parallel/mpi/OSU_MicroBenchmarks/ 

IOR
https://ior.readthedocs.io/en/latest/userDoc/tutorial.html 
https://blog.glennklockwood.com/2016/07/basics-of-io-benchmarking.html 

h5bench
https://h5bench.readthedocs.io/en/latest/index.html 
https://ieeexplore.ieee.org/document/11106079 
https://onlinelibrary.wiley.com/doi/full/10.1002/cpe.8046 
https://escholarship.org/content/qt3nb8f3d7/qt3nb8f3d7_noSplash_24663da61e0a0e9240d7ce461bd1b939.pdf 
https://cug.org/proceedings/cug2021_proceedings/includes/files/pap103s2-file1.pdf 
https://www.proquest.com/openview/20ecfe3586937ac21d936ddea29cadd9/1?pq-origsite=gscholar&cbl=18750&diss=y
https://ieeexplore.ieee.org/document/10701352 

darshan
https://www.nas.nasa.gov/hecc/support/kb/using-darshan-for-io-characterization_681.html 

https://docs.nersc.gov/tools/performance/darshan/ 

recorder 
https://recorder.readthedocs.io/latest/index.html 
https://github.com/uiuc-hpc/Recorder 

Others
