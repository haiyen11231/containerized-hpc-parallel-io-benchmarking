#!/bin/bash
cd "$(dirname "$0")"

# Two collectives with deliberately different cost shapes:
#   osu_allreduce - every rank contributes, all receive the result.
#                   O(log P) communication rounds, latency-dominated.
#   osu_alltoall  - every rank sends DISTINCT data to every other rank.
#                   O(P) traffic per rank, bandwidth-dominated. Worst case.
BENCHES=(allreduce alltoall)

# The scaling variable. All of these fit on ONE node (128 cores), so the whole
# sweep stays intra-node and no network is ever involved.
NP_LIST=(8 16 32 64 128)

REPS=${REPS:-10}

mkdir -p logs

for B in "${BENCHES[@]}"; do
  for NP in "${NP_LIST[@]}"; do
    JOBNAME="osu_native_collective_weak_${B}_np${NP}"
    OUTFILE="logs/${JOBNAME}.out"

    echo "Submitting ${JOBNAME} (bench: ${B}, np: ${NP}, reps: ${REPS})..."

    qsub -N "$JOBNAME" \
         -o "$OUTFILE" \
         -l select=1:ncpus=${NP}:mpiprocs=${NP}:mem=16gb \
         -v BENCH=${B},NP=${NP},REPS=${REPS} \
         osu_native_collective_weak.pbs
  done
done
