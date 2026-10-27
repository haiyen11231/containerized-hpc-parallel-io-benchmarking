#!/bin/bash
cd "$(dirname "$0")"

mkdir -p logs

COMBOS=(
  "MPIIO shared"
  "POSIX fpp"
)

for combo in "${COMBOS[@]}"; do
  read -r API MODEL <<< "$combo"
  API_LOWER=$(echo "$API" | tr '[:upper:]' '[:lower:]')
  JOBNAME="ior_native_intra_${API_LOWER}_${MODEL}"
  echo "Submitting ${JOBNAME}..."

  qsub -N "$JOBNAME" \
       -o "logs/${JOBNAME}.out" \
       -v "API=${API},MODEL=${MODEL}" \
       ior_native_intra.pbs
done
