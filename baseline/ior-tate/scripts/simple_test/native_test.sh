#!/bin/bash
#SBATCH --job-name=native_test
#SBATCH --nodes=1
#SBATCH --nodelist=tate01
#SBATCH --exclusive
#SBATCH --ntasks-per-node=4
#SBATCH --time=00:03:00
#SBATCH --output=logs/%x_%j.out       # %x = job name, %j = job ID -> one log per run
#SBATCH --error=logs/%x_%j.err

# Experiment description: Smoke test for native IOR on TATE. 4 ranks on one
# node, 16 MiB per rank, POSIX file-per-process then MPI-IO shared file,
# writing to NFS /home. Only checks that IOR + mpirun + UCX + NFS work!!!
# Launch line and UCX settings are identical to container_test.sh.
#
# Submit from your experiments directory (logs/ and data_<jobid>/ are created there):
#   mkdir -p logs && sbatch native_test.sh

IOR_BIN=$HOME/native/ior/ior-4.0.0/install/bin/ior
DATA_DIR=$SLURM_SUBMIT_DIR/data_${SLURM_JOB_ID}   # inside the experiments dir you submit from

# Fail early if the binary is missing instead of 4 confusing mpirun errors
[ -x "$IOR_BIN" ] || { echo "ERROR: IOR binary not found at $IOR_BIN"; exit 1; }

mkdir -p "$DATA_DIR"
# Remove the payload even if a test fails or the job is cancelled
trap 'rm -rf "$DATA_DIR"' EXIT

# Force UCX so the job fails loudly instead of silently falling back to another transport
export OMPI_MCA_pml=ucx
# Not needed natively, but set here too so native and container use the same
# UCX shared-memory mechanism (see container_test.sh)
export UCX_POSIX_USE_PROC_LINK=n

echo "Node: $(hostname)  Job: $SLURM_JOB_ID  Tasks: $SLURM_NTASKS"
echo "IOR:  $IOR_BIN"
echo "Data: $DATA_DIR"

# mpirun reads the node list and slot count from the Slurm allocation; OMPI_MCA_*
# variables are forwarded to every rank automatically, other variables need -x.
MPIRUN="mpirun -np $SLURM_NTASKS --bind-to core -x UCX_POSIX_USE_PROC_LINK"

echo "=== Test 1: POSIX, file-per-process ==="
$MPIRUN "$IOR_BIN" -a POSIX -F -w -r -C -e -t 1m -b 16m -i 3 \
    -o "$DATA_DIR/posix_fpp"
echo "Test 1 exit code: $?"

echo "=== Test 2: MPI-IO, shared file ==="
$MPIRUN "$IOR_BIN" -a MPIIO -c -w -r -C -t 1m -b 16m -i 3 \
    -o "$DATA_DIR/mpiio_shared"
echo "Test 2 exit code: $?"

echo "Done"
