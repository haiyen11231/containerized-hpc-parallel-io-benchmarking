#!/bin/bash
# Submits the intra-node MPI-IO shared lock-fix runs (fs_ufs_lock_algorithm 3), native
# then container for each run index, to compare against the default-locking runs 1-3.
# Results: <variant>/mpiio/shared_lock3/run<RUN>/ior_t*.txt (an existing run is refused).
#
#   ./submit_intra_lockfix.sh          # run 1
#   ./submit_intra_lockfix.sh 2 3      # runs 2 and 3
cd "$(dirname "$0")"

if [ $# -gt 0 ]; then RUNS=("$@"); else RUNS=(1); fi

for RUN in "${RUNS[@]}"; do
  [[ "$RUN" =~ ^[0-9]+$ ]] || { echo "Run index must be a number: $RUN"; exit 1; }
done

mkdir -p logs

for RUN in "${RUNS[@]}"; do
  for VARIANT in native container; do
    JOBNAME="ior_${VARIANT}_intra_mpiio_shared_lock3_run${RUN}"
    echo "Submitting ${JOBNAME}..."

    sbatch -J "$JOBNAME" \
           -o "logs/${JOBNAME}_%j.out" \
           -e "logs/${JOBNAME}_%j.err" \
           --export="ALL,RUN=${RUN}" \
           "ior_${VARIANT}_intra_lockfix.sbatch"
  done
done
