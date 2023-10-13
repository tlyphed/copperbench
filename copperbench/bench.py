import os
import stat
import random
import math
import json
import datetime
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass
import argparse
import uuid
import re
from .__version__ import __version__

PERF_PREFIX = f'stat -o perf.log -B -e'
PERF_EVENTS = [
    'cache-references',
    'cache-misses',
    'cycles',
    'instructions',
    'branches',
    'faults',
    'migrations',
    'context-switches'
]

@dataclass
class BenchConfig:
    name: str
    instances: Path
    configs: Path
    timeout: int
    request_cpus: int
    mem_limit: int
    runs: int = 1
    executable: Optional[str] = None
    working_dir: Optional[Path] = None
    symlink_working_dir: bool = True
    runsolver_kill_delay: int = 5
    slurm_time_buffer: int = 10
    timeout_factor: int = 1
    initial_seed: Optional[int] = None
    partition: str = 'broadwell'
    cpu_per_node: int = 24
    mem_lines: int = 4
    exclusive: bool = False
    cache_pinning: bool = True
    cpu_freq: int = 2200
    use_perf: bool = True    
    runsolver_path: str = "/opt/runsolver"
    billing: Optional[str] = None

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

    configs = {}
    with open(bench_config.configs, 'r') as file:
        i = 1
        for line in file:
            config = line.strip()
            if not config.startswith('#') and len(config) > 0:
                configs[f'config{i}'] = config
                i += 1
    
    os.mkdir(bench_config.name)

    metadata = {}
    metadata['instances'] = instances
    metadata['configs'] = configs

    start_scripts = []
    
    for config_name, config in configs.items():
        for instance_name, data in instances.items():
            for i in range(1, bench_config.runs + 1):

                log_folder = Path(bench_config.name, config_name, instance_name, f'run{i}')
                os.makedirs(log_folder)

                job_file = 'start.sh'
                job_path = log_folder / job_file

                shm_uid = uuid.uuid1()
                shm_dir = Path(f'/dev/shm/{shm_uid}/')

                cmd = ''
                if bench_config.executable != None:
                    cmd += bench_config.executable
                    cmd += ' '
                cmd += config + ' ' + data

                shm_files = []
                for m in re.finditer(r"\$file{([^}]*)}", cmd):
                    path = Path(m.group(1))
                    if working_dir != None:
                        path = Path('~', os.path.relpath(working_dir, start=Path.home()), path)
                    shm_path = Path(shm_dir, 'input', path.name)
                    shm_files += [(path,shm_path)]

                occ = {}
                for i, (p, sp) in enumerate(shm_files):
                    if sp.name in occ:
                        new_name = f'{sp.stem}{occ[sp.name]}{sp.suffix}'
                        shm_files[i] = (p, sp.with_name(new_name))
                        occ[sp.name] += 1
                    else:
                        occ[sp.name] = 1

                for _,f in shm_files:
                    cmd = re.sub(r"\$file{([^}]*)}", str(f), cmd, 1)

                cmd = re.sub(r"\$timeout", str(bench_config.timeout * bench_config.timeout_factor), cmd)
                cmd = re.sub(r"\$seed", str(random.randint(0,2**32)), cmd)

                rs_file = Path(bench_config.runsolver_path).name
                runsolver_str = Path(shm_dir, 'input', rs_file)
                shm_files += [(Path(bench_config.runsolver_path), runsolver_str)]

                rs_time = bench_config.timeout+bench_config.slurm_time_buffer  
                slurm_time = rs_time+bench_config.runsolver_kill_delay 
                rs_cmd = f'{runsolver_str} -w runsolver.log -W {rs_time} -V {bench_config.mem_limit} -d {bench_config.runsolver_kill_delay}'
                solver_cmd =  f'{cmd} 2> stderr.log 1> stdout.log'
                if bench_config.use_perf:
                    events_str = ','.join(PERF_EVENTS)
                    perf = Path(shm_dir, 'input', 'perf')
                    shm_files += [(Path('/','usr','bin','perf'), perf)]
                    cmd = f'{rs_cmd} {perf} {PERF_PREFIX} {events_str} {solver_cmd}'
                else:
                    cmd = f'{rs_cmd} {solver_cmd}'
    
                with open(job_path, 'w') as file:
                    file.write('#!/bin/sh\n\n')
                    file.write('_cleanup() {\n')
                    if working_dir != None and bench_config.symlink_working_dir:
                        file.write('\t# cleanup symlinks\n')
                        file.write('\tfind . -type l -delete\n')
                    file.write(f'\t# copy output into run dir\n')
                    file.write(f'\tcp * ~/{os.path.relpath(log_folder, start=Path.home())}\n')
                    file.write('\t# cleanup shm files\n')
                    file.write(f'\trm -rf /dev/shm/{shm_uid}/\n')
                    file.write('}\n\n')
                    file.write('_term() {\n')
                    file.write('\tkill -TERM "$child" 2>/dev/null\n')
                    file.write('\t_cleanup\n')
                    file.write('}\n\n')
                    file.write('trap _term SIGTERM\n\n')
                    file.write('# change into job directory\n')
                    file.write(f'mkdir {shm_dir}\n')
                    file.write(f'cd {shm_dir}\n')
                    file.write('mkdir input\n')
                    file.write('mkdir output\n')
                    file.write('cd output\n')
                    if working_dir != None and bench_config.symlink_working_dir:
                        file.write('# create log files (so that symlinks cannot interfere)\n')
                        file.write('touch runsolver.log stdout.log stderr.log\n')
                        file.write('# create symlinks for working directory\n')
                        file.write(f'ln -s ~/{working_dir}/* .\n')
                    file.write('# move data into shared mem\n')
                    for orig_path,shm_path in shm_files:
                        file.write(f'cp {orig_path} {shm_path}\n')

                    file.write('# store node info\n')
                    file.write('echo Date: $(date) > node_info.log\n')
                    file.write('echo Node: $(hostname) >> node_info.log\n')
                    file.write('cat /proc/self/status | grep Cpus_allowed: >> node_info.log\n')
                    file.write('# execute run\n')

                    file.write(cmd + ' &\n')
                    file.write('child=$!\n')
                    file.write('wait "$child"\n')
                    file.write('_cleanup\n')
                        
                st = os.stat(job_path)
                os.chmod(job_path, st.st_mode | stat.S_IEXEC)
                start_scripts += [Path(*job_path.parts[1:])]
    
    with open(Path(bench_config.name, 'metadata.json'), 'w') as file:
        file.write(json.dumps(metadata, indent=4))

    with open(Path(bench_config.name, 'start_list.txt'), 'w') as file:
        for p in start_scripts:
            file.write(str(p) + '\n')

    bench_path = os.path.relpath(Path(bench_config.name), start=Path.home())

    with open(Path(bench_config.name, 'batch_job.slurm'), 'w') as file:
        file.write('#!/bin/bash\n')
        file.write('#\n')
        file.write(f'#SBATCH --job-name={bench_config.name}\n')
        file.write(f'#SBATCH --time={datetime.timedelta(seconds=slurm_time)}\n')
        file.write(f'#SBATCH --partition={bench_config.partition}\n')
        file.write(f'#SBATCH --cpus-per-task={cpus}\n')
        file.write(f'#SBATCH --mem-per-cpu={int(math.ceil(bench_config.mem_limit/cpus))}\n')
        file.write(f'#SBATCH --mem-per-cpu={int(math.ceil(bench_config.mem_limit/cpus))}\n')
        account = bench_config.billing
        if account:
            file.write(f'#SBATCH --account={account}\n')
        if bench_config.cache_pinning:
            file.write(f'#SBATCH --gres=cache:{cache_lines}\n')
        file.write(f'#SBATCH --cpu-freq={bench_config.cpu_freq*1000}-{bench_config.cpu_freq*1000}:performance\n')
        file.write(f'#SBATCH --output=/dev/null\n')
        file.write(f'#SBATCH --error=/dev/null\n')
        file.write(f'#SBATCH --array=1-{len(start_scripts)}\n')
        if bench_config.exclusive:
            file.write(f"#SBATCH --exclusive=user\n")
        file.write('#SBATCH --ntasks=1\n\n')
        file.write(f'cd ~/{bench_path}\n')
        file.write('start=$( awk "NR==$SLURM_ARRAY_TASK_ID" start_list.txt )\n')
        file.write('srun $start')

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
        file.write(f'sbatch --dependency=afterany:${{jid}} compress_results.slurm')

    os.chmod(submit_sh_path, st.st_mode | stat.S_IEXEC)
