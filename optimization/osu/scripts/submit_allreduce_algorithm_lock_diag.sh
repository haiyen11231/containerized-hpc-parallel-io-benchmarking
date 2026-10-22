#!/bin/bash
cd "$(dirname "$0")"

# ALG=0 is the control (= the already-measured baseline, no override).
# 3 = recursive doubling, 6 = Rabenseifner -- two representative non-default
# algorithms from OpenMPI 4.1's tuned Allreduce set.
ALGS=(0 3 6)
NP_LIST=(32 64 128)
REPS=${REPS:-10}

mkdir -p logs

for ALG in "${ALGS[@]}"; do
  for NP in "${NP_LIST[@]}"; do
    JOBNAME="osu_native_allreduce_alglock_a${ALG}_np${NP}"
    echo "Submitting ${JOBNAME} (alg: ${ALG}, np: ${NP}, reps: ${REPS})..."
    qsub -N "$JOBNAME" -o "logs/${JOBNAME}.out" \
         -l select=1:ncpus=${NP}:mpiprocs=${NP}:mem=16gb \
         -v NP=${NP},ALG=${ALG},REPS=${REPS} \
         osu_native_allreduce_algorithm_lock_diag.pbs
  done
done
