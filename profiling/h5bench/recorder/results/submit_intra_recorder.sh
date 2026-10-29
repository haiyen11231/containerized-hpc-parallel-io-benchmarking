#!/bin/bash
cd "$(dirname "$0")"

# Experiment description: Run h5bench intra-node, both combos (CONTIG_CONTIG
# and INTERLEAVED_CONTIG), on both native and container, with Recorder
# tracing the MPI-IO/POSIX/HDF5 calls.
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
    JOBNAME="h5bench_${VARIANT}_intra_recorder_${MEM_LOWER}_${FILE_LOWER}"
    echo "Submitting ${JOBNAME} (MEM=${MEM} FILE=${FILE})..."
    qsub -N "$JOBNAME" -o "logs/${JOBNAME}.out" \
         -l select=1:ncpus=64:mpiprocs=64:mem=32gb \
         -v MEM_PATTERN=${MEM},FILE_PATTERN=${FILE} \
         "h5bench_${VARIANT}_intra_recorder.pbs"
  done
done

