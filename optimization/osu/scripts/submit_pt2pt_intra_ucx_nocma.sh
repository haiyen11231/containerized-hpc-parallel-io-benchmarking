#!/bin/bash
cd "$(dirname "$0")"
BENCHES=(latency bw)
REPS=${REPS:-10}
mkdir -p logs
for B in "${BENCHES[@]}"; do
  JOBNAME="osu_container_pt2pt_intra_ucx_nocma_${B}"
  echo "Submitting ${JOBNAME} (bench: ${B}, reps: ${REPS})..."
  qsub -N "$JOBNAME" -o "logs/${JOBNAME}.out" \
       -l select=1:ncpus=2:mpiprocs=2:mem=8gb \
       -v BENCH=${B},REPS=${REPS} \
       osu_container_pt2pt_intra_ucx_nocma.pbs
done
