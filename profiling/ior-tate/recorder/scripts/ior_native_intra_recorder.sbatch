#!/bin/bash
#SBATCH --nodes=1
#SBATCH --nodelist=tate01
#SBATCH --exclusive
#SBATCH --ntasks-per-node=16
#SBATCH --time=00:30:00

# Experiment description: Recorder-traced native IOR on tate01, 16 ranks, MPI-IO +
# shared file, same flags as the intra-node baseline (B=16m, -w -m -g -d 5 -c).
# Recorder logs every POSIX and MPI-IO call of every rank with start/end time,
# including fcntl() (built with RECORDER_ENABLE_FCNTL_TRACE=ON), so the file
# locks OMPIO takes around each write -- and how long each one waits -- are
# visible directly. T/LOCK/REPS passed at submission; LOCK selects OMPIO's NFS
# locking: "default" (whole file) or an fs_ufs_lock_algorithm value (3 = ranges).
# Submitted by submit_intra_recorder.sh.

IOR_BIN=$HOME/native/ior/ior-4.0.0/install/bin/ior
RECORDER_INSTALL=$HOME/native/recorder/Recorder/install
VARIANT=native

# Validate input variables
: "${T:?Must pass --export=ALL,T=<transfer size>}"
: "${LOCK:?Must pass --export=ALL,LOCK=<default|0-3>}"
: "${REPS:?Must pass --export=ALL,REPS=<repetitions>}"
[ -x "$IOR_BIN" ] || { echo "ERROR: IOR binary not found at $IOR_BIN"; exit 1; }
[ -r "$RECORDER_INSTALL/lib/librecorder.so" ] || { echo "ERROR: librecorder.so not found under $RECORDER_INSTALL"; exit 1; }
export PATH=$RECORDER_INSTALL/bin:$PATH

case "$LOCK" in
    default) LOCK_FLAG="" ;;
    [0-3])   LOCK_FLAG="--mca fs_ufs_lock_algorithm $LOCK" ;;
    *)       echo "ERROR: LOCK must be default or 0-3, got '$LOCK'"; exit 1 ;;
esac

API=MPIIO
B=16m
CASE="mpiio_shared_t${T}_lock${LOCK}"

REPORT_DIR="${VARIANT}/${CASE}"
mkdir -p "$REPORT_DIR"
# Recorder creates this directory itself; it must not exist yet
TRACE_DIR="$(pwd)/${REPORT_DIR}/trace_${SLURM_JOB_ID}"
[ -e "$TRACE_DIR" ] && { echo "ERROR: $TRACE_DIR already exists"; exit 1; }

PAYLOAD_DIR="payload/${VARIANT}_${CASE}_${SLURM_JOB_ID}"
mkdir -p "$PAYLOAD_DIR"
# Ensure leftover payload is cleaned up even on failure/scancel/timeout
trap 'rm -rf "$PAYLOAD_DIR"' EXIT

export OMPI_MCA_pml=ucx                  # fail loudly instead of falling back to another PML
export UCX_POSIX_USE_PROC_LINK=n         # same shm mechanism as the container (see container script)

# Recorder settings go to the IOR ranks only (-x), never to mpirun itself.
# POSIX and MPI-IO tracing are on by default; MPI (non-I/O) tracing stays off.
MPIRUN="mpirun -np $SLURM_NTASKS --map-by ppr:16:socket --bind-to core -x UCX_POSIX_USE_PROC_LINK $LOCK_FLAG \
  -x LD_PRELOAD=$RECORDER_INSTALL/lib/librecorder.so -x RECORDER_TRACES_DIR=$TRACE_DIR"

echo "=== Environment ==="
echo "Node: $(hostname)  Job: $SLURM_JOB_ID  Tasks: $SLURM_NTASKS"
echo "Variant: $VARIANT  Case: $CASE  B: $B  REPS: $REPS  OMPIO lock: $LOCK"
echo "Load before: $(cat /proc/loadavg)"
mpirun --version | head -1
echo "Recorder: $RECORDER_INSTALL"

set -x
$MPIRUN "$IOR_BIN" \
  -a "$API" \
  -w \
  -t "$T" -b "$B" \
  -m -g -d 5 -c -i "$REPS" \
  -o "${PAYLOAD_DIR}/testfile_${CASE}" \
  > "${REPORT_DIR}/ior_${SLURM_JOB_ID}.txt"
MPIRUN_EXIT=$?
set +x

echo "Load after: $(cat /proc/loadavg)"

if [ "$MPIRUN_EXIT" -ne 0 ]; then
    echo "FAILED: $CASE (mpirun exit code $MPIRUN_EXIT)"
    exit "$MPIRUN_EXIT"
fi

# Recorder writes its traces at MPI_Finalize; confirm, then convert to text
[ -s "$TRACE_DIR/recorder.mt" ] || [ -n "$(ls -A "$TRACE_DIR" 2>/dev/null)" ] \
    || { echo "FATAL: no Recorder trace in $TRACE_DIR"; exit 1; }
echo "Trace: $TRACE_DIR ($(du -sh "$TRACE_DIR" | cut -f1))"
recorder-summary "$TRACE_DIR" > "${REPORT_DIR}/summary_${SLURM_JOB_ID}.txt" 2>&1 \
    || echo "WARNING: recorder-summary failed (see ${REPORT_DIR}/summary_${SLURM_JOB_ID}.txt)"
recorder2text "$TRACE_DIR" > /dev/null 2>&1 \
    || { echo "FATAL: recorder2text failed"; exit 1; }

# Quick check that the lock calls were caught: fcntl lines in the text traces
# (each line starts with "<start> <end> <function> ...")
awk '$3 ~ /fcntl/ { n++; d = $2 - $1; if (d > max) max = d; if (d >= 29) long++ }
     END { printf "fcntl calls: %d, longest: %.2f s, >= 29 s: %d\n", n, max, long }' \
    "$TRACE_DIR"/_text/*.txt
grep -hoE '^[0-9.]+ [0-9.]+ [A-Za-z_0-9]+' "$TRACE_DIR"/_text/*.txt | awk '{print $3}' \
    | sort | uniq -c | sort -rn | head -15 | sed 's/^/  /'

echo "Completed Successfully! "
