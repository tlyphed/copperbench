# copperbench

Lightweight tool to create reproducible benchmarks for copperhead.

You can either use it as a script:
```
python copperbench.py <bench_config_file>
```

or install it as a python module:
```
python -m pip install .
copperbench <bench_config_file>
```

The only argument `bench_config.json` contains parameters specific to the current benchmark like the executable that should be run. Required fields are `name`, `configs`, `instances`, `timeout`, `mem_limit` and `request_cpus`. The `configs` and `instances` parameter take txt files as values which contain the args and, respectively, the instances to be tested. Each config is run for every instance (the respective lines are concatenated). Optionally, an `executable` can be specified which is prepended to every config-instance pair. 

There are two meta-arguments which can be used in the config files. Namely, `$seed` and `$timeout`. During job generation they are replaced with the respective values where the `$seed` is randomly generated. The initial seed for this generation can be specified with the optional field `initial_seed` in the bench config. Furthermore, since `timeout` is assumed to be in seconds, it is possible to factor that value with the optional `timeout_factor` parameter before it is subsituted with `$timeout`.  

Advanced optional fields are the number of cores on each node, the location of runsolver, the number of memory lines and the slurm partition to be used. The tool tries to ensure that each job always gets the memory lines exclusely, which in practice means that each job is always scheduled on at least 6 cores and the number of requested cores is always a multiple of 6 (cpus / mem lines = 24 / 4 = 6). 

copperbench then creates the following folder structure and files:
```
[benchmark name]
|__config1
   |__instance2
      |__run1
         |__start.sh
         |__stdout.log
         |__stderr.log
         |__runsolver.log
      |__run2
      |__ ...
   |__instance1
   |__ ...
|__config2
|__ ...
|__metadata.json
|__batch_job.slurm
```

The file `batch_job.slurm` can then be submitted with `sbatch` to schedule each `start.sh`.  

The config and instance folders are numbered in the given order, but cobrabench also creates a json file `metadata.json` linking them to what was specified in `config.txt` and `instances.txt`.

An example of how the results can be processed is given [here](examples/tlsp/evaluation.py). Do not do this on the cluster, but rather copy the files to your machine first.

