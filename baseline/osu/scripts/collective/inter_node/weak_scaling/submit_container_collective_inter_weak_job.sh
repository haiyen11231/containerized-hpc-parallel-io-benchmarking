#!/bin/bash
cd "$(dirname "$0")"

BENCHES=(allreduce alltoall)

# The scaling variable is NODE COUNT. 128 ranks per node means 2/4/8 nodes gives 256/512/1024 ranks, which
# picks up exactly where the intra-node study's 128-rank point left off.
NODE_COUNTS=(2 4 8)

REPS=${REPS:-10}

mkdir -p logs

for B in "${BENCHES[@]}"; do
  for N in "${NODE_COUNTS[@]}"; do
    JOBNAME="osu_container_collective_inter_weak_${B}_n${N}"
    OUTFILE="logs/${JOBNAME}.out"

    echo "Submitting ${JOBNAME} (bench: ${B}, nodes: ${N}, ranks: $((N*128)), reps: ${REPS})..."

    qsub -N "$JOBNAME" \
         -o "$OUTFILE" \
         -l select=${N}:ncpus=128:mpiprocs=128:mem=64gb \
         -v BENCH=${B},NODES=${N},REPS=${REPS} \
         osu_container_collective_inter_weak.pbs
  done
done
