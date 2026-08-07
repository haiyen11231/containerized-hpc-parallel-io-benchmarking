#include<mpi.h>
#include<stdio.h>

int main(int argc, char** argv) {
    // Initialize MPI environment
    MPI_Init(&argc, &argv);

    // Get the number of processes
    int world_size;
    MPI_Comm_size(MPI_COMM_WORLD, &world_size);

    // Get the rank of the process
    int world_rank;
    MPI_Comm_rank(MPI_COMM_WORLD, &world_rank);

    // Get the name of the processor/node
    char processor_name[MPI_MAX_PROCESSOR_NAME];
    int name_len;
    MPI_Get_processor_name(processor_name, &name_len);

    printf("Rank %d out of %d processes on processor/node %s\n", world_rank, world_size, processor_name);

    MPI_Barrier(MPI_COMM_WORLD); // Synchronize all processes

    // Finalize MPI environment.
    MPI_Finalize();
    return 0;
}