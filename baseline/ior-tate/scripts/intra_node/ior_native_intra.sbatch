#!/bin/bash
#SBATCH --job-name=ior_native_intra
#SBATCH --nodes=1
#SBATCH --nodelist=tate01
#SBATCH --exclusive
#SBATCH --ntasks-per-node=16
#SBATCH --time=00:45:00
#SBATCH --output=logs/%x_%j.out       # %x = job name, %j = job ID -> one log per run
#SBATCH --error=logs/%x_%j.err

# Experiment description: Run native IOR on a single TATE node with 16 ranks,
# sweeping transfer size (-t: 64k, 256k, 1m, 4m) with block size fixed
# at 16m, writing to NFS /home. Two combos (MPI-IO + Shared vs POSIX + FPP),
# selected with API/MODEL at submission. Mirrors the ASPIRE 2A intra-node
# design minus Lustre striping (TATE has no Lustre). 

IOR_BIN=$HOME/native/ior/ior-4.0.0/install/bin/ior
VARIANT=native

# Validate input variables
: "${API:?Must pass --export=ALL,API=<POSIX|MPIIO>}"
: "${MODEL:?Must pass --export=ALL,MODEL=<shared|fpp>}"
: "${RUN:?Must pass --export=ALL,RUN=<run index>}"
[ -x "$IOR_BIN" ] || { echo "ERROR: IOR binary not found at $IOR_BIN"; exit 1; }

API_LOWER=$(echo "$API" | tr '[:upper:]' '[:lower:]')
FPP_FLAG=""
[ "$MODEL" == "fpp" ] && FPP_FLAG="-F"

API_EXTRA_FLAGS=""
if [ "$API" == "MPIIO" ]; then
    API_EXTRA_FLAGS="-c"
elif [ "$API" == "POSIX" ]; then
    API_EXTRA_FLAGS="-e --posix.odirect"
fi

B=16m
T_SIZES=(64k 256k 1m 4m)

# Never overwrite an earlier run's results
REPORT_DIR="${VARIANT}/${API_LOWER}/${MODEL}/run${RUN}"
if ls "$REPORT_DIR"/ior_t*.txt >/dev/null 2>&1; then
    echo "ERROR: $REPORT_DIR already has results; pick another RUN index"; exit 1
fi
mkdir -p "$REPORT_DIR"

PAYLOAD_ROOT="payload/${VARIANT}_${API_LOWER}_${MODEL}_${SLURM_JOB_ID}"
# Ensure leftover payload dirs are cleaned up even on failure/scancel/timeout
trap 'rm -rf "$PAYLOAD_ROOT"' EXIT

export OMPI_MCA_pml=ucx                  # fail loudly instead of falling back to another PML
export UCX_POSIX_USE_PROC_LINK=n         

MPIRUN="mpirun -np $SLURM_NTASKS --map-by ppr:16:socket --bind-to core -x UCX_POSIX_USE_PROC_LINK"

echo "=== Environment ==="
echo "Node: $(hostname)  Job: $SLURM_JOB_ID  Tasks: $SLURM_NTASKS  Run: $RUN"
echo "Variant: $VARIANT  API: $API  MODEL: $MODEL  B: $B  T: ${T_SIZES[*]}"
echo "Load before: $(cat /proc/loadavg)"
grep " /home " /proc/mounts
mpirun --version | head -1

ANY_FAILURE=0
for T in "${T_SIZES[@]}"; do
    echo "---------------------------------------------------"
    echo "Running: API=$API | MODEL=$MODEL | -t $T | -b $B "
    echo "---------------------------------------------------"

    # Each transfer size gets its own fresh payload directory
    PAYLOAD_DIR="${PAYLOAD_ROOT}/t${T}"
    mkdir -p "$PAYLOAD_DIR"
    TEST_FILE="${PAYLOAD_DIR}/testfile_${API_LOWER}_${MODEL}_t${T}"

    set -x
    $MPIRUN "$IOR_BIN" \
      -a "$API" $FPP_FLAG \
      -w \
      -t "$T" -b "$B" \
      -m -g -d 5 $API_EXTRA_FLAGS -i 10 \
      -o "$TEST_FILE" \
      > "${REPORT_DIR}/ior_t${T}.txt"
    MPIRUN_EXIT=$?
    set +x

    if [ "$MPIRUN_EXIT" -ne 0 ]; then
        echo "FAILED: API=$API MODEL=$MODEL T=$T (mpirun exit code $MPIRUN_EXIT)"
        ANY_FAILURE=1
    fi

    rm -rf "${PAYLOAD_DIR}"

    sleep 5
done

echo "Load after: $(cat /proc/loadavg)"

if [ "$ANY_FAILURE" -eq 1 ]; then
    echo "================================================================="
    echo " Native Intra-Node Sweep (API=$API MODEL=$MODEL RUN=$RUN) COMPLETED WITH FAILURES -- see FAILED lines above! "
    echo "================================================================="
    exit 1
fi

echo "Completed Successfully! "
