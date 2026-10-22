#!/bin/bash
cd "$(dirname "$0")"

# Same algorithm choices as the inter-node alglock experiments, for
# consistency: Rabenseifner for Allreduce, pairwise for Alltoall.
declare -A ALG_FOR=( [allreduce]=6 [alltoall]=2 )
MODES=(weak strong)
NP_LIST=(8 16 32 64 128)
REPS=${REPS:-10}

mkdir -p logs

for B in allreduce alltoall; do
  ALG=${ALG_FOR[$B]}
  for M in "${MODES[@]}"; do
    for NP in "${NP_LIST[@]}"; do
      JOBNAME="osu_container_collective_intra_alglock_${B}_${M}_np${NP}_a${ALG}"
      echo "Submitting ${JOBNAME} (bench: ${B}, mode: ${M}, np: ${NP}, alg: ${ALG}, reps: ${REPS})..."
      qsub -N "$JOBNAME" -o "logs/${JOBNAME}.out" \
           -l select=1:ncpus=${NP}:mpiprocs=${NP}:mem=16gb \
           -v BENCH=${B},MODE=${M},NP=${NP},ALG=${ALG},REPS=${REPS} \
           osu_container_collective_intra_alglock.pbs
    done
  done
done
