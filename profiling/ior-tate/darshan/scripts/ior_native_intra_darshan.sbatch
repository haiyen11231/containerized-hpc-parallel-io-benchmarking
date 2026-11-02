#!/bin/bash
#SBATCH --nodes=1
#SBATCH --nodelist=tate01
#SBATCH --exclusive
#SBATCH --ntasks-per-node=16
#SBATCH --time=01:00:00

# Experiment description: Darshan-instrumented native IOR on tate01, 16 ranks,
# same flags as the intra-node baseline (B=16m, -w -m -g -d 5) for one profiling
# case: API/MODEL/T/LOCK/REPS passed at submission. Darshan (POSIX + MPI-IO
# counters, plus DXT per-operation timeline) is loaded into the IOR ranks with
# LD_PRELOAD. LOCK selects OMPIO's NFS locking for MPI-IO: "default" (whole file)
# or an fs_ufs_lock_algorithm value (3 = ranges, as in the scaling runs).
# Submitted by submit_intra_darshan.sh.

IOR_BIN=$HOME/native/ior/ior-4.0.0/install/bin/ior
DARSHAN_INSTALL=$HOME/native/darshan/darshan/install
VARIANT=native

# Validate input variables
: "${API:?Must pass --export=ALL,API=<POSIX|MPIIO>}"
: "${MODEL:?Must pass --export=ALL,MODEL=<shared|fpp>}"
: "${T:?Must pass --export=ALL,T=<transfer size>}"
: "${LOCK:?Must pass --export=ALL,LOCK=<default|1|2|3|- (POSIX)>}"
: "${REPS:?Must pass --export=ALL,REPS=<repetitions>}"
[ -x "$IOR_BIN" ] || { echo "ERROR: IOR binary not found at $IOR_BIN"; exit 1; }
[ -r "$DARSHAN_INSTALL/lib/libdarshan.so" ] || { echo "ERROR: libdarshan.so not found under $DARSHAN_INSTALL"; exit 1; }
export PATH=$DARSHAN_INSTALL/bin:$PATH

API_LOWER=$(echo "$API" | tr '[:upper:]' '[:lower:]')
FPP_FLAG=""
[ "$MODEL" == "fpp" ] && FPP_FLAG="-F"

API_EXTRA_FLAGS=""
if [ "$API" == "MPIIO" ]; then
    API_EXTRA_FLAGS="-c"
elif [ "$API" == "POSIX" ]; then
    API_EXTRA_FLAGS="-e --posix.odirect"
fi

# OMPIO locking only matters for MPI-IO; POSIX cases take no lock setting
LOCK_FLAG=""
LOCK_TAG=""
if [ "$API" == "MPIIO" ]; then
    case "$LOCK" in
        default) LOCK_TAG="_lockdefault" ;;
        [0-3])   LOCK_FLAG="--mca fs_ufs_lock_algorithm $LOCK"; LOCK_TAG="_lock${LOCK}" ;;
        *)       echo "ERROR: LOCK must be default or 0-3 for MPIIO, got '$LOCK'"; exit 1 ;;
    esac
fi

B=16m
CASE="${API_LOWER}_${MODEL}_t${T}${LOCK_TAG}"

REPORT_DIR="${VARIANT}/${CASE}"
mkdir -p "$REPORT_DIR"
DLOG="$(pwd)/${REPORT_DIR}/${CASE}_${SLURM_JOB_ID}.darshan"

PAYLOAD_DIR="payload/${VARIANT}_${CASE}_${SLURM_JOB_ID}"
mkdir -p "$PAYLOAD_DIR"
# Ensure leftover payload is cleaned up even on failure/scancel/timeout
trap 'rm -rf "$PAYLOAD_DIR"' EXIT

export OMPI_MCA_pml=ucx                  # fail loudly instead of falling back to another PML
export UCX_POSIX_USE_PROC_LINK=n         # same shm mechanism as the container (see container script)

# Darshan settings go to the IOR ranks only (-x), never to mpirun itself.
# DARSHAN_JOBID names the variable holding the job ID (the build defaults to PBS_JOBID).
MPIRUN="mpirun -np $SLURM_NTASKS --map-by ppr:16:socket --bind-to core -x UCX_POSIX_USE_PROC_LINK $LOCK_FLAG \
  -x LD_PRELOAD=$DARSHAN_INSTALL/lib/libdarshan.so -x DARSHAN_LOGFILE=$DLOG -x DXT_ENABLE_IO_TRACE=1 \
  -x DARSHAN_JOBID=SLURM_JOB_ID"

echo "=== Environment ==="
echo "Node: $(hostname)  Job: $SLURM_JOB_ID  Tasks: $SLURM_NTASKS"
echo "Variant: $VARIANT  Case: $CASE  B: $B  REPS: $REPS  OMPIO lock: ${LOCK}"
echo "Load before: $(cat /proc/loadavg)"
mpirun --version | head -1
darshan-config --version 2>/dev/null | sed 's/^/Darshan /'

set -x
$MPIRUN "$IOR_BIN" \
  -a "$API" $FPP_FLAG \
  -w \
  -t "$T" -b "$B" \
  -m -g -d 5 $API_EXTRA_FLAGS -i "$REPS" \
  -o "${PAYLOAD_DIR}/testfile_${CASE}" \
  > "${REPORT_DIR}/ior_${SLURM_JOB_ID}.txt"
MPIRUN_EXIT=$?
set +x

echo "Load after: $(cat /proc/loadavg)"

if [ "$MPIRUN_EXIT" -ne 0 ]; then
    echo "FAILED: $CASE (mpirun exit code $MPIRUN_EXIT)"
    exit "$MPIRUN_EXIT"
fi

# Darshan writes its log at MPI_Finalize; confirm it exists and holds the expected modules
[ -s "$DLOG" ] || { echo "FATAL: no Darshan log at $DLOG"; exit 1; }
darshan-parser "$DLOG" > "${DLOG%.darshan}.parsed" || { echo "FATAL: darshan-parser failed"; exit 1; }
darshan-parser --total --perf "$DLOG" > "${DLOG%.darshan}.perf" 2>/dev/null
darshan-dxt-parser "$DLOG" > "${DLOG%.darshan}.dxt.txt" 2>/dev/null
POSIX_N=$(grep -cP '^POSIX\t' "${DLOG%.darshan}.parsed")
MPIIO_N=$(grep -cP '^MPI-IO\t' "${DLOG%.darshan}.parsed")
echo "Darshan log $(du -h "$DLOG" | cut -f1): $POSIX_N POSIX lines, $MPIIO_N MPI-IO lines, DXT $(wc -l < "${DLOG%.darshan}.dxt.txt") lines"
[ "$POSIX_N" -gt 0 ] || { echo "FATAL: no POSIX counters in Darshan log"; exit 1; }
if [ "$API" == "MPIIO" ] && [ "$MPIIO_N" -eq 0 ]; then
    echo "FATAL: MPIIO case but no MPI-IO counters in Darshan log"; exit 1
fi

echo "Completed Successfully! "
