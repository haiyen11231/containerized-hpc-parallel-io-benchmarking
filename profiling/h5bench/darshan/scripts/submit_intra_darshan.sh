#!/bin/bash
cd "$(dirname "$0")"

# The 4 MEM_PATTERN x FILE_PATTERN combos from the baseline intra-node study.
COMBOS=(
  "CONTIG CONTIG"
  "CONTIG INTERLEAVED"
  "INTERLEAVED CONTIG"
  "INTERLEAVED INTERLEAVED"
)

# Darshan aggregates over the whole process lifetime -- a handful of reps is
# enough for a representative log, not the baseline's full REPS=10 (which
# exists to characterize run-to-run variance, not to generate more counters).
REPS=${REPS:-2}

mkdir -p logs

for VARIANT in native container; do
  for COMBO in "${COMBOS[@]}"; do
    read -r MEM FILE <<< "$COMBO"
    MEM_LOWER=$(echo "$MEM" | tr '[:upper:]' '[:lower:]')
    FILE_LOWER=$(echo "$FILE" | tr '[:upper:]' '[:lower:]')
    JOBNAME="h5bench_${VARIANT}_intra_darshan_${MEM_LOWER}_${FILE_LOWER}"
    echo "Submitting ${JOBNAME} (MEM=${MEM} FILE=${FILE} REPS=${REPS})..."
    qsub -N "$JOBNAME" -o "logs/${JOBNAME}.out" \
         -l select=1:ncpus=128:mpiprocs=128:mem=64gb \
         -v MEM_PATTERN=${MEM},FILE_PATTERN=${FILE},REPS=${REPS} \
         "h5bench_${VARIANT}_intra_darshan.pbs"
  done
done
