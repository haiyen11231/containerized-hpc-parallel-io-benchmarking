#!/bin/bash
#SBATCH --job-name=diag_multinode
#SBATCH --nodes=2
#SBATCH --nodelist=tate01,tate03
#SBATCH --ntasks-per-node=16
#SBATCH --exclusive
#SBATCH --time=01:00:00
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

# Experiment description: Bisects why native MPI-IO shared-file IOR stalls/hangs
# across nodes on TATE (0 repetitions in 60 min at 2-3 nodes, while 1 node and
# POSIX FPP work). Runs steps A-H, each adding one layer, each with its own
# timeout. On a timeout it records where every IOR process is blocked
# (/proc/<pid>/wchan, state) on every node before killing it, and it records
# the NFS LOCK operation counters from /proc/self/mountstats around each IOR step.
# Native only (apptainer is not on tate02/tate03).
#
#   mkdir -p logs && sbatch diag_multinode.sbatch
#   sbatch --nodelist=tate01,tate02,tate03 --nodes=3 diag_multinode.sbatch   # 3 nodes

IOR_BIN=$HOME/native/ior/ior-4.0.0/install/bin/ior
STEP_TIMEOUT=${STEP_TIMEOUT:-180}          # seconds per step; a healthy step takes < 30 s
WORK="$SLURM_SUBMIT_DIR/diag_${SLURM_JOB_ID}"
mkdir -p "$WORK"
trap 'rm -rf "$WORK"/data_*' EXIT

export OMPI_MCA_pml=ucx
export UCX_POSIX_USE_PROC_LINK=n
export UCX_NET_DEVICES=ibp134s0:1
N=$SLURM_JOB_NUM_NODES

echo "Nodes: $SLURM_JOB_NODELIST  Job: $SLURM_JOB_ID  Step timeout: ${STEP_TIMEOUT}s"
mpirun --version | head -1

# NFS lock counters for /home on this (first) node: ops, transmissions, timeouts, ... execute time
nfs_locks() {
    awk '/mounted on \/home with/{m=1} m && /^device /{if(!/\/home/) m=0} m && /^[[:space:]]*(LOCK|LOCKT|LOCKU):/' /proc/self/mountstats
}

# Where is every IOR process blocked, on every node? (wchan = kernel wait function)
snapshot() {
    echo "  --- snapshot of ior processes (state, wchan) on all nodes ---"
    srun --overlap -N "$N" -n "$N" --ntasks-per-node=1 bash -c \
        'for p in $(pgrep -u $USER -x ior); do echo "  $(hostname -s) pid $p state=$(awk "/^State/{print \$2}" /proc/$p/status) wchan=$(cat /proc/$p/wchan) cpu=$(ps -o pcpu= -p $p)"; done' 2>&1 | sort | head -40
}

# run_step <label> <command...>: runs in the background, snapshots and kills on timeout
run_step() {
    local label=$1; shift
    echo; echo "===== $label ====="
    echo "\$ $*"
    local before; before=$(nfs_locks)
    local t0=$SECONDS
    "$@" > "$WORK/${label%% *}.log" 2>&1 &
    local pid=$!
    while kill -0 $pid 2>/dev/null && [ $((SECONDS - t0)) -lt "$STEP_TIMEOUT" ]; do sleep 2; done
    if kill -0 $pid 2>/dev/null; then
        echo "  RESULT: HUNG (> ${STEP_TIMEOUT}s)"
        snapshot
        kill $pid; sleep 3; kill -9 $pid 2>/dev/null
        pkill -u "$USER" -x ior 2>/dev/null
        srun --overlap -N "$N" -n "$N" --ntasks-per-node=1 pkill -u "$USER" -x ior 2>/dev/null
    else
        wait $pid; local rc=$?
        echo "  RESULT: exit=$rc after $((SECONDS - t0))s"
        grep -E "^(write|Max Write)" "$WORK/${label%% *}.log" | head -3 | sed 's/^/  /'
    fi
    echo "  NFS LOCK counters before -> after (ops trans timeouts ... execute_ms):"
    paste <(echo "$before") <(nfs_locks) | sed 's/^/   /'
    grep -iE "error|warn|abort" "$WORK/${label%% *}.log" | head -5 | sed 's/^/  log: /'
}

IOR_SMALL="-w -t 1m -b 4m -i 1"
P1="mpirun -np $N --map-by ppr:1:node --bind-to core -x UCX_POSIX_USE_PROC_LINK -x UCX_NET_DEVICES"
P16="mpirun -np $((N * 16)) --map-by ppr:16:node --bind-to core -x UCX_POSIX_USE_PROC_LINK -x UCX_NET_DEVICES"

run_step "A srun_hostname"    srun -N "$N" -n "$N" --ntasks-per-node=1 hostname
run_step "B mpirun_hostname"  $P1 hostname
run_step "C posix_fpp_1pn"    $P1 -x UCX_LOG_LEVEL=info "$IOR_BIN" -a POSIX -F $IOR_SMALL -o "$WORK/data_C"
grep -iE "ucp|transport|rc_mlx5|dc_mlx5|ud_mlx5|tcp" "$WORK/C.log" | sort -u | head -8 | sed 's/^/  ucx: /'
run_step "D posix_shared_1pn" $P1 "$IOR_BIN" -a POSIX $IOR_SMALL -o "$WORK/data_D"
run_step "E mpiio_indep_1pn"  $P1 "$IOR_BIN" -a MPIIO $IOR_SMALL -o "$WORK/data_E"
run_step "F mpiio_coll_1pn"   $P1 "$IOR_BIN" -a MPIIO -c $IOR_SMALL -o "$WORK/data_F"
run_step "G mpiio_coll_romio" $P1 --mca io romio321 "$IOR_BIN" -a MPIIO -c $IOR_SMALL -o "$WORK/data_G"
run_step "H mpiio_coll_16pn"  $P16 "$IOR_BIN" -a MPIIO -c $IOR_SMALL -o "$WORK/data_H"

echo; echo "===== OpenMPI MPI-IO locking settings ====="
ompi_info --param fs ufs --level 9 2>/dev/null | grep -iE "lock" | sed 's/^/  /'
ompi_info 2>/dev/null | grep -E "MCA io:" | sed 's/^/  /'
echo; echo "Per-step IOR logs: $WORK/<step>.log"
echo "Done"
