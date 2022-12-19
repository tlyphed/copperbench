# cobrabench

Lightweight tool to create reproducible benchmarks for cobra.

Example usage:
```
python cobrabench.py examples/toy/cobra_config.json examples/toy/bench_config.json examples/toy/configs.txt examples/toy/instances.txt
```

The first parameter `cobra_config.json` contains things like the number of cores on each node, the location of runsolver, and the number of memory lines. The tool tries to ensure that each job always gets at a memory line exclusely.
The second parameter `bench_config.json` contains parameters specific to the current benchmark like the executable that should be run. 
Lastly, `config.txt` and `instances.txt` contain the args to be tested as well the instances. Each config is run for every instance.

cobrabench then creates the following folder structure and files:
```
[benchmark name]
|__config1
   |__instance2
      |__run1
         |__job.sh
         |__stdout.log
         |__stderr.log
         |__condor.log
         |__runsolver.log
      |__run2
      |__ ...
   |__instance1
   |__ ...
|__config2
|__ ...
|__config_names.json
|__instance_names.json
|__[benchmark name].sub
```

The file `[benchmark name].sub` can then be submitted to schedule each `job.sh`.

The config and instance folders are numbered in the given order, but cobrabench also creates json files (`config_names.json` and `instance_names.json`) linking them to what was specified in `config.txt` and `instances.txt`.

An example of how the results can be processed, is given in [here](examples/tlsp/evaluation.py). Do not do this on the cluster, but rather copy the files to your machine first.

