#!/bin/bash
#SBATCH --job-name=ior_container_inter_strong
#SBATCH --ntasks-per-node=16
#SBATCH --exclusive
#SBATCH --output=logs/%x_%j.out       # %x = job name, %j = job ID -> one log per run
#SBATCH --error=logs/%x_%j.err

# Experiment description: Run IOR in an Apptainer container on 1, 2 or 3 TATE
# nodes (one node count per job), 16 ranks/node, Combo A (MPI-IO + Shared) vs
# Combo B (POSIX + FPP), writing to NFS /home. STRONG scaling: total data is fixed at 768 MiB, so the
# per-rank block shrinks as nodes are added (48m/24m/16m for 1/2/3 nodes). Transfer size fixed at
# 1m, 5 repetitions.

SIF=$HOME/container/ior/ior_benchmarks_tate_cluster.sif
IOR_BIN=/opt/ior-4.0.0/install/bin/ior            # path INSIDE the container
VARIANT=container

# Validate input variables
: "${NODE_COUNT:?Must pass --export=ALL,NODE_COUNT=<1|2|3>}"
: "${API:?Must pass --export=ALL,API=<POSIX|MPIIO>}"
: "${MODEL:?Must pass --export=ALL,MODEL=<shared|fpp>}"
[ -f "$SIF" ] || { echo "ERROR: container image not found at $SIF"; exit 1; }

# Verify Slurm actually granted the requested number of nodes
if [ "$SLURM_JOB_NUM_NODES" -ne "$NODE_COUNT" ]; then
    echo "FATAL: Expected $NODE_COUNT node(s), Slurm granted $SLURM_JOB_NUM_NODES."
    exit 1
fi

# Every node that runs ranks must have apptainer, or mpirun fails at launch
MISSING=$(srun -N "$SLURM_JOB_NUM_NODES" -n "$SLURM_JOB_NUM_NODES" --ntasks-per-node=1 \
    bash -c 'command -v apptainer >/dev/null || hostname -s')
[ -z "$MISSING" ] || { echo "FATAL: apptainer not installed on: $MISSING"; exit 1; }

API_LOWER=$(echo "$API" | tr '[:upper:]' '[:lower:]')
FPP_FLAG=""
[ "$MODEL" == "fpp" ] && FPP_FLAG="-F"

API_EXTRA_FLAGS=""
if [ "$API" == "MPIIO" ]; then
    API_EXTRA_FLAGS="-c"
elif [ "$API" == "POSIX" ]; then
    API_EXTRA_FLAGS="-e --posix.odirect"
fi

RANKS_PER_NODE=16
NP=$((NODE_COUNT * RANKS_PER_NODE))
T=1m
# Strong scaling: fixed 768 MiB global dataset regardless of node count, so the
# per-rank block shrinks as NP grows: NP=16 -> 48m, 32 -> 24m, 48 -> 16m.
# 768 = 48 x 16m, so the 3-node case matches weak scaling and intra-node (B=16m);
# it divides evenly by all three rank counts, and every B is a multiple of T.
TOTAL_GLOBAL_MB=768
B_MB=$((TOTAL_GLOBAL_MB / NP))
B="${B_MB}m"
REPS=5

# Never overwrite an earlier result
REPORT_DIR="${VARIANT}/${API_LOWER}/${MODEL}"
REPORT_FILE="${REPORT_DIR}/ior_n${NODE_COUNT}.txt"
[ -e "$REPORT_FILE" ] && { echo "ERROR: $REPORT_FILE already exists; move it away to re-run"; exit 1; }
mkdir -p "$REPORT_DIR"

# Payload on NFS /home so every node sees the same directory
PAYLOAD_DIR="payload/${VARIANT}_${API_LOWER}_${MODEL}_n${NODE_COUNT}_${SLURM_JOB_ID}"
mkdir -p "$PAYLOAD_DIR"
# Ensure leftover payload is cleaned up even on failure/scancel/timeout
trap 'rm -rf "$PAYLOAD_DIR"' EXIT
TEST_FILE="${PAYLOAD_DIR}/testfile_strong_${API_LOWER}_${MODEL}_n${NODE_COUNT}"

export OMPI_MCA_pml=ucx                  # fail loudly instead of falling back to another PML
# TATE's Apptainer runs in user-namespace mode: each rank's container has its own
# user namespace, so UCX can't open other ranks' /proc/<pid>/fd for shared memory
# ("mm_posix.c ... Permission denied"). Use named /dev/shm segments instead.
export UCX_POSIX_USE_PROC_LINK=n
export UCX_NET_DEVICES=ibp134s0:1
# OpenMPI's MPI-IO layer (OMPIO) by default locks the WHOLE file around every
# read/write when the file is on NFS. Writes then take turns, the NFS client retries
# blocked locks with back-off up to 30 s, and across nodes the job hangs (0 repetitions
# in 60 min; see diag/diag_multinode.sbatch, diag/diag_mpiio_fix.sbatch). Algorithm 3
# locks only writes that start/end mid-block; IOR's per-rank blocks are aligned and
# non-overlapping, so data stays correct. Only affects MPI-IO, not POSIX.
LOCK_ALG=3
        # the only active IB port; pinned so native and container use the same device

MPIRUN="mpirun -np $NP --map-by ppr:${RANKS_PER_NODE}:node --bind-to core -x UCX_POSIX_USE_PROC_LINK -x UCX_NET_DEVICES --mca fs_ufs_lock_algorithm $LOCK_ALG"

echo "=== Environment ==="
echo "Nodes: $SLURM_JOB_NODELIST ($SLURM_JOB_NUM_NODES)  Job: $SLURM_JOB_ID  NP: $NP"
echo "Variant: $VARIANT  API: $API  MODEL: $MODEL  T: $T  B: $B (per rank, strong; total ${TOTAL_GLOBAL_MB}m)  REPS: $REPS"
echo "OMPIO lock algorithm: $LOCK_ALG (fs_ufs_lock_algorithm)"
echo "Load before:"
srun -N "$SLURM_JOB_NUM_NODES" -n "$SLURM_JOB_NUM_NODES" --ntasks-per-node=1 bash -c 'echo "  $(hostname -s): $(cat /proc/loadavg)"'
grep " /home " /proc/mounts
mpirun --version | head -1
apptainer --version
echo "SIF: $SIF"
apptainer exec "$SIF" cat /opt/ior-4.0.0/stack_versions.txt
echo "UCX transports visible in the container:"
apptainer exec "$SIF" ucx_info -d | grep -E "Transport|Device" | sort -u

set -x
$MPIRUN apptainer exec "$SIF" "$IOR_BIN" \
  -a "$API" $FPP_FLAG \
  -w \
  -t "$T" -b "$B" \
  -m -g -d 5 $API_EXTRA_FLAGS -i "$REPS" \
  -o "$TEST_FILE" \
  > "$REPORT_FILE"
MPIRUN_EXIT=$?
set +x

echo "Load after:"
srun -N "$SLURM_JOB_NUM_NODES" -n "$SLURM_JOB_NUM_NODES" --ntasks-per-node=1 bash -c 'echo "  $(hostname -s): $(cat /proc/loadavg)"'

if [ "$MPIRUN_EXIT" -ne 0 ]; then
    echo "FAILED: API=$API MODEL=$MODEL NODES=$NODE_COUNT (mpirun exit code $MPIRUN_EXIT)"
    exit "$MPIRUN_EXIT"
fi

echo "Completed Successfully! "
