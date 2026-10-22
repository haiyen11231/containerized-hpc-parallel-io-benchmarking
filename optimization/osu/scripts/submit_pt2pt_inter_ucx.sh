#!/bin/bash
cd "$(dirname "$0")"
BENCHES=(latency bw)
REPS=${REPS:-10}
mkdir -p logs
for B in "${BENCHES[@]}"; do
  JOBNAME="osu_container_pt2pt_inter_ucx_${B}"
  echo "Submitting ${JOBNAME} (bench: ${B}, reps: ${REPS})..."
  # Identical resources to the baseline inter-node pt2pt jobs, so the only
  # difference between baseline and optimized is the MCA transport flag.
  qsub -N "$JOBNAME" -o "logs/${JOBNAME}.out" \
       -l select=2:ncpus=1:mpiprocs=1:mem=8gb \
       -v BENCH=${B},REPS=${REPS} \
       osu_container_pt2pt_inter_ucx.pbs
done
