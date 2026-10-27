#!/bin/bash
cd "$(dirname "$0")"

# H7's two-cell comparison per variant: dno_mno (reference) vs dyes_mno (the
# cell where container's gain resolves and native's doesn't). COLLECTIVE_METADATA
# is fixed NO throughout -- see GUIDE.md for why that switch is not re-tested.
COLL_DATA_VALUES=(NO YES)

mkdir -p logs

for VARIANT in native container; do
  for CD in "${COLL_DATA_VALUES[@]}"; do
    CD_LOWER=$(echo "$CD" | tr '[:upper:]' '[:lower:]')
    JOBNAME="h5bench_${VARIANT}_collective_recorder_d${CD_LOWER}"
    echo "Submitting ${JOBNAME} (COLL_DATA=${CD})..."
    qsub -N "$JOBNAME" -o "logs/${JOBNAME}.out" \
         -l select=2:ncpus=128:mpiprocs=128:mem=64gb \
         -v COLL_DATA=${CD} \
         "h5bench_${VARIANT}_collective_recorder.pbs"
  done
done
