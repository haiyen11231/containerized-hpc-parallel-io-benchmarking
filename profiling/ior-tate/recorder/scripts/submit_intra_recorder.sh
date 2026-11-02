#!/bin/bash
# Submits the intra-node Recorder tracing set: MPI-IO shared, -t 64k, default
# locking vs lock fix, x {native, container}, one job each (4 jobs on tate01).
# Native and container for the same case are submitted back to back.
#
#   ./submit_intra_recorder.sh         # both cases
#   ./submit_intra_recorder.sh 1       # only case 1 (numbers as listed below)
cd "$(dirname "$0")"

# T LOCK REPS   (LOCK: default | fs_ufs_lock_algorithm value)
# One repetition each: a default-locking repetition can take ~8 min, and
# Recorder logs every call of every rank.
CASES=(
  "64k default 1"   # 1: the lock call around every write, and the ~30 s waits inside it
  "64k 3 1"         # 2: lock fix -- those lock calls gone or rare
)

if [ $# -gt 0 ]; then PICK=("$@"); else PICK=($(seq 1 ${#CASES[@]})); fi
for i in "${PICK[@]}"; do
  [[ "$i" =~ ^[0-9]+$ ]] && [ "$i" -ge 1 ] && [ "$i" -le ${#CASES[@]} ] \
    || { echo "Case number must be 1-${#CASES[@]}: $i"; exit 1; }
done

mkdir -p logs

for i in "${PICK[@]}"; do
  read -r T LOCK REPS <<< "${CASES[$((i - 1))]}"
  for VARIANT in native container; do
    JOBNAME="recorder_${VARIANT}_mpiio_shared_t${T}_lock${LOCK}"
    echo "Submitting ${JOBNAME} (REPS=${REPS})..."

    sbatch -J "$JOBNAME" \
           -o "logs/${JOBNAME}_%j.out" \
           -e "logs/${JOBNAME}_%j.err" \
           --export="ALL,T=${T},LOCK=${LOCK},REPS=${REPS}" \
           "ior_${VARIANT}_intra_recorder.sbatch"
  done
done
