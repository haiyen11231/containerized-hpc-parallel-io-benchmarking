#!/bin/bash
cd "$(dirname "$0")"

# pt2pt has two kernels:
#   osu_latency - round-trip time for a single message, small sizes dominate
#   osu_bw      - sustained bandwidth with a window of outstanding messages
BENCHES=(latency bw)

REPS=${REPS:-10}

mkdir -p logs

for B in "${BENCHES[@]}"; do
  JOBNAME="osu_container_pt2pt_intra_${B}"
  OUTFILE="logs/${JOBNAME}.out"

  # ncpus matches mpiprocs -- the convention used throughout this project (see
  # IOR's 16- and 64-rank jobs). Exclusivity comes from place=excl in the .pbs,
  # not from inflating ncpus: PBS reports the node as job-exclusive either way,
  # so no other job shares the hardware. Asking for 128 would only make the job
  # far harder to schedule (measured: 16s to start at ncpus=2, >25min at 128).
  echo "Submitting ${JOBNAME} (bench: ${B}, reps: ${REPS})..."

  qsub -N "$JOBNAME" \
       -o "$OUTFILE" \
       -l select=1:ncpus=2:mpiprocs=2:mem=8gb \
       -v BENCH=${B},REPS=${REPS} \
       osu_container_pt2pt_intra.pbs
done
