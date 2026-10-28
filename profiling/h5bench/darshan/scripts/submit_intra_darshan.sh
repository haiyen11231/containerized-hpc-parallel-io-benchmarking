#!/bin/bash
cd "$(dirname "$0")"

COMBOS=(
  "CONTIG CONTIG"
  "INTERLEAVED CONTIG"
)

mkdir -p logs

for VARIANT in native container; do
  for COMBO in "${COMBOS[@]}"; do
    read -r MEM FILE <<< "$COMBO"
    MEM_LOWER=$(echo "$MEM" | tr '[:upper:]' '[:lower:]')
    FILE_LOWER=$(echo "$FILE" | tr '[:upper:]' '[:lower:]')
    JOBNAME="h5bench_${VARIANT}_intra_darshan_${MEM_LOWER}_${FILE_LOWER}"
    echo "Submitting ${JOBNAME} (MEM=${MEM} FILE=${FILE})..."
    qsub -N "$JOBNAME" -o "logs/${JOBNAME}.out" \
         -l select=1:ncpus=64:mpiprocs=64:mem=32gb \
         -v MEM_PATTERN=${MEM},FILE_PATTERN=${FILE} \
         "h5bench_${VARIANT}_intra_darshan.pbs"
  done
done
