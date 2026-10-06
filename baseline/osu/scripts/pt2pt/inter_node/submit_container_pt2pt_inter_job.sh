#!/bin/bash
cd "$(dirname "$0")"

BENCHES=(latency bw)

REPS=${REPS:-10}

mkdir -p logs

for B in "${BENCHES[@]}"; do
  JOBNAME="osu_container_pt2pt_inter_${B}"
  OUTFILE="logs/${JOBNAME}.out"

  echo "Submitting ${JOBNAME} (bench: ${B}, reps: ${REPS})..."

  qsub -N "$JOBNAME" \
       -o "$OUTFILE" \
       -l select=2:ncpus=1:mpiprocs=1:mem=8gb \
       -v BENCH=${B},REPS=${REPS} \
       osu_container_pt2pt_inter.pbs
done
