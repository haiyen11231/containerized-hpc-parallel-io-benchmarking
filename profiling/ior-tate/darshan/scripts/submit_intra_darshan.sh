#!/bin/bash
# Submits the intra-node Darshan profiling set: 3 cases x {native, container},
# one job each (6 jobs on tate01). Native and container for the same case are
# submitted back to back.
#
#   ./submit_intra_darshan.sh          # all 3 cases
#   ./submit_intra_darshan.sh 1        # only case 1 (numbers as listed below)
cd "$(dirname "$0")"

# API MODEL T LOCK REPS   (LOCK: default | fs_ufs_lock_algorithm value | - for POSIX)
# 64k throughout: the largest locking effect (x18) and the most calls per rank,
# so any per-call difference between native and container is largest here.
CASES=(
  "MPIIO shared 64k default 3"   # 1: where the x18 goes -- 30 s stalls, so fewer reps
  "MPIIO shared 64k 3 5"         # 2: lock fix, pair with case 1; same-I/O check for MPI-IO
  "POSIX fpp 64k - 5"            # 3: same-I/O check for POSIX (4096 writes per rank)
)

if [ $# -gt 0 ]; then PICK=("$@"); else PICK=($(seq 1 ${#CASES[@]})); fi
for i in "${PICK[@]}"; do
  [[ "$i" =~ ^[0-9]+$ ]] && [ "$i" -ge 1 ] && [ "$i" -le ${#CASES[@]} ] \
    || { echo "Case number must be 1-${#CASES[@]}: $i"; exit 1; }
done

mkdir -p logs

for i in "${PICK[@]}"; do
  read -r API MODEL T LOCK REPS <<< "${CASES[$((i - 1))]}"
  API_LOWER=$(echo "$API" | tr '[:upper:]' '[:lower:]')
  TAG=""
  [ "$API" == "MPIIO" ] && TAG="_lock${LOCK}"
  for VARIANT in native container; do
    JOBNAME="darshan_${VARIANT}_${API_LOWER}_${MODEL}_t${T}${TAG}"
    echo "Submitting ${JOBNAME} (REPS=${REPS})..."

    sbatch -J "$JOBNAME" \
           -o "logs/${JOBNAME}_%j.out" \
           -e "logs/${JOBNAME}_%j.err" \
           --export="ALL,API=${API},MODEL=${MODEL},T=${T},LOCK=${LOCK},REPS=${REPS}" \
           "ior_${VARIANT}_intra_darshan.sbatch"
  done
done
