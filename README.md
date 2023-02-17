# cobrabench

Lightweight tool to create reproducible benchmarks for copperhead.

Example usage:
```
python cobrabench.py examples/toy/cobra_config.json examples/toy/bench_config.json
```

The first argument `cobra_config.json` contains things like the number of cores on each node, the location of runsolver, and the number of memory lines. The tool tries to ensure that each job always gets the memory lines exclusely. This file is optional and if left out, it will assume default settings w.r.t. the cluster and except runsolver to in the path. 

The second argument `bench_config.json` contains parameters specific to the current benchmark like the executable that should be run. Required fields are `name`, `configs`, `instances`, `timeout`, `mem_limit` and `request_cpus`. The `configs` and `instances` parameter take txt files as values which contain the args and, respectively, the instances to be tested. Each config is run for every instance (the respective lines are concatenated). Optionally, an `executable` can be specified which is prepended to every config-instance pair. 

There are three meta-arguments which can be used in the config files. Namely, `$seed`, `$timeout` and `$log_folder`. During job generation they are replaced with the respective values where the `$seed` is randomly generated. The initial seed for this generation can be specified with the optional field `initial_seed` in the bench config. Furthermore, since `timeout` is assumed to be in seconds, it is possible to factor that value with the optional `timeout_factor` parameter before it is subsituted with `$timeout`. 

cobrabench then creates the following folder structure and files:
```
[benchmark name]
|__config1
   |__instance2
      |__run1
         |__job.sh
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
|__sbatch.sh
```

The file `sbatch.sh` can then be submitted to schedule each `job.sh`.  

The config and instance folders are numbered in the given order, but cobrabench also creates a json file `metadata.json` linking them to what was specified in `config.txt` and `instances.txt`.

An example of how the results can be processed is given [here](examples/tlsp/evaluation.py). Do not do this on the cluster, but rather copy the files to your machine first.

