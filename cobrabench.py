
import os
import stat
import string
import random
import math
import json
import sys
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any, TypedDict

DEFAULT_RUN_SOLVER_KILL_DELAY = 10
DEFAULT_TIME_BUFFER = 1
DEFAULT_N_MEM_LINES = 4
DEFAULT_N_CPUS = 24
DEFAULT_PARTITION = 'broadwell'

class BenchConfig(TypedDict):
    name: str
    instances: str
    configs: str
    timeout: int
    request_cpus: int
    mem_limit: int
    runs: Optional[int]
    executable: Optional[str]
    working_dir: Optional[str]
    runsolver_path: Optional[str]
    runsolver_kill_delay: Optional[int]
    slurm_time_buffer: Optional[int]
    timeout_factor: Optional[int]
    initial_seed: Optional[int]
    partition: Optional[str]
    cpu_per_node: Optional[int]
    mem_lines: Optional[int]


def process_bench(bench_folder: Path, log_read_func: Callable[[Path], Optional[Dict[str, Any]]], 
                  metadata_file: Optional[str] = None) -> List[Dict[str, Any]]:
    if metadata_file != None:
        with open(metadata_file, 'r') as file:
            metadata = json.loads(file.read())
    else:
        metadata = None

    data = []
    for config_dir in os.scandir(bench_folder):
        if config_dir.name.startswith('config') and os.path.isdir(config_dir):
            for instance_dir in os.scandir(config_dir):
                if instance_dir.name.startswith('instance') and os.path.isdir(instance_dir):
                    for run_dir in os.scandir(instance_dir):
                        if run_dir.name.startswith('run') and os.path.isdir(run_dir):
                            result = log_read_func(Path(run_dir, 'stdout.log'))
                            if result:
                                if metadata != None:
                                    conf_name = metadata['configs'][config_dir.name]
                                    inst_name = metadata['instances'][instance_dir.name]
                                else:
                                    conf_name = config_dir.name
                                    inst_name = instance_dir.name
                                entry = {}
                                entry['config'] = conf_name
                                entry['instance'] = inst_name
                                entry['run'] = run_dir.name[3:]
                                data += [entry | result]

    return data


def main(bench_config : BenchConfig) -> None:

    # required fields
    bench_name = bench_config['name']
    instances_file = bench_config['instances']
    configs_file = bench_config['configs']
    timeout = bench_config['timeout']
    mem_limit = bench_config['mem_limit']
    request_cpu = bench_config['request_cpus']

    # optional fields
    macro_default = lambda k,d : d if not k in bench_config else bench_config[k]
    runsolver_path = macro_default('runsolver_path', 'runsolver')
    mem_lines = macro_default('mem_lines', DEFAULT_N_MEM_LINES)
    cpu_per_node = macro_default('cpu_per_node', DEFAULT_N_CPUS)
    partition = macro_default('partition', DEFAULT_PARTITION)
    n_runs = macro_default('runs', 1)
    runsolver_kill_delay = macro_default('runsolver_kill_delay', DEFAULT_RUN_SOLVER_KILL_DELAY)
    time_buffer = macro_default('slurm_time_buffer', DEFAULT_TIME_BUFFER)
    exec_path = macro_default('executable', None)
    timeout_factor = macro_default('timeout_factor', 1)

    working_dir = None
    if 'working_dir' in bench_config:
        working_dir = os.path.relpath(str(bench_config['working_dir']), start=Path.home())

    if 'initial_seed' in bench_config:
        random.seed(bench_config['initial_seed'])
    
    cpus = int(math.ceil(request_cpu / (cpu_per_node / mem_lines)) * (cpu_per_node / mem_lines))

    instances = {}
    with open(instances_file, 'r') as file:
        i = 1
        for line in file:
            instance = line.strip()
            if not instance.startswith('#') and len(instance) > 0:
                instances[f'instance{i}'] = instance
                i += 1

    configs = {}
    with open(configs_file, 'r') as file:
        i = 1
        for line in file:
            config = line.strip()
            if not config.startswith('#') and len(config) > 0:
                configs[f'config{i}'] = config
                i += 1
    
    os.mkdir(bench_name)

    with open(Path(bench_name, 'metadata.json'), 'w') as file:
        metadata = {}
        metadata['instances'] = instances
        metadata['configs'] = configs
        file.write(json.dumps(metadata, indent=4))

    counter = 0
    for config_name, config in configs.items():
        for instance_name, data in instances.items():
            for i in range(1, n_runs + 1):

                log_folder = Path(bench_name, config_name, instance_name, f'run{i}')
                os.makedirs(log_folder)

                job_file = 'start.sh'
                job_path = log_folder / job_file

                run =  f'{config} {data}'

                if exec_path != None:
                    run =  f'{exec_path} {run}'
                    
                cmd = f'{runsolver_path} -w runsolver.log -W {timeout+time_buffer} -V {mem_limit} -d {runsolver_kill_delay} {run} 2> stderr.log 1> stdout.log'

                with open(job_path, 'w') as file:
                    file.write('#!/bin/sh\n\n')
                    file.write('# change into job directory\n')
                    file.write(f'cd ~/{os.path.relpath(log_folder, start=Path.home())}\n')
                    if working_dir != None:
                        file.write('# create log files (so that symlinks cannot interfere)\n')
                        file.write('touch runsolver.log stdout.log stderr.log\n')
                        file.write('# create symlinks for working directory\n')
                        file.write(f'ln -s ~/{working_dir}/* .\n')
                    file.write('# execute run\n')
                    cmd = string.Template(cmd).substitute(timeout=timeout * timeout_factor, seed=random.randint(0,2**32))
                    file.write(cmd)
                    file.write('\n')
                    if working_dir != None:
                        file.write('# cleanup symlinks\n')
                        file.write('find . -type l -delete\n')

                st = os.stat(job_path)
                os.chmod(job_path, st.st_mode | stat.S_IEXEC)
                counter += 1
    
    with open(Path(bench_name, 'batch_job.slurm'), 'w') as file:
        file.write('#!/bin/bash\n')
        file.write('#\n')
        file.write(f'#SBATCH --job-name={bench_name}\n')
        file.write(f'#SBATCH --time={datetime.timedelta(seconds=timeout+time_buffer)}\n')
        file.write(f'#SBATCH --partition={partition}\n')
        file.write(f'#SBATCH --cpus-per-task={cpus}\n')
        file.write(f'#SBATCH --mem-per-cpu={int(math.ceil(mem_limit/cpus))}\n')
        file.write(f'#SBATCH --output={bench_name}.log\n')
        file.write(f'#SBATCH --error={bench_name}.log\n')
        file.write(f'#SBATCH --array=0-{counter - 1}\n')
        file.write('#SBATCH --ntasks=1\n\n')
        file.write(f'cd ~/{os.path.relpath(os.curdir, start=Path.home())}\n')
        file.write(f'FILES=(config*/instance*/run*/start.sh)\n\n')
        file.write('srun ${FILES[$SLURM_ARRAY_TASK_ID]}\n')
        
if __name__ == "__main__":
    if len(sys.argv) == 2:
        bench_config_file = sys.argv[1]
    else:
        print("usage: cobrabench.py <bench_config_file>")
        sys.exit(1)
    
    with open(bench_config_file, 'r') as file:
        bench_config : BenchConfig = json.loads(file.read())

    main(bench_config)