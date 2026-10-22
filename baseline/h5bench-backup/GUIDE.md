this is the guide about h5bench baseline experiment for native and container.
Info about the experiment and some note about the command that we use and also the reason behind it
and the info about the system that we use for the experiments!!!

Fixed base configuration

Key: NUM_DIMS / DIM_2 / DIM_3
Value: 1 / 1 / 1
Note: 1-D; unused dims must be 1
────────────────────────────────────────
Key: DIM_1
Value: per case
Note: Per-rank particles = the real size knob
────────────────────────────────────────
Key: TIMESTEPS
Value: 5
Note:
────────────────────────────────────────
Key: EMULATED_COMPUTE_TIME_PER_TIMESTEP
Value: "0 s"
Note: Unit required, space-separated — parse_unit splits on space, so
"0s" misparses
────────────────────────────────────────
Key: MODE
Value: SYNC
Note: No async VOL built
────────────────────────────────────────
Key: READ_OPTION
Value: FULL
Note: Only parallel-safe option
────────────────────────────────────────
Key: CSV_FILE
Value: set
Note: Machine-readable results for your plotting pipeline
────────────────────────────────────────
Key: "file-system": {}
Value: empty
Note: ← see below

Drop the file-system.lustre block from the native JSON too. Right now native calls lfs setstripe internally on every run while the container structurally cannot — that asymmetry is a confound, and it's my leading explanation for the bogus "container is faster" result. Set striping once in the PBS script (lfs setstripe -c 4 -S 1m) for both sides, so they're symmetric. Keep -c 4 -S 1m fixed everywhere.

Sizing: bytes = ranks × TIMESTEPS × DIM_1 × 32. Use DIM_1 = 1048576 (1 M particles = 32 MiB/rank/timestep) as the weak-scaling constant → 20 GiB/node/run, comparable to IOR's 16 GiB/node.

The four case studies

#: 1
Case: Write access pattern (write-only)
Varied: MEM_PATTERN×FILE_PATTERN ∈ {CONTIG,INTERLEAVED}² → 4
Fixed: 1 node, 128 ranks, DIM_1=1M
Probes: Mech #3 — strided/compound vs sequential Lustre access
────────────────────────────────────────
#: 2
Case: Weak scaling
Varied: nodes 1/2/4/8 (128→1024 ranks)
Fixed: DIM_1=1M/rank, CONTIG/CONTIG
Probes: Mech #1+#2 — fixed per-rank burden at growing scale
────────────────────────────────────────
#: 3
Case: Strong scaling
Varied: nodes 1/2/4/8; DIM_1 = 128M/ranks → 1M, 512K, 256K, 128K
Fixed: total = 128 M particles (4 GiB/timestep)
Probes: Mech #3 at HDF5 layer — does IOR's MDS-contention story
reproduce?
────────────────────────────────────────
#: 4
Case: Collective I/O
Varied: COLLECTIVE_DATA×COLLECTIVE_METADATA ∈ {YES,NO}² → 4
Fixed: 2 nodes (256 ranks), DIM_1=1M, CONTIG/CONTIG
Probes: Mech #1 — your bridge to the OSU findings

Case Study 4 is the highest-value one for your thesis narrative: COLLECTIVE_DATA exercises MPI collective communication (where the UCX-vs-generic-OpenMPI gap should appear), while COLLECTIVE_METADATA targets MDS contention — the full factorial separates the two mechanisms instead of conflating them.

Scale: 16 configs × 2 variants = 32 PBS jobs, each looping 5 repetitions internally (h5bench creates a fresh UUID subdirectory per invocation, so repetitions self-separate). Comparable to IOR's 64-job sweep.
┌─────────────────┬────────────────────────────────────┬────────┐
│   Case study    │               Needs                │ Status │
├─────────────────┼────────────────────────────────────┼────────┤
│ 1 — write       │ h5bench_write                      │ ✅     │
│ pattern sweep   │                                    │ built  │
├─────────────────┼────────────────────────────────────┼────────┤
│ 2 — weak        │ write + read                       │ ✅     │
│ scaling         │                                    │ built  │
├─────────────────┼────────────────────────────────────┼────────┤
│ 3 — strong      │ write + read                       │ ✅     │
│ scaling         │                                    │ built  │
├─────────────────┼────────────────────────────────────┼────────┤
│ 4 — collective  │ write + read; COLLECTIVE_* are     │ ✅     │
│ I/O             │ runtime config keys, not build     │ built  │
│                 │ flags                              │        │
└─────────────────┴────────────────────────────────────┴────────┘

native hdf5: https://support.hdfgroup.org/ftp/HDF5/releases/hdf5-1.10/hdf5-1.10.7/src/index.html@C=N%3BO=D.html 

in `/home/users/ntu/haiyen00/scratch/fyp/native/hdf5/`
```bash
module purge
module load libfabric/1.11.0.4.125
module load intel/2022.0.2
module load openmpi/4.1.2-hpe
wget https://support.hdfgroup.org/ftp/HDF5/releases/hdf5-1.10/hdf5-1.10.7/src/hdf5-1.10.7.tar.gz
tar xzf hdf5-1.10.7.tar.gz
cd hdf5-1.10.7
mkdir -p build && cd build

cmake .. \
    -DCMAKE_C_COMPILER=mpicc \
    -DCMAKE_INSTALL_PREFIX=$(pwd)/install \
    -DHDF5_ENABLE_PARALLEL=ON \
    -DBUILD_SHARED_LIBS=ON \
    -DHDF5_BUILD_CPP_LIB=OFF

make -j8
make install

# rebuild h5bench with this version of hdf5
cd $HOME/scratch/fyp/native/h5bench/h5bench
mkdir -p build_hdf5_1107 && cd build_hdf5_1107

export HDF5_DIR=$HOME/scratch/fyp/native/hdf5/hdf5-1.10.7/build/install
export PATH=$HDF5_DIR/bin:$PATH
which h5cc

cmake .. \
    -DCMAKE_C_COMPILER=mpicc \
    -DCMAKE_CXX_COMPILER=mpicxx \
    -DCMAKE_INSTALL_PREFIX=$(pwd)/install \
    -DH5BENCH_ALL=OFF

make -j8
make install

# check
[haiyen02@asp2a-login-ntu01 build_hdf5_1107]$ H5BENCH=$HOME/scratch/fyp/native/h5bench/h5bench/build_hdf5_1107/install/bin/
[haiyen02@asp2a-login-ntu01 build_hdf5_1107]$ ldd $H5BENCH/h5bench_write | grep hdf5
        libhdf5.so.103 => not found
[haiyen02@asp2a-login-ntu01 build_hdf5_1107]$ h5bench --help
bash: h5bench: command not found...
[haiyen02@asp2a-login-ntu01 build_hdf5_1107]$ export LD_LIBRARY_PATH=$HOME/scratch/fyp/native/hdf5/hdf5-1.10.7/build/install/lib:$LD_LIBRARY_PATH
[haiyen02@asp2a-login-ntu01 build_hdf5_1107]$ ldd $H5BENCH/h5bench_write | grep hdf5
libhdf5.so.103 => /home/users/ntu/haiyen00/scratch/fyp/native/hdf5/hdf5-1.10.7/build/install/lib/libhdf5.so.103 (0x00007fedc7bcb000)
```


install h5bench
in hpc in `~/scratch/fyp/native/h5bench/ `
`git clone --recurse-submodules https://github.com/hpc-io/h5bench`

Use system provided by HDF5:
```bash
# Terminal Module Load
module purge
module load libfabric/1.11.0.4.125
module load intel/2022.0.2
module load hdf5/1.12.1-parallel-icc22-ompi4
module swap openmpi/4.1.7-icc24.2.1 openmpi/4.1.2-hpe
module swap intel/2024.2.1 intel/2022.0.2

module list
which mpirun
mpirun --version
```

Compiler: Intel 2022 (intel/2022.0.2).

MPI: Cray OpenMPI (openmpi/4.1.2-hpe).

CMake Compiler Choice: Use Cray's wrappers -DCMAKE_C_COMPILER=cc -DCMAKE_CXX_COMPILER=CC when building h5bench (because of the cmpi tag).

Verify HDF5 parallel wrapper executable path
`which h5pcc`
/app/libs/hdf5/1.10.8-parallel-icc22-cmpi/bin/h5pcc
Check environment variables
`echo $HDF5_DIR`
/app/libs/hdf5/1.10.8-parallel-icc22-cmpi

Move into the cloned h5bench repository directory
`cd h5bench`

Create and enter the build directory
`mkdir -p build && cd build`

[haiyen02@asp2a-login-ntu01 build]$ which mpirun
/app/apps/openmpi/4.1.2-hpe/bin/mpirun
[haiyen02@asp2a-login-ntu01 build]$ mpirun --version
mpirun (Open MPI) 4.1.2

Report bugs to http://www.open-mpi.org/community/help/

Configure CMake with parallel MPI compilers & Install inside your local build folder
```bash
cmake .. \
    -DCMAKE_C_COMPILER=mpicc \
    -DCMAKE_CXX_COMPILER=mpicxx \
    -DCMAKE_INSTALL_PREFIX=$(pwd)/install \
    -DH5BENCH_ALL=OFF
```
Build files have been written to: /scratch/users/ntu/haiyen00/fyp/native/h5bench/h5bench/build

Compile and install
`make -j8` #depends on the number of cores u have
`make install`

verify installation 
`./install/bin/h5bench --help`

run simple test native


---------
based on steps to install natively in ASPIRE2A, then build a .def file --> build image --> scp to aspire2a

how hdf5 works under the scene??? architecture?? to config, do we need to bypass cache??? how

relationship between lustre and hdf5???

how can i design the experiments to examine the overhead of container compared to native parallel io, with scaling and varios key component flags
------

container
-- Found HDF5: /usr/lib/x86_64-linux-gnu/hdf5/openmpi/libhdf5.so;/usr/lib/x86_64-linux-gnu/hdf5/openmpi/libhdf5.so;/usr/lib/x86_64-linux-gnu/libcrypto.so;/usr/lib/x86_64-linux-gnu/libcurl.so;/usr/lib/x86_64-linux-gnu/libsz.so;/usr/lib/x86_64-linux-gnu/libz.so;/usr/lib/x86_64-linux-gnu/libdl.a;/usr/lib/x86_64-linux-gnu/libm.so (found version "1.10.7")  
-- Using HDF5 version: 1.10.7
--    Detected HDF5 subfiling support: 
-- HDF5 VOL ASYNC: OFF
-- Found Python3: /usr/bin/python3.10 (found version "3.10.12") found components: Interpreter 
-- Configuring done
-- Generating done
-- Build files have been written to: /opt/h5bench/build
------------------
module avail hdf5

---------------------------------------- /app/libs/modulefiles -----------------------------------------
hdf5/1.8.17-intel                hdf5/1.12.1-parallel-icc22-cmpi  hdf5/1.12.2-parallel-icc22-cmpi
hdf5/1.10.5                      hdf5/1.12.1-parallel-icc22-ompi4 hdf5/2.0.0-parallel-gcc-cmpi
hdf5/1.10.8-parallel-icc22-cmpi  hdf5/1.12.1-parallel-icc23-cmpi  hdf5/2.0.0-parallel-icc24-ompi
hdf5/1.12.1-nvhpc                hdf5/1.12.1-parallel-icc24-ompi4

The module names on ASPIRE 2A explicitly tell you which compiler and MPI implementation were used to build them:

icc22 / icc23 / icc24: Built with Intel C Compiler (versions 2022, 2023, 2024).

gcc / gcc11: Built with GCC.

cmpi: Built against Cray MPI (which relies on Cray's cc and CC wrappers).

ompi / ompi4: Built against OpenMPI (which uses mpicc / mpicxx).

+-------------------------------------------------------------+
| Layer 3: Application & Libraries (h5bench, Parallel HDF5)   |
+-------------------------------------------------------------+
                              │  (calls Parallel I/O & MPI functions)
                              ▼
+-------------------------------------------------------------+
| Layer 2: MPI Implementation (OpenMPI, Cray MPI / cmpi)     |
+-------------------------------------------------------------+
                              │  (uses underlying C/C++ compiler)
                              ▼
+-------------------------------------------------------------+
| Layer 1: Base C/C++ Compiler (GCC, Intel icc/icx)           |
+-------------------------------------------------------------+


Base Compilers (Layer 1): The fundamental tools that translate C/C++ code into machine code (e.g., GCC gcc/g++ or Intel icc/icx).

MPI Wrappers (Layer 2): MPI is not a standalone compiler; it is a communication library. Tools like mpicc, mpicxx, or Cray’s cc/CC are smart wrappers. They call your Layer 1 compiler under the hood while automatically attaching MPI headers (mpi.h) and network drivers (libfabric, UCX, Slingshot).

Parallel HDF5 & h5bench (Layer 3): High-level scientific libraries built using the Layer 2 MPI wrapper.

The Golden Rule of HPC ABI CompatibilityRule: You must compile your application (h5bench) using the exact same compiler family and MPI wrapper that were used to build the loaded Parallel HDF5 library.The Conflict: If hdf5/1.10.8-parallel-icc22-cmpi was built with Intel (icc22) and Cray MPI (cmpi), but you try to compile h5bench using GCC (gcc/11.4.0-nscc), two different C++ runtime libraries (libstdc++ vs. Intel libimf/libsvml) try to manage the same memory. When MPI tries to initialize, it throws an ABI error (MPI_Comm_create_keyval).The Solution:If you load an icc22-cmpi module $\rightarrow$ compile h5bench with Intel 2022 and Cray wrappers (-DCMAKE_C_COMPILER=cc -DCMAKE_CXX_COMPILER=CC).If you load a gcc-ompi module $\rightarrow$ compile h5bench with GCC 11 and mpicc (-DCMAKE_C_COMPILER=mpicc -DCMAKE_CXX_COMPILER=mpicxx).

GoalModule Stack to LoadCMake Command for h5benchIntel Stack (HDF5 1.10.8)intel/2022.0.2openmpi/4.1.2-hpehdf5/1.10.8-parallel-icc22-cmpicmake .. -DCMAKE_C_COMPILER=cc -DCMAKE_CXX_COMPILER=CC -DCMAKE_C_FLAGS="-O3"GCC Stack (HDF5 1.12.1 / 4.1.7)gcc/11.4.0-nsccopenmpi/4.1.7-gcc11hdf5/1.12.1-parallel-icc22-ompi4cmake .. -DCMAKE_C_COMPILER=mpicc -DCMAKE_CXX_COMPILER=mpicxx -DCMAKE_C_FLAGS="-O3"

1. container:
haiyen11231@lima-apptainer-amd64:~/h5bench-build$ sudo apptainer shell h5bench_benchmarks.sif 
Apptainer> which gcc g++ icc icx cc 2>/dev/null
/usr/bin/gcc
/usr/bin/g++
/usr/bin/cc
Apptainer> gcc --version
gcc (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0
Copyright (C) 2021 Free Software Foundation, Inc.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

Apptainer> which mpicc
/usr/bin/mpicc
Apptainer> mpicc -show
mpicc --version
gcc -I/usr/lib/x86_64-linux-gnu/openmpi/include -I/usr/lib/x86_64-linux-gnu/openmpi/include/openmpi -L/usr/lib/x86_64-linux-gnu/openmpi/lib -lmpi
gcc (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0
Copyright (C) 2021 Free Software Foundation, Inc.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

Apptainer> which cc
/usr/bin/cc
Apptainer> cc -show
cc: error: unrecognized command-line option ‘-show’
cc: fatal error: no input files
compilation terminated.
Apptainer> cc --version
cc (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0
Copyright (C) 2021 Free Software Foundation, Inc.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

Apptainer> exit
exit
haiyen11231@lima-apptainer-amd64:~/h5bench-build$ sudo apptainer exec your_container.sif mpicc -show
FATAL:   While checking container encryption: could not open image /home/haiyen11231.guest/h5bench-build/your_container.sif: failed to retrieve path for /home/haiyen11231.guest/h5bench-build/your_container.sif: lstat /home/haiyen11231.guest/h5bench-build/your_container.sif: no such file or directory
haiyen11231@lima-apptainer-amd64:~/h5bench-build$ sudo apptainer exec h5bench_benchmarks.sif  mpicc -show
gcc -I/usr/lib/x86_64-linux-gnu/openmpi/include -I/usr/lib/x86_64-linux-gnu/openmpi/include/openmpi -L/usr/lib/x86_64-linux-gnu/openmpi/lib -lmpi
haiyen11231@lima-apptainer-amd64:~/h5bench-build$ sudo apptainer exec h5bench_benchmarks.sif  mpicc --version
gcc (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0
Copyright (C) 2021 Free Software Foundation, Inc.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

haiyen11231@lima-apptainer-amd64:~/h5bench-build$ sudo apptainer exec h5bench_benchmarks.sif h5pcc -showconfig | grep -E "C Compiler|MPI"
                     C Compiler: /usr/bin/mpicc.openmpi ( Configured with: ../src/configure -v --with-pkgversion='Ubuntu 11.2.0-12ubuntu1' --with-bugurl=file:///usr/share/doc/gcc-11/README.Bugs --enable-languages=c,ada,c++,go,brig,d,fortran,objc,obj-c++,m2 --prefix=/usr --with-gcc-major-version-only --program-suffix=-11 --program-prefix=x86_64-linux-gnu- --enable-shared --enable-linker-build-id --libexecdir=/usr/lib --without-included-gettext --enable-threads=posix --libdir=/usr/lib --enable-nls --enable-bootstrap --enable-clocale=gnu --enable-libstdcxx-debug --enable-libstdcxx-time=yes --with-default-libstdcxx-abi=new --enable-gnu-unique-object --disable-vtable-verify --enable-plugin --enable-default-pie --with-system-zlib --enable-libphobos-checking=release --with-target-system-zlib=auto --enable-objc-gc=auto --enable-multiarch --disable-werror --enable-cet --with-arch-32=i686 --with-abi=m64 --with-multilib-list=m32,m64,mx32 --enable-multilib --with-tune=generic --enable-offload-targets=nvptx-none=/build/gcc-11-VB3iS9/gcc-11-11.2.0/debian/tmp-nvptx/usr,amdgcn-amdhsa=/build/gcc-11-VB3iS9/gcc-11-11.2.0/debian/tmp-gcn/usr --without-cuda-driver --enable-checking=release --build=x86_64-linux-gnu --host=x86_64-linux-gnu --target=x86_64-linux-gnu --with-build-config=bootstrap-lto-lean --enable-link-serialization=2 built with gcc version 11.2.0 (Ubuntu 11.2.0-12ubuntu1))

===> h5pcc -showconfig Result:

C Compiler: /usr/bin/mpicc.openmpi: Confirms that Parallel HDF5 inside `h5bench_benchmarks.sif` was compiled directly against `OpenMPI` and `GCC 11.2.0/11.4.0.`

No Cray/Intel Influence: There are no Intel drivers (icc/icx) or Cray wrappers (cc/cmpi) present in the container image.

2. native
due to limited version of parallel hdf5, elly hard to find the version that match both ompi and gcc (can only choose 1 of 2)
-------
omponent	Native Host (ASPIRE 2A)	Container Image (h5bench_benchmarks.sif)	Methodological Alignment Status
OS Distribution	RHEL 8.5 / HPE Cray OS	Ubuntu 22.04 LTS	Base OS Baseline
Compiler	Intel 2022 (icc/icx) via Cray cc/CC	GCC 11.4.0 (/usr/bin/gcc)	Documented Compiler Backend Delta
MPI Engine	openmpi/4.1.2-hpe	Open MPI 4.1.2 (/usr/bin/mpicc.openmpi)	Identical Major/Minor Series (4.1.2)
Parallel HDF5	1.10.8 (hdf5/1.10.8-parallel-icc22-cmpi)	1.10.7 (libhdf5-openmpi-dev)	Identical Feature Family (1.10.x)


-----
How to Justify This Setup in Your Final Report
When summarizing your methodology, write it up using these three key justifications:

Strict MPI & I/O Protocol Control:

"To eliminate network protocol variance during parallel I/O benchmark execution, both native and containerized environments were locked to the OpenMPI 4.1.2 release series and the Parallel HDF5 1.10.x feature set."

Isolated Virtualization Overhead:

"By keeping the MPI communication engine and HDF5 library versions consistent across both testbeds, measured throughput deltas between bare-metal execution and Apptainer (.sif) reflect true container abstraction overhead (e.g., overlay filesystem translation and namespace tracking) rather than software version drift."

Vendor-Optimized vs. Generic Distribution Baseline:

"The host environment utilizes ASPIRE 2A's native Intel 2022 toolchain (icc22-cmpi) via HPE Cray cc wrappers to interface with the Slingshot interconnect, whereas the container utilizes Ubuntu 22.04's default GCC 11 toolchain (/usr/bin/mpicc.openmpi). This compiler backend delta represents the standard trade-off between vendor-optimized HPC bare-metal execution and out-of-the-box container portability."
-----
Objective: Establish the maximum performance native host baseline using OpenMPI 4.1.x and the HDF5 1.10.x feature series.

Container Counterpart: GCC 11.4 + OpenMPI 4.1.2 + HDF5 1.10.7 (Ubuntu 22.04 default).

Alignment Strategy: Aligns the OpenMPI release series (4.1.2) and Parallel HDF5 API family (1.10.x).


Unlike IOR's container test, h5bench is not itself an MPI binary -- it's a driver script that reads "mpi":{"command":"mpirun"} from the JSON config and launches mpirun *itself*. So there is no outer host mpirun wrapping this call (that would try to launch a second, conflicting MPI runtime): a single apptainer exec hands control to the container, and the mpirun that actually runs is the container's own apt-installed OpenMPI, resolved from PATH inside the container's environment.

in container: # Pin Lustre striping explicitly -- the container's h5bench logs "Lustre
# support not detected" (built without liblustreapi), so its JSON
# "file-system.lustre" block is a silent no-op. Without this, the output
# directory would get whatever default/inherited striping Lustre happens
# to assign, uncontrolled -- same discipline as IOR's container test.



What does this mean??? What I was describing (apptainer exec sif h5bench config.json — driver inside the container): genuinely can't do multi-node. The container's generic OpenMPI has no PBS tm support, and its ssh fallback would launch bare orted on the remote host — outside the container, where that binary doesn't exist.

What you're describing (driver on the host, container entered per-rank): works. Here's why, from the source:

understand the architecture, how it spawn to multi node to process request????


Layer 1 — How MPI launches across nodes at all

When you ask PBS for 2 nodes, it starts your .pbs script on one node only (the "head" node of the allocation). Nothing is running on node 2 yet. mpirun is what fans out:

PBS allocates: node001, node002  →  writes $PBS_NODEFILE
   │
   └─ runs your .pbs script on node001 ONLY
         │
         └─ mpirun -np 256
              ├─ reads $PBS_NODEFILE → "I need 128 ranks on each"
              ├─ asks PBS (via the 'tm' task-manager API, compiled into
              │   the HPE OpenMPI build) to start a daemon on each node
              │
              ├─ node001: orted ──┬─ rank 0
              │                   ├─ rank 1  … (128 ranks)
              └─ node002: orted ──┬─ rank 128
                                  └─ … (128 ranks)
                     │
                     └─ ranks wire up to each other over hsn0 (Slingshot)

The important bit: mpirun needs a privileged channel to start processes on other machines. On this cluster that's PBS's tm API, built into openmpi/4.1.2-hpe. A generic apt OpenMPI has no tm support and falls back to ssh.

Layer 2 — Where Apptainer fits

The broken way (what I was wrongly describing as the only option):

apptainer exec sif h5bench config.json
   └─ container's mpirun       ← this is the problem
        ├─ no PBS tm support → can't ask the scheduler
        ├─ falls back to: ssh node002 orted
        └─ but `orted` only exists INSIDE the .sif image.
           node002's host filesystem has no such binary.
           → "orted: command not found" → dead

The working way — the standard HPC "hybrid model", MPI on the outside:

host mpirun -np 256 … apptainer exec --bind /scratch sif /opt/.../h5bench_write
   │
   └─ host mpirun fans out via PBS tm (it CAN do this)
        node001: orted → 128 × [ apptainer exec → h5bench_write ]
        node002: orted → 128 × [ apptainer exec → h5bench_write ]

You get 256 separate container instances, one per rank. apptainer exec is cheap — it's not a VM or a daemon, it just sets up namespaces and exec()s your binary. Think of it as "run this program, but with a different view of the filesystem."

The ranks still have to talk to each other, and they do that using libmpi.so from inside the .sif. So you have host mpirun/orted coordinating container-resident MPI libraries. That only works because both are OpenMPI 4.1.2 — and it's exactly your mechanism #1: the container's libmpi.so has no UCX, so those 256 ranks coordinate over TCP on hsn0 instead of native Slingshot. That's the overhead you're measuring.

Your IOR runs already proved this model works here — 8 nodes × 128 ranks, host mpirun + apptainer exec.

Layer 3 — Where the h5bench driver fits (this is the key insight)

The driver never participates in MPI. It's a single-process Python script that runs once, builds a command string, and shells out:

h5bench (1 python process, serial)
  1. read config.json
  2. mkdir <directory>/<uuid>/
  3. if Lustre detected → run `lfs setstripe`
  4. translate JSON "configuration" → h5bench.cfg  (KEY=VALUE text)
  5. build a STRING:
        "<mpi.command> <mpi.configuration> <prefix>/h5bench_write <cfg> <file>"
  6. subprocess.run(string)     ←── the parallel job starts HERE
  7. collect logs

So the only thing that matters is what string it builds at step 5. Three ways to get the same string:

┌─────────────────┬────────────┬────────────────────────────────────┬─────────────┐
│    Approach     │  Driver    │         String it produces         │ Multi-node? │
│                 │    runs    │                                    │             │
├─────────────────┼────────────┼────────────────────────────────────┼─────────────┤
│ Driver inside   │ in         │ container-mpirun … h5bench_write   │ ❌ no tm    │
│ container       │ container  │                                    │             │
├─────────────────┼────────────┼────────────────────────────────────┼─────────────┤
│ Driver on host  │ on host    │ host-mpirun … apptainer exec sif   │ ✅          │
│ + -p            │            │ /opt/…/h5bench_write               │             │
├─────────────────┼────────────┼────────────────────────────────────┼─────────────┤
│ Manual (what I  │ —          │ you write that string in bash      │ ✅          │
│ wrote)          │            │ yourself                           │             │
└─────────────────┴────────────┴────────────────────────────────────┴─────────────┘

Approaches 2 and 3 produce an identical command. That's why I said it's a maintainability choice, not a correctness one — the driver is a string-builder, and in approach 2 you're hand-writing most of the string anyway inside mpi.configuration.

Layer 4 — The I/O stack: HDF5 → MPI-IO → Lustre

  h5bench_write            H5Dwrite(...)
        │
        ▼
  HDF5 library             collective or independent?
  (libhdf5.so)             ← COLLECTIVE_DATA=YES switches this
        │
        ▼
  MPI-IO / ROMIO           two-phase I/O, aggregation, data sieving
  (inside libmpi.so)       ← ranks COMMUNICATE here to coordinate writes
        │
        ▼
  POSIX syscalls           open() / write() / close() on /scratch/...
        │
════════╪═══════ KERNEL BOUNDARY ═══════════════════════
        ▼
  Lustre client            kernel module — runs on the HOST, always
        │
        ▼
  MDS (metadata) + OSTs (data)      2 MDTs, 17+ OSTs

The single most important thing to understand for your thesis: Lustre is a kernel filesystem. The container does not have its own Lustre client — it cannot. When you --bind /scratch, you are only making the host's already-mounted Lustre visible inside the container's mount namespace. Every write() syscall from inside the container is serviced by the exact same host kernel Lustre client as a native run.

So the bytes take an identical path below the boundary. What actually differs is all above it:

- lfs userspace tools aren't installed in the container → h5bench logs Lustre support not detected → can't set striping (exactly what we observed, and why we moved setstripe into the PBS script)
- HDF5 version/build differs (1.12.1 icc vs 1.10.7 gcc) → different MPI-IO hints and collective decisions
- MPI library differs → different ROMIO implementation, and different transport for the rank-to-rank coordination that two-phase I/O depends on

That reframes your result nicely: a container/native gap here is not "the container's filesystem is slower." It's the userspace library stack above the kernel boundary — which is precisely the mechanism your OSU and IOR work already isolated.

Putting it together: one container write at 256 ranks

1.  PBS starts h5bench_container_weak.pbs on node001
2.  Script does lfs setstripe -c 4 -S 1m on the payload dir   [host, 1 process]
3.  Script writes write_rep1.cfg                               [host, 1 process]
4.  host mpirun fans out via PBS tm → orted on node001+node002
5.  Each orted forks 128 × apptainer exec → h5bench_write      [256 containers]
6.  Ranks wire up via container libmpi.so → TCP over hsn0      ← mechanism #1
7.  H5Dwrite → ROMIO two-phase → ranks exchange data           ← mechanism #1 again
8.  write() syscalls cross into the HOST kernel Lustre client  ← identical to native
9.  Data lands striped across 4 OSTs                           ← we pinned this in step 2
10. Ranks exit, containers vanish, mpirun returns

Steps 6 and 7 are where native and container diverge. Steps 8–9 are identical by construction. That's the whole experiment in one picture.

what is disable OpenIB (HPE Cray EX), use UCX PML, and set UCX log level to ERROR.