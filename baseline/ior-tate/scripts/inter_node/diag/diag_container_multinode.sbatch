#!/bin/bash
#SBATCH --job-name=diag_container_multinode
#SBATCH --nodes=3
#SBATCH --nodelist=tate01,tate02,tate03
#SBATCH --ntasks-per-node=16
#SBATCH --exclusive
#SBATCH --time=00:20:00
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

# Experiment description: Checks that containerized MPI runs across nodes now that
# apptainer is installed on tate02/tate03. Small IOR runs (seconds each) on 3 nodes x
# 16 ranks: POSIX FPP, then MPI-IO shared with the NFS locking fix
# (fs_ufs_lock_algorithm 3, see diag_mpiio_fix). Fails fast with a timeout per step.
#
#   mkdir -p logs && sbatch diag_container_multinode.sbatch

SIF=$HOME/container/ior/ior_benchmarks_tate_cluster.sif
IOR_BIN=/opt/ior-4.0.0/install/bin/ior
WORK="$SLURM_SUBMIT_DIR/diag_${SLURM_JOB_ID}"
mkdir -p "$WORK/data_fpp"
trap 'rm -rf "$WORK"/data_*' EXIT

export OMPI_MCA_pml=ucx
export UCX_POSIX_USE_PROC_LINK=n
export UCX_NET_DEVICES=ibp134s0:1
N=$SLURM_JOB_NUM_NODES
NP=$((N * 16))

echo "Nodes: $SLURM_JOB_NODELIST  Job: $SLURM_JOB_ID  NP: $NP"
echo "--- apptainer per node"
srun -N "$N" -n "$N" --ntasks-per-node=1 bash -c 'echo "  $(hostname -s): $(apptainer --version 2>&1)"' | sort

MPIRUN="mpirun -np $NP --map-by ppr:16:node --bind-to core -x UCX_POSIX_USE_PROC_LINK -x UCX_NET_DEVICES"
CEXEC="apptainer exec $SIF"

step() {
    local label=$1; shift
    echo; echo "===== $label ====="
    local t0=$SECONDS
    timeout 300 "$@" > "$WORK/$label.log" 2>&1; local rc=$?
    echo "  exit=$rc after $((SECONDS - t0))s"
    grep -E "^(write|read) " "$WORK/$label.log" | head -2 | sed 's/^/  /'
    grep -iE "error|warn|abort|not find" "$WORK/$label.log" | sort -u | head -5 | sed 's/^/  log: /'
}

step hosts       $MPIRUN $CEXEC hostname
sort "$WORK/hosts.log" | uniq -c | sed 's/^/  /'
step posix_fpp   $MPIRUN $CEXEC $IOR_BIN -a POSIX -F -w -r -C -e -t 1m -b 16m -i 1 -o "$WORK/data_fpp/f"
step mpiio_fix   $MPIRUN --mca fs_ufs_lock_algorithm 3 $CEXEC $IOR_BIN -a MPIIO -c -w -r -C -t 1m -b 16m -i 1 -o "$WORK/data_shared"
echo; echo "Per-step logs: $WORK/<step>.log"
