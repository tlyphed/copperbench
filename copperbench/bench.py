import os
import stat
import string
import random
import math
import json
import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import argparse
from .__version__ import __version__


@dataclass
class BenchConfig:
    name: str
    instances: Path
    configs: Path
    timeout: int
    request_cpus: int
    mem_limit: int
    runs: int = 1
    executable: Optional[Path] = None
    working_dir: Optional[Path] = None
    runsolver_path: str = 'runsolver'
    runsolver_kill_delay: int = 10
    slurm_time_buffer: int = 1
    timeout_factor: int = 1
    initial_seed: Optional[int] = None
    partition: str = 'broadwell'
    cpu_per_node: int = 24
    mem_lines: int = 4


def main() -> None:
    
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                     description=f'copperbench (version {__version__})')
    parser.add_argument('bench_config_file') 
    args = parser.parse_args() 

    with open(args.bench_config_file, 'r') as file:
        bench_config = BenchConfig(**json.loads(file.read()))

    working_dir = None
    if bench_config.working_dir != None:
        working_dir = os.path.relpath(bench_config.working_dir, start=Path.home())

    if bench_config.initial_seed != None:
        random.seed(bench_config.initial_seed)
    
    cpus = int(math.ceil(bench_config.request_cpus / (bench_config.cpu_per_node / bench_config.mem_lines)) 
                         * (bench_config.cpu_per_node / bench_config.mem_lines))

    instances = {}
    with open(bench_config.instances, 'r') as file:
        i = 1
        for line in file:
            instance = line.strip()
            if not instance.startswith('#') and len(instance) > 0:
                instances[f'instance{i}'] = instance
                i += 1

    configs = {}
    with open(bench_config.configs, 'r') as file:
        i = 1
        for line in file:
            config = line.strip()
            if not config.startswith('#') and len(config) > 0:
                configs[f'config{i}'] = config
                i += 1
    
    os.mkdir(bench_config.name)

    with open(Path(bench_config.name, 'metadata.json'), 'w') as file:
        metadata = {}
        metadata['instances'] = instances
        metadata['configs'] = configs
        file.write(json.dumps(metadata, indent=4))

    counter = 0
    for config_name, config in configs.items():
        for instance_name, data in instances.items():
            for i in range(1, bench_config.runs + 1):

                log_folder = Path(bench_config.name, config_name, instance_name, f'run{i}')
                os.makedirs(log_folder)

                job_file = 'start.sh'
                job_path = log_folder / job_file

                run =  f'{config} {data}'

                if bench_config.executable != None:
                    run =  f'{bench_config.executable} {run}'
                    
                cmd = f'{bench_config.runsolver_path} -w runsolver.log -W {bench_config.timeout+bench_config.slurm_time_buffer} -V {bench_config.mem_limit} -d {bench_config.runsolver_kill_delay} {run} 2> stderr.log 1> stdout.log'

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
                    cmd = string.Template(cmd).substitute(timeout=bench_config.timeout * bench_config.timeout_factor, seed=random.randint(0,2**32))
                    file.write(cmd)
                    file.write('\n')
                    if working_dir != None:
                        file.write('# cleanup symlinks\n')
                        file.write('find . -type l -delete\n')

                st = os.stat(job_path)
                os.chmod(job_path, st.st_mode | stat.S_IEXEC)
                counter += 1
    
    with open(Path(bench_config.name, 'batch_job.slurm'), 'w') as file:
        file.write('#!/bin/bash\n')
        file.write('#\n')
        file.write(f'#SBATCH --job-name={bench_config.name}\n')
        file.write(f'#SBATCH --time={datetime.timedelta(seconds=bench_config.timeout+bench_config.slurm_time_buffer)}\n')
        file.write(f'#SBATCH --partition={bench_config.partition}\n')
        file.write(f'#SBATCH --cpus-per-task={cpus}\n')
        file.write(f'#SBATCH --mem-per-cpu={int(math.ceil(bench_config.mem_limit/cpus))}\n')
        file.write(f'#SBATCH --output={bench_config.name}.log\n')
        file.write(f'#SBATCH --error={bench_config.name}.log\n')
        file.write(f'#SBATCH --array=0-{counter - 1}\n')
        file.write('#SBATCH --ntasks=1\n\n')
        file.write(f'cd ~/{os.path.relpath(Path(bench_config.name), start=Path.home())}\n')
        file.write(f'FILES=(config*/instance*/run*/start.sh)\n\n')
        file.write('srun ${FILES[$SLURM_ARRAY_TASK_ID]}\n')

    with open(Path(bench_config.name, 'compress_results.slurm'), 'w') as file:
        file.write('#!/bin/bash\n')
        file.write('#\n')
        file.write(f'#SBATCH --job-name={bench_config.name}_compress\n')
        file.write(f'#SBATCH --partition={bench_config.partition}\n')
        file.write(f'#SBATCH --cpus-per-task={bench_config.cpu_per_node / bench_config.mem_lines}\n')
        file.write(f'#SBATCH --output={bench_config.name}.log\n')
        file.write(f'#SBATCH --error={bench_config.name}.log\n')
        file.write('#SBATCH --ntasks=1\n\n')
        file.write(f'cd ~/{os.path.relpath(Path(bench_config.name), start=Path.home())}\n')
        file.write('cd ..\n')
        file.write(f'srun tar czf {bench_config.name}.tar.gz {bench_config.name}\n')

    submit_sh_path = Path(bench_config.name, 'submit_all.sh')
    with open(submit_sh_path, 'w') as file:
        file.write('#!/bin/bash\n')
        file.write('#\n')
        file.write(f'cd ~/{os.path.relpath(Path(bench_config.name), start=Path.home())}\n')
        file.write(f'jid=$(sbatch --parsable batch_job.slurm)\n')
        file.write('cd ..\n')
        file.write(f'sbatch --dependency=afterok:${{jid}} compress_results.slurm')

    os.chmod(submit_sh_path, st.st_mode | stat.S_IEXEC)