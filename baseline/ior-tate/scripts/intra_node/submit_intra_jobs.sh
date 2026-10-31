#!/bin/bash
# Submits the full intra-node study: RUNS rounds x 2 combos x {native, container}.
# Within each round, native and container for the same combo are submitted back
# to back, so background load on the shared NFS server hits both variants alike.
# All jobs are --exclusive on tate01 (set by #SBATCH --nodelist in both .sbatch
# files), so Slurm runs them one at a time.
#
#   ./submit_intra_jobs.sh                 # runs 1..3
#   RUNS=5 ./submit_intra_jobs.sh          # runs 1..5
cd "$(dirname "$0")"

RUNS=${RUNS:-3}

mkdir -p logs

COMBOS=(
  "MPIIO shared"
  "POSIX fpp"
)

for ((RUN = 1; RUN <= RUNS; RUN++)); do
  for combo in "${COMBOS[@]}"; do
    read -r API MODEL <<< "$combo"
    API_LOWER=$(echo "$API" | tr '[:upper:]' '[:lower:]')
    for VARIANT in native container; do
      JOBNAME="ior_${VARIANT}_intra_${API_LOWER}_${MODEL}_run${RUN}"
      echo "Submitting ${JOBNAME}..."

      sbatch -J "$JOBNAME" \
             -o "logs/${JOBNAME}_%j.out" \
             --export="ALL,API=${API},MODEL=${MODEL},RUN=${RUN}" \
             "ior_${VARIANT}_intra.sbatch"
    done
  done
done
