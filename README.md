# cobrabench

Lightweight tool to create reproducible benchmarks for cobra.

Example usage:
```
python cobrabench.py examples/toy/cobra_config.json examples/toy/bench_config.json examples/toy/configs.txt examples/toy/instances.txt
```

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

Furthermore, cobrabench also creates condor submit file which contains a job for each run (the `job.sh` in the respective folder).

The config and instance folders are numbered in the given order, but cobrabench also creates json files linking them to what was specified in `config.txt` and `instances.txt`.

An example of how the results can be processed, is given in [here](examples/tlsp/evaluation.py). Do not do this on the cluster, but rather copy the files to your machine first.
