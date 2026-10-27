#!/bin/bash
cd "$(dirname "$0")"

NODE_COUNTS=(1 2 4 8)

COMBOS=(
  "MPIIO shared"
  "POSIX fpp"
)

mkdir -p logs

for NODES in "${NODE_COUNTS[@]}"; do
  for combo in "${COMBOS[@]}"; do
    read -r API MODEL <<< "$combo"
    API_LOWER=$(echo "$API" | tr '[:upper:]' '[:lower:]')
    JOBNAME="ior_native_inter_weak_${NODES}n_${API_LOWER}_${MODEL}"
    OUTFILE="logs/${JOBNAME}.out"

    echo "Submitting ${JOBNAME} (Nodes: ${NODES}, API: ${API}, Model: ${MODEL})..."

    qsub -N "$JOBNAME" \
         -o "$OUTFILE" \
         -l select=${NODES}:ncpus=64:mpiprocs=64:mem=64gb \
         -v NODE_COUNT=${NODES},API=${API},MODEL=${MODEL} \
         ior_native_inter_weak.pbs
  done
done
