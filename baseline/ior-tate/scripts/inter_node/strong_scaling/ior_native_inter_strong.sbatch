#!/bin/bash
#SBATCH --job-name=ior_native_inter_strong
#SBATCH --nodes=3
#SBATCH --nodelist=tate01,tate02,tate03
#SBATCH --ntasks-per-node=16
#SBATCH --exclusive
#SBATCH --time=01:00:00
#SBATCH --output=logs/%x_%j.out       # %x = job name, %j = job ID -> one log per run
#SBATCH --error=logs/%x_%j.err

# Experiment description: Run native IOR across 1/2/3 TATE nodes, 16 ranks/node,
# Combo A (MPI-IO + Shared) vs Combo B (POSIX + FPP), writing to NFS /home.
# STRONG scaling: total data is fixed at 1 GiB, so the per-rank block shrinks as
# nodes are added (48m/24m/16m for 1/2/3 nodes). Transfer size fixed at 256KiB.
# Every job reserves the whole cluster (all 3 nodes, exclusive) so no other
# Slurm job shares the nodes or NFS during a measurement.

IOR_BIN=$HOME/native/ior/ior-4.0.0/install/bin/ior
VARIANT=native

# Validate input variables
: "${NODE_COUNT:?Must pass --export=ALL,NODE_COUNT=<1|2|3>}"
: "${API:?Must pass --export=ALL,API=<POSIX|MPIIO>}"
: "${MODEL:?Must pass --export=ALL,MODEL=<shared|fpp>}"
: "${RUN:?Must pass --export=ALL,RUN=<run index>}"
[ -x "$IOR_BIN" ] || { echo "ERROR: IOR binary not found at $IOR_BIN"; exit 1; }

# Verify Slurm actually reserved the whole cluster
if [ "$SLURM_JOB_NUM_NODES" -ne 3 ]; then
    echo "FATAL: Expected all 3 nodes reserved, Slurm granted $SLURM_JOB_NUM_NODES."
    exit 1
fi

case "$NODE_COUNT" in
    1) RANK_NODES=(tate01) ;;
    2) RANK_NODES=(tate01 tate03) ;;
    3) RANK_NODES=(tate01 tate02 tate03) ;;
    *) echo "FATAL: NODE_COUNT must be 1, 2 or 3"; exit 1 ;;
esac

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
HOST_LIST=$(printf "%s:$RANKS_PER_NODE," "${RANK_NODES[@]}"); HOST_LIST=${HOST_LIST%,}   # e.g. tate01:16,tate03:16
NP=$((NODE_COUNT * RANKS_PER_NODE))
T=256k
# Strong scaling: fixed 768 MiB global dataset regardless of node count, so the
# per-rank block shrinks as NP grows: NP=16 -> 48m, 32 -> 24m, 48 -> 16m.
# 768 = 48 x 16m, so the 3-node case matches weak scaling and intra-node (B=16m);
# it divides evenly by all three rank counts, and every B is a multiple of T.
TOTAL_GLOBAL_MB=768
B_MB=$((TOTAL_GLOBAL_MB / NP))
B="${B_MB}m"

# Never overwrite an earlier run's results
REPORT_DIR="${VARIANT}/${API_LOWER}/${MODEL}/run${RUN}"
REPORT_FILE="${REPORT_DIR}/ior_n${NODE_COUNT}.txt"
[ -e "$REPORT_FILE" ] && { echo "ERROR: $REPORT_FILE already exists; pick another RUN index"; exit 1; }
mkdir -p "$REPORT_DIR"

# Payload on NFS /home so every node sees the same directory
PAYLOAD_DIR="payload/${VARIANT}_${API_LOWER}_${MODEL}_n${NODE_COUNT}_${SLURM_JOB_ID}"
mkdir -p "$PAYLOAD_DIR"
# Ensure leftover payload is cleaned up even on failure/scancel/timeout
trap 'rm -rf "$PAYLOAD_DIR"' EXIT
TEST_FILE="${PAYLOAD_DIR}/testfile_strong_${API_LOWER}_${MODEL}_n${NODE_COUNT}"

export OMPI_MCA_pml=ucx                  # fail loudly instead of falling back to another PML
export UCX_POSIX_USE_PROC_LINK=n         # same shm mechanism as the container (see container script)
export UCX_NET_DEVICES=ibp134s0:1        # the only active IB port; pinned so native and container use the same device

MPIRUN="mpirun -np $NP --host $HOST_LIST --map-by ppr:${RANKS_PER_NODE}:node --bind-to core -x UCX_POSIX_USE_PROC_LINK -x UCX_NET_DEVICES"

echo "=== Environment ==="
echo "Reserved: $SLURM_JOB_NODELIST  Ranks on: $HOST_LIST"
echo "Job: $SLURM_JOB_ID  NP: $NP  Run: $RUN"
echo "Variant: $VARIANT  API: $API  MODEL: $MODEL  T: $T  B: $B (per rank, strong; total ${TOTAL_GLOBAL_MB}m)"
echo "Load before:"
srun --ntasks-per-node=1 bash -c 'echo "  $(hostname -s): $(cat /proc/loadavg)"'
grep " /home " /proc/mounts
mpirun --version | head -1

set -x
$MPIRUN "$IOR_BIN" \
  -a "$API" $FPP_FLAG \
  -w \
  -t "$T" -b "$B" \
  -m -g -d 5 $API_EXTRA_FLAGS -i 10 \
  -o "$TEST_FILE" \
  > "$REPORT_FILE"
MPIRUN_EXIT=$?
set +x

echo "Load after:"
srun --ntasks-per-node=1 bash -c 'echo "  $(hostname -s): $(cat /proc/loadavg)"'

if [ "$MPIRUN_EXIT" -ne 0 ]; then
    echo "FAILED: API=$API MODEL=$MODEL NODES=$NODE_COUNT RUN=$RUN (mpirun exit code $MPIRUN_EXIT)"
    exit "$MPIRUN_EXIT"
fi

echo "Completed Successfully! "
