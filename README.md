# copperbench

Lightweight tool to create reproducible benchmarks for copperhead.

Install it as a python module:
```
python -m pip install .
copperbench <bench_config_file>
```

The only argument `bench_config.json` contains parameters specific to the current benchmark like the executable that should be run. 
Required fields are:
* `name`: Name of the benchmark folder that will be generated.
* `configs`: Text file of configurations to be executed. One for each line.
* `instances`: Text file of instances to be used. One for each line.
* `timeout`: The time limit for each run in seconds. 
* `mem_limit`: The memory limit for each run in megabytes. 
* `request_cpus`: The number of cores used in parallel in each run. 

Further optional arguments:
* `executable`: Short hand for a string which gets prepended to each configuration (default: None).
* `runs`: Number of runs per config-instance pair (default: 1).
* `working_dir`: The directory from which given paths are assumed to be relative (default: None).
* `timeout_factor`: The factor with which `timeout` gets multiplied before it is passed to the config. (default: 1)
* `initial_seed`: The initial seed used for generating random seeds.
* `runsolver_term_delay`: The amount of seconds added to the run time before runsolver gracefully tries to end the executable (default: 5).
* `runsolver_kill_delay`: The amount of seconds added to the run time before runsolver forcefully tries to end the executable (default: 5).
* `slurm_time_buffer`: The amount of seconds added to the run time before slurm ends the job (default: 10).
* `exclusive`: Whether the benchmark should be run exclusively on each node (default: `false`).
* `cpu_freq`: The used CPU frequency in MHz (max. 2900MHz). Default is the baseline frequency of 2200MHz. Higher values should be used at your own risk as they can increase non-reproducability.

Advanced parameters (usually do not need changing):
* `partition`: The slurm partition to which the jobs get submitted (default: `"broadwell"`)
* `cpus_per_node`: Number of CPU cores per node (default: 24).
* `mem_lines`: Number of memory lines to be used per node (default: 8).
* `use_perf`: Whether `perf` should be used for monitoring (default: `true`).
* `symlink_working_dir`: Whether symlinks should be created in the run dir so that the solver can find potentially referenced files (default: `true`).
* `runsolver_path`: The path to the runsolver binary.
* `billing`: The SLURM account the job will be billed to (default `None`).
* `max_parallel_jobs`: The maximum number of jobs that will be executed in parallel (default `None` which means no limit).
* `instances_are_parameters`: Specifies that the instance file contains parameters rather than files (default `false`).
* `data_to_main_mem`: Copy instance files into main memory (default `true`).
* `exclude_nodes`: Names of compute nodes to be excluded from job execution. Specify as a comma-separated string or list of node names (default `None`).

There are three meta-arguments which can be used in the executable string and config files. Namely, `$seed`, `$timeout`, `$file{<path/to/file>}`. During job generation the first two are replaced with the respective values where the `$seed` is randomly generated. The initial seed for this generation can be specified with the optional field `initial_seed` in the bench config. 
Furthermore, since `timeout` is assumed to be in seconds, it is possible to factor that value with the optional `timeout_factor` parameter before it is substituted with `$timeout`.  
The meta-argument `$file{<path/to/file>}` can be used to specify files which should be copied into main memory before the actual solver gets executed. This ensures that the solver execution is unfaced by potential delays of the NFS or disk. Note that the solver output is always written into main memory and only copied back into the run directory after completion of the job. Furthermore, any additional output files can simply be written in the current directory w.r.t. the solver, those files are copied into `[benchmark name]/configX/instanceX/runX/` as well.

The instance files are supposed to contain files only, which will be automatically copied into main memory before solver execution. You can supply multiple files (separated by space, comma or semicolon) and if need be reference them in the config. See [here](examples/tlsp/) for an example.

The tool tries to ensure that each job always gets the memory lines exclusively, which in practice means that each job is always scheduled on at least 3 cores and the number of requested cores is always a multiple of 3 (cpus / mem lines = 24 / 8 = 3). 

copperbench then creates the following folder structure and files:
```
[benchmark name]
|__config1
   |__instance2
      |__run1
         |__start.sh
         |__stdout.log
         |__stderr.log
         |__...
      |__run2
      |__ ...
   |__instance1
   |__ ...
|__config2
|__ ...
|__slurm_logs
|__metadata.json
|__start_list.txt
|__batch_job.slurm
|__compress_results.slurm
|__submit_all.sh
```

The file `batch_job.slurm` can then be submitted with `sbatch` to schedule each `start.sh` and `compress_results.slurm` can be submitted to tar the whole benchmark folder for easier download.
Furthermore, calling the script `submit_all.sh` schedules both `batch_job.slurm` and `compress_results.slurm` such that the compression is only performed after all runs have finished.

The config and instance folders are numbered in the given order, but copperbench also creates a json file `metadata.json` linking them to what was specified in `config.txt` and `instances.txt`.

An example of how the results can be processed is given [here](examples/tlsp/evaluation.py). Do not do this on the cluster, but rather copy the files to your machine first.

