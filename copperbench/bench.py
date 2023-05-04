import os
import stat
import string
import random
import math
import json
import datetime
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass
import argparse
import uuid
from .__version__ import __version__

PERF = 'perf stat -o perf.log -B -e cache-references,cache-misses,cycles,instructions,branches,faults,migrations,context-switches '

@dataclass
class Exec:
    path: Path
    configs: Path

@dataclass
class BenchConfig:
    name: str
    instances: Path
    timeout: int
    request_cpus: int
    mem_limit: int
    executables: List[Exec]
    runsolver_path: str
    runs: int = 1
    working_dir: Optional[Path] = None
    runsolver_kill_delay: int = 10
    slurm_time_buffer: int = 1
    timeout_factor: int = 1
    initial_seed: Optional[int] = None
    partition: str = 'broadwell'
    cpu_per_node: int = 24
    mem_lines: int = 4
    exclusive: bool = False
    cache_pinning: bool = True
    cpu_freq: int = 2900
    use_shm: bool = False
    use_perf: bool = False
    nodelist: List[str] = None
    def __post_init__(self):
        self.executables = [ Exec(**e) for e in self.executables ]


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
    cache_lines = int(cpus / bench_config.mem_lines)

    instances = {}
    with open(bench_config.instances, 'r') as file:
        i = 1
        for line in file:
            instance = line.strip()
            if not instance.startswith('#') and len(instance) > 0:
                instances[f'instance{i}'] = instance
                i += 1

    
    
    os.mkdir(bench_config.name)

    metadata = {}
    metadata['instances'] = instances
    metadata['executables'] = []

    counter = 0
    for executable in bench_config.executables:

        configs = {}
        with open(executable.configs, 'r') as file:
            i = 1
            for line in file:
                config = line.strip()
                if not config.startswith('#') and len(config) > 0:
                    configs[f'config{i}'] = config
                    i += 1

        md = {}
        md['path'] = Path(executable.path).name
        md['configs'] = configs
        metadata['executables'] += [
            {
                'name' : Path(executable.path).name,
                'path' : executable.path,
                'configs' : configs
            }
        ]

        for config_name, config in configs.items():
            for instance_name, data in instances.items():
                for i in range(1, bench_config.runs + 1):

                    log_folder = Path(bench_config.name, Path(executable.path).name, config_name, instance_name, f'run{i}')
                    os.makedirs(log_folder)

                    job_file = 'start.sh'
                    job_path = log_folder / job_file

                    shm_uid = uuid.uuid1()
                    shm_dir = Path(f'/dev/shm/{shm_uid}/')

                    if not bench_config.use_shm:
                        executable_str = executable.path
                        data_str = data
                        runsolver_str = bench_config.runsolver_path
                    else:
                        rs_file = Path(bench_config.runsolver_path).name
                        runsolver_str = Path(shm_dir, 'bin', rs_file)
                        exec_file = Path(executable.path).name
                        executable_str = Path(shm_dir, 'bin', exec_file)
                        instance_file = Path(data).name
                        data_str = Path(shm_dir, 'input', instance_file)
                    
                    cmd = f'{runsolver_str} -w runsolver.log -W {bench_config.timeout+bench_config.slurm_time_buffer} -V {bench_config.mem_limit} -d {bench_config.runsolver_kill_delay} {executable_str} {config} {data_str} 2> stderr.log 1> stdout.log'
    
                    with open(job_path, 'w') as file:
                        file.write('#!/bin/sh\n\n')
                        file.write('_cleanup() {\n')
                        if working_dir != None:
                            file.write('\t# cleanup symlinks\n')
                            file.write('\tfind . -type l -delete\n')
                        if bench_config.use_shm:
                            file.write(f'\tcp *.log ~/{os.path.relpath(log_folder, start=Path.home())}\n')
                            file.write('\t# cleanup shm files\n')
                            file.write(f'\trm -rf /dev/shm/{shm_uid}/\n')
                        file.write('}\n\n')
                        file.write('_term() {\n')
                        file.write('\tkill -TERM "$child" 2>/dev/null\n')
                        file.write('\t_cleanup\n')
                        file.write('}\n\n')
                        file.write('trap _term SIGTERM\n\n')
                        file.write('# change into job directory\n')
                        if bench_config.use_shm:
                            file.write(f'mkdir {shm_dir}\n')
                            file.write(f'cd {shm_dir}\n')
                            file.write('mkdir input\n')
                            file.write('mkdir bin\n')
                        else:
                            file.write(f'cd ~/{os.path.relpath(log_folder, start=Path.home())}\n')
                        if working_dir != None:
                            file.write('# create log files (so that symlinks cannot interfere)\n')
                            file.write('touch runsolver.log stdout.log stderr.log\n')
                            file.write('# create symlinks for working directory\n')
                            file.write(f'ln -s ~/{working_dir}/* .\n')
                        if bench_config.use_shm:
                            file.write('# move data into shared mem\n')
                            file.write(f'cp ~/{os.path.relpath(Path(bench_config.runsolver_path), start=Path.home())} {runsolver_str}\n')
                            file.write(f'cp {executable.path} {executable_str}\n')
                            file.write(f'cp {data} {data_str}\n')
                        file.write('# store node info\n')
                        file.write('echo Node: $(hostname) > node_info.log\n')
                        file.write('echo Date: $(date) >> node_info.log\n')
                        file.write('# execute run\n')
                        cmd = string.Template(cmd).substitute(timeout=bench_config.timeout * bench_config.timeout_factor, seed=random.randint(0,2**32))
                        if bench_config.use_perf:
                            cmd = PERF + cmd
                        file.write(cmd + ' &\n')
                        file.write('child=$!\n')
                        file.write('wait "$child"\n')
                        file.write('_cleanup\n')
                        
                    st = os.stat(job_path)
                    os.chmod(job_path, st.st_mode | stat.S_IEXEC)
                    counter += 1
    
    with open(Path(bench_config.name, 'metadata.json'), 'w') as file:
        file.write(json.dumps(metadata, indent=4))

    bench_path = os.path.relpath(Path(bench_config.name), start=Path.home())

    with open(Path(bench_config.name, 'batch_job.slurm'), 'w') as file:
        file.write('#!/bin/bash\n')
        file.write('#\n')
        file.write(f'#SBATCH --job-name={bench_config.name}\n')
        file.write(f'#SBATCH --time={datetime.timedelta(seconds=bench_config.timeout+bench_config.slurm_time_buffer)}\n')
        file.write(f'#SBATCH --partition={bench_config.partition}\n')
        file.write(f'#SBATCH --cpus-per-task={cpus}\n')
        file.write(f'#SBATCH --mem-per-cpu={int(math.ceil(bench_config.mem_limit/cpus))}\n')
        if bench_config.cache_pinning:
            file.write(f'#SBATCH --gres=cache:{cache_lines}\n')
        file.write(f'#SBATCH --cpu-freq={bench_config.cpu_freq*1000}-{bench_config.cpu_freq*1000}:Performance\n')
        file.write(f'#SBATCH --output=/dev/null\n')
        file.write(f'#SBATCH --error=/dev/null\n')
        file.write(f'#SBATCH --array=0-{counter - 1}\n')
        if bench_config.exclusive:
            file.write(f"#SBATCH --exclusive=user\n")
        if bench_config.nodelist != None:
            file.write(f"#SBATCH --nodelist={','.join(bench_config.nodelist)}\n")
        file.write('#SBATCH --ntasks=1\n\n')
        file.write(f'cd ~/{bench_path}\n')
        file.write(f'FILES=(*/config*/instance*/run*/start.sh)\n\n')
        file.write('srun ${FILES[$SLURM_ARRAY_TASK_ID]}\n')

    with open(Path(bench_config.name, 'compress_results.slurm'), 'w') as file:
        file.write('#!/bin/bash\n')
        file.write('#\n')
        file.write(f'#SBATCH --job-name={bench_config.name}_compress\n')
        file.write(f'#SBATCH --partition={bench_config.partition}\n')
        file.write(f'#SBATCH --cpus-per-task={int(bench_config.cpu_per_node / bench_config.mem_lines)}\n')
        file.write(f'#SBATCH --output=/dev/null\n')
        file.write(f'#SBATCH --error=/dev/null\n')
        file.write('#SBATCH --ntasks=1\n\n')
        file.write(f'cd ~/{bench_path}\n')
        file.write('cd ..\n')
        file.write(f'srun tar czf {bench_config.name}.tar.gz {bench_config.name}\n')

    submit_sh_path = Path(bench_config.name, 'submit_all.sh')
    with open(submit_sh_path, 'w') as file:
        file.write('#!/bin/bash\n')
        file.write('#\n')
        file.write(f'cd ~/{os.path.relpath(Path(bench_config.name), start=Path.home())}\n')
        file.write(f'jid=$(sbatch --parsable batch_job.slurm)\n')
        file.write(f'sbatch --dependency=after:${{jid}} compress_results.slurm')

    os.chmod(submit_sh_path, st.st_mode | stat.S_IEXEC)