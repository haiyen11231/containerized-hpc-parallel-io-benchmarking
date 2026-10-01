#!/bin/bash
cd "$(dirname "$0")"

NODE_COUNTS=(1 2 4 8)
APIS=(POSIX MPIIO)
MODELS=(shared fpp)

mkdir -p logs

for NODES in "${NODE_COUNTS[@]}"; do
  for API in "${APIS[@]}"; do
    API_LOWER=$(echo "$API" | tr '[:upper:]' '[:lower:]')
    for MODEL in "${MODELS[@]}"; do
      JOBNAME="ior_native_inter_weak_${NODES}n_${API_LOWER}_${MODEL}"
      OUTFILE="logs/${JOBNAME}.out"

      echo "Submitting ${JOBNAME} (Nodes: ${NODES}, API: ${API}, Model: ${MODEL})..."

      qsub -N "$JOBNAME" \
           -o "$OUTFILE" \
           -l select=${NODES}:ncpus=128:mpiprocs=128:mem=64gb \
           -v NODE_COUNT=${NODES},API=${API},MODEL=${MODEL} \
           ior_native_inter_weak.pbs

    done
  done
done

