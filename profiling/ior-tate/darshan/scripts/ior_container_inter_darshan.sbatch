#!/bin/bash
#SBATCH --ntasks-per-node=16
#SBATCH --exclusive
#SBATCH --time=00:30:00

# Experiment description: Darshan-instrumented containerized IOR on 2 or 3 TATE
# nodes, 16 ranks/node, same flags as the inter-node weak-scaling baseline (-t 1m,
# B=16m per rank, -w -m -g -d 5, OMPIO fs_ufs_lock_algorithm 3) for MPI-IO +
# shared file: the case with a small container gap (-3 to -4% at 1-2 nodes).
# The HOST Darshan build is bind-mounted into the container and loaded with
# LD_PRELOAD, so native and container are measured by the identical library.
# submit_inter_darshan.sh sets --nodes, --nodelist and passes NODE_COUNT/REPS.

SIF=$HOME/container/ior/ior_benchmarks_tate_cluster.sif
IOR_BIN=/opt/ior-4.0.0/install/bin/ior            # path INSIDE the container
DARSHAN_INSTALL=$HOME/native/darshan/darshan/install   # host build, bind-mounted below
DARSHAN_IN_CONTAINER=/opt/darshan
VARIANT=container

# Validate input variables
: "${NODE_COUNT:?Must pass --export=ALL,NODE_COUNT=<1|2|3>}"
: "${REPS:?Must pass --export=ALL,REPS=<repetitions>}"
[ -f "$SIF" ] || { echo "ERROR: container image not found at $SIF"; exit 1; }
[ -r "$DARSHAN_INSTALL/lib/libdarshan.so" ] || { echo "ERROR: libdarshan.so not found under $DARSHAN_INSTALL"; exit 1; }
export PATH=$DARSHAN_INSTALL/bin:$PATH

# Verify Slurm actually granted the requested number of nodes
if [ "$SLURM_JOB_NUM_NODES" -ne "$NODE_COUNT" ]; then
    echo "FATAL: Expected $NODE_COUNT node(s), Slurm granted $SLURM_JOB_NUM_NODES."
    exit 1
fi

# Every node that runs ranks must have apptainer, or mpirun fails at launch
MISSING=$(srun -N "$SLURM_JOB_NUM_NODES" -n "$SLURM_JOB_NUM_NODES" --ntasks-per-node=1 \
    bash -c 'command -v apptainer >/dev/null || hostname -s')
[ -z "$MISSING" ] || { echo "FATAL: apptainer not installed on: $MISSING"; exit 1; }

# Fixed case: MPI-IO shared, collective, -t 1m, lock fix as in the scaling runs
API=MPIIO
MODEL=shared
API_LOWER=mpiio
T=1m
LOCK_ALG=3
RANKS_PER_NODE=16
NP=$((NODE_COUNT * RANKS_PER_NODE))

B=16m
CASE="inter_n${NODE_COUNT}_${API_LOWER}_${MODEL}_t${T}_lock${LOCK_ALG}"

REPORT_DIR="${VARIANT}/${CASE}"
mkdir -p "$REPORT_DIR"
DLOG="$(pwd)/${REPORT_DIR}/${CASE}_${SLURM_JOB_ID}.darshan"   # under $HOME, so visible inside the container

PAYLOAD_DIR="payload/${VARIANT}_${CASE}_${SLURM_JOB_ID}"
mkdir -p "$PAYLOAD_DIR"
# Ensure leftover payload is cleaned up even on failure/scancel/timeout
trap 'rm -rf "$PAYLOAD_DIR"' EXIT

export OMPI_MCA_pml=ucx                  # fail loudly instead of falling back to another PML
# TATE's Apptainer runs in user-namespace mode: each rank's container has its own
# user namespace, so UCX can't open other ranks' /proc/<pid>/fd for shared memory
# ("mm_posix.c ... Permission denied"). Use named /dev/shm segments instead.
export UCX_POSIX_USE_PROC_LINK=n
export UCX_NET_DEVICES=ibp134s0:1        # the only active IB port; same device for native and container

MPIRUN="mpirun -np $NP --map-by ppr:${RANKS_PER_NODE}:node --bind-to core -x UCX_POSIX_USE_PROC_LINK -x UCX_NET_DEVICES \
  --mca fs_ufs_lock_algorithm $LOCK_ALG"
# Darshan settings go inside the container via --env, so LD_PRELOAD applies to
# IOR only, not to the apptainer runtime on the host. DARSHAN_JOBID names the
# variable holding the job ID (the build defaults to PBS_JOBID).
APPTAINER="apptainer exec --bind $DARSHAN_INSTALL:$DARSHAN_IN_CONTAINER \
  --env LD_PRELOAD=$DARSHAN_IN_CONTAINER/lib/libdarshan.so \
  --env DARSHAN_LOGFILE=$DLOG --env DXT_ENABLE_IO_TRACE=1 --env DARSHAN_JOBID=SLURM_JOB_ID"

echo "=== Environment ==="
echo "Nodes: $SLURM_JOB_NODELIST ($SLURM_JOB_NUM_NODES)  Job: $SLURM_JOB_ID  NP: $NP"
echo "Variant: $VARIANT  Case: $CASE  B: $B (per rank)  REPS: $REPS  OMPIO lock: $LOCK_ALG"
echo "Load before:"
srun -N "$SLURM_JOB_NUM_NODES" -n "$SLURM_JOB_NUM_NODES" --ntasks-per-node=1 bash -c 'echo "  $(hostname -s): $(cat /proc/loadavg)"'
mpirun --version | head -1
apptainer --version
darshan-config --version 2>/dev/null | sed 's/^/Darshan /'
echo "SIF: $SIF"
# Confirm the bind-mounted library resolves all its dependencies inside the image
$APPTAINER "$SIF" ldd $DARSHAN_IN_CONTAINER/lib/libdarshan.so | grep -E "mpi|libz|not found"

set -x
$MPIRUN $APPTAINER "$SIF" "$IOR_BIN" \
  -a "$API" \
  -w \
  -t "$T" -b "$B" \
  -m -g -d 5 -c -i "$REPS" \
  -o "${PAYLOAD_DIR}/testfile_${CASE}" \
  > "${REPORT_DIR}/ior_${SLURM_JOB_ID}.txt"
MPIRUN_EXIT=$?
set +x

echo "Load after:"
srun -N "$SLURM_JOB_NUM_NODES" -n "$SLURM_JOB_NUM_NODES" --ntasks-per-node=1 bash -c 'echo "  $(hostname -s): $(cat /proc/loadavg)"'

if [ "$MPIRUN_EXIT" -ne 0 ]; then
    echo "FAILED: $CASE (mpirun exit code $MPIRUN_EXIT)"
    exit "$MPIRUN_EXIT"
fi

# Darshan writes its log at MPI_Finalize; confirm it exists and holds the expected modules
[ -s "$DLOG" ] || { echo "FATAL: no Darshan log at $DLOG (check the ldd output above)"; exit 1; }
darshan-parser "$DLOG" > "${DLOG%.darshan}.parsed" || { echo "FATAL: darshan-parser failed"; exit 1; }
darshan-parser --total --perf "$DLOG" > "${DLOG%.darshan}.perf" 2>/dev/null
darshan-dxt-parser "$DLOG" > "${DLOG%.darshan}.dxt.txt" 2>/dev/null
POSIX_N=$(grep -cP '^POSIX\t' "${DLOG%.darshan}.parsed")
MPIIO_N=$(grep -cP '^MPI-IO\t' "${DLOG%.darshan}.parsed")
echo "Darshan log $(du -h "$DLOG" | cut -f1): $POSIX_N POSIX lines, $MPIIO_N MPI-IO lines, DXT $(wc -l < "${DLOG%.darshan}.dxt.txt") lines"
[ "$POSIX_N" -gt 0 ] || { echo "FATAL: no POSIX counters in Darshan log"; exit 1; }
if [ "$MPIIO_N" -eq 0 ]; then
    echo "FATAL: MPIIO case but no MPI-IO counters in Darshan log"; exit 1
fi

echo "Completed Successfully! "
