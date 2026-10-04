#!/bin/bash
cd "$(dirname "$0")"

MEM_PATTERNS=(CONTIG INTERLEAVED)
FILE_PATTERNS=(CONTIG INTERLEAVED)

REPS=${REPS:-10}

mkdir -p logs

for MEM in "${MEM_PATTERNS[@]}"; do
  MEM_LOWER=$(echo "$MEM" | tr '[:upper:]' '[:lower:]')
  for FILE in "${FILE_PATTERNS[@]}"; do
    FILE_LOWER=$(echo "$FILE" | tr '[:upper:]' '[:lower:]')
    JOBNAME="h5bench_container_intra_${MEM_LOWER}_${FILE_LOWER}"
    OUTFILE="logs/${JOBNAME}.out"

    echo "Submitting ${JOBNAME} (MEM: ${MEM}, FILE: ${FILE})..."

    qsub -N "$JOBNAME" \
         -o "$OUTFILE" \
         -l select=1:ncpus=128:mpiprocs=128:mem=64gb \
         -v MEM_PATTERN=${MEM},FILE_PATTERN=${FILE},REPS=${REPS} \
         h5bench_container_intra.pbs
  done
done
