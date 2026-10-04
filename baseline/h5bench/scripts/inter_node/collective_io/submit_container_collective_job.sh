#!/bin/bash
cd "$(dirname "$0")"

# Compare the MPI-collective-communication effect
# (COLLECTIVE_DATA) from the HDF5-metadata-consolidation effect
# (COLLECTIVE_METADATA) instead of conflating them in one on/off switch.
COLL_DATA_OPTS=(NO YES)
COLL_META_OPTS=(NO YES)

# Fixed at 2 nodes = 256 ncpus -> routes to q5
NODES=2

REPS=${REPS:-10}

mkdir -p logs

for CD in "${COLL_DATA_OPTS[@]}"; do
  CD_LOWER=$(echo "$CD" | tr '[:upper:]' '[:lower:]')
  for CM in "${COLL_META_OPTS[@]}"; do
    CM_LOWER=$(echo "$CM" | tr '[:upper:]' '[:lower:]')
    JOBNAME="h5bench_container_collective_d${CD_LOWER}_m${CM_LOWER}"
    OUTFILE="logs/${JOBNAME}.out"

    echo "Submitting ${JOBNAME} (COLLECTIVE_DATA: ${CD}, COLLECTIVE_METADATA: ${CM}, Reps: ${REPS})..."

    qsub -N "$JOBNAME" \
         -o "$OUTFILE" \
         -l select=${NODES}:ncpus=128:mpiprocs=128:mem=64gb \
         -v COLL_DATA=${CD},COLL_META=${CM},REPS=${REPS} \
         h5bench_container_collective.pbs
  done
done
