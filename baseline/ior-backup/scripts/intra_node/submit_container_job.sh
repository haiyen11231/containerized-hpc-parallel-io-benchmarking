#!/bin/bash
STRIPE_COUNTS=(1 8)
APIS=(POSIX MPIIO)
MODELS=(shared fpp)

mkdir -p logs

for C in "${STRIPE_COUNTS[@]}"; do
  for API in "${APIS[@]}"; do
    API_LOWER=$(echo "$API" | tr '[:upper:]' '[:lower:]')
    for MODEL in "${MODELS[@]}"; do
      JOBNAME="ior_container_intra_c${C}_${API_LOWER}_${MODEL}"
      echo "Submitting ${JOBNAME}..."

      qsub -N "$JOBNAME" \
           -o "logs/${JOBNAME}.out" \
           -v "STRIPE_COUNT=${C},API=${API},MODEL=${MODEL}" \
           ior_container_intra.pbs
    done
  done
done
