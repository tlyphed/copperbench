#!/usr/bin/false
import argparse
import datetime
import json
import math
import os
import random
import re
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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
    cpus_per_node: int = 24
    mem_lines: int = 4
    exclusive: bool = False
    cache_pinning: bool = True
    cpu_freq: int = 2200
    use_perf: bool = True
    runsolver_path: str = "/opt/runsolver"
    billing: Optional[str] = None
    max_parallel_jobs: Optional[int] = None
    overwrite: bool = False
    email: Optional[str] = None
    write_scheuler_logs: Optional[bool] = True


def main() -> None:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                     description=f'copperbench (version {__version__})')
    parser.add_argument('bench_config_file')
    args = parser.parse_args()

    bench_config_dir = os.path.dirname(os.path.realpath(args.bench_config_file))
    with open(os.path.realpath(args.bench_config_file)) as fh:
        print(fh.name)
        bench_config = BenchConfig(**json.loads(fh.read()))

    starthome = os.path.realpath(Path.home())

    working_dir = None
    if bench_config.working_dir is not None:
        if (os.path.isabs(bench_config.working_dir) or
                (isinstance(bench_config.working_dir, str) and bench_config.working_dir.startswith('~'))):
            working_dir = os.path.expanduser(bench_config.working_dir)
        else:
            wd = Path(os.path.dirname(args.bench_config_file), bench_config.working_dir)
            working_dir = os.path.relpath(os.path.realpath(wd), start=starthome)

    if bench_config.initial_seed is not None:
        random.seed(bench_config.initial_seed)

    cpus = int(math.ceil(bench_config.request_cpus / (bench_config.cpus_per_node / bench_config.mem_lines))
               * (bench_config.cpus_per_node / bench_config.mem_lines))
    cache_lines = int(cpus / bench_config.mem_lines)

    instance_conf = bench_config.instances
    instance_dict = {}
    dir_prefix = ''
    if isinstance(instance_conf, str):
        instance_dict[bench_config.name] = instance_conf
    elif isinstance(instance_conf, list):
        for e in instance_conf:
            instance_dict[f'{bench_config.name}_{os.path.splitext(e)[0]}'] = e
        dir_prefix = f'{bench_config.name}/'
    elif isinstance(instance_conf, dict):
        instance_dict = instance_conf
        dir_prefix = f'{bench_config.name}/'

    for benchmark_name, instancelist_filename in instance_dict.items():
        if (benchmark_name.startswith("%") or benchmark_name.startswith("#") or
                instancelist_filename.startswith("%") or instancelist_filename.startswith("#")):
            continue
        if os.path.isabs(instancelist_filename):
            instance_path = instancelist_filename
        else:
            instance_path = f'{bench_config_dir}/{instancelist_filename}'

        instances = {}
        with open(instance_path) as file:
            i = 1
            for line in file:
                instance = line.strip()
                if not instance.startswith('#') and len(instance) > 0:
                    instances[f'instance{i}'] = instance
                    i += 1

        configs = {}
        if os.path.isabs(bench_config.configs):
            config_path = bench_config.configs
        else:
            config_path = f'{bench_config_dir}/{bench_config.configs}'
        with open(config_path) as file:
            i = 1
            for line in file:
                config = line.strip()
                if not config.startswith('#') and len(config) > 0:
                    configs[f'config{i}'] = config
                    i += 1

        if os.path.exists(f'{dir_prefix}{benchmark_name}'):
            if not bench_config.overwrite:
                print(f"Directory {os.path.realpath(f'{dir_prefix}{benchmark_name}')} exists. Exiting...")
                exit(2)
        else:
            os.makedirs(f'{dir_prefix}{benchmark_name}')

        metadata = {'instances': instances, 'configs': configs}

        start_scripts = []
        config_line = 0
        for config_name, config in configs.items():
            config_line += 1
            config = "" if config == "None" else config
            instance_config_line = 0
            for input_name, input_line in instances.items():
                instance_config_line += 1
                if input_line.startswith('#') or input_line.startswith('%'):
                    continue
                for i in range(1, bench_config.runs + 1):
                    log_folder = Path(dir_prefix, benchmark_name, config_name, input_name, f'run{i}')
                    if os.path.exists(log_folder):
                        if not bench_config.overwrite:
                            print(f"Directory {os.path.realpath(log_folder)} exists. Exiting...")
                            exit(2)
                    else:
                        os.makedirs(log_folder)

                    job_file = 'start.sh'
                    job_path = log_folder / job_file

                    shm_uid = uuid.uuid1()
                    shm_dir = Path(f'/dev/shm/{shm_uid}/')

                    cmd = ''
                    if bench_config.executable is not None:
                        cmd += bench_config.executable
                        cmd += ' '
                    cmd += config

                    shm_files = []
                    for m in re.finditer(r"\$file{([^}]*)}", cmd):
                        path = m.group(1)
                        if working_dir is not None and not path.startswith('~') and not os.path.isabs(path):
                            path = Path('~', os.path.relpath(working_dir, start=starthome), path)
                        else:
                            path = Path(path)
                        shm_path = Path(shm_dir, 'input', path.name)
                        shm_files.append((path, shm_path))

                    data_split = re.split('[;, ]', input_line)
                    collected = {}
                    uncompress = []
                    cmd_instances = []
                    for e in data_split:
                        if e in collected.keys() and collected[e] != os.path.realpath(e):
                            print(
                                f'Instance {e} was already added. Instances of the same name from different paths are '
                                f'currently not supported! Exiting...')
                            exit(2)
                        collected[e] = os.path.realpath(e)

                        if os.path.isabs(os.path.expanduser(e)):
                            instance_path = Path(e)
                        else:
                            if working_dir is not None:
                                instance_path = os.path.realpath(os.path.expanduser(Path('~', working_dir, e)))
                                instance_path = Path('~', os.path.relpath(instance_path, start=starthome))
                            else:
                                instance_dir = os.path.realpath(os.path.join(bench_config_dir, e))
                                instance_path = Path('~', os.path.relpath(instance_dir, start=starthome))

                        shm_path = Path(shm_dir, 'input', os.path.basename(e))
                        shm_files.append((Path(instance_path), shm_path))

                        if e.lower().endswith('.lzma') or e.lower().endswith('.zip') or e.lower().endswith(
                                '.gz') or e.lower().endswith('.xz') or e.lower().endswith('.bz2'):
                            shm_path_uncompr = os.path.splitext(e)[0]
                            shm_path_uncompr = Path(shm_dir, 'input', os.path.basename(shm_path_uncompr))
                            uncompress.append((shm_path, shm_path_uncompr))
                            cmd_instances.append(shm_path_uncompr)
                        else:
                            shm_path_uncompr = shm_path
                            cmd_instances.append(shm_path_uncompr)

                    cmd_instances_used = set()
                    for m in re.finditer(r"\$[1-9][0-9]*", cmd):
                        grp = m.group(0)
                        idx = int(grp[1:])
                        try:
                            cmd = cmd.replace(grp, f'{cmd_instances[idx - 1]}')
                        except IndexError as e:
                            print(
                                f"Config: '{os.path.basename(config_path)}:L{config_line}' contained '${idx}', "
                                f"but instance file '{instancelist_filename}:L{instance_config_line}' "
                                f"was missing an file ${idx}.\n........Content was '{input_line}'.")
                            print(f"Exiting!")
                            exit(2)
                        cmd_instances_used.add(idx - 1)

                    for j, v in enumerate(cmd_instances):
                        if j in cmd_instances_used:
                            continue
                        cmd += f' {v}'

                    occ = {}
                    for j, (p, sp) in enumerate(shm_files):
                        if sp.name in occ:
                            new_name = f'{sp.stem}{occ[sp.name]}{sp.suffix}'
                            shm_files[j] = (p, sp.with_name(new_name))
                            occ[sp.name] += 1
                        else:
                            occ[sp.name] = 1

                    for _, f in shm_files:
                        cmd = re.sub(r"\$file{([^}]*)}", str(f), cmd, 1)

                    cmd = re.sub(r"\$timeout", str(bench_config.timeout * bench_config.timeout_factor), cmd)
                    cmd = re.sub(r"\$seed", str(random.randint(0, 2 ** 32)), cmd)

                    rs_file = Path(bench_config.runsolver_path).name
                    runsolver_str = Path(shm_dir, 'input', rs_file)
                    shm_files += [(Path(bench_config.runsolver_path), runsolver_str)]

                    rs_time = bench_config.timeout + bench_config.slurm_time_buffer
                    slurm_time = rs_time + bench_config.runsolver_kill_delay
                    rs_cmd = (f'{runsolver_str} -w runsolver.log -v varfile.log -W {rs_time}'
                              f' -V {bench_config.mem_limit} -d {bench_config.runsolver_kill_delay}')
                    solver_cmd = f'{cmd} 2> stderr.log 1> stdout.log'
                    if bench_config.use_perf:
                        events_str = ','.join(PERF_EVENTS)
                        perf = Path(shm_dir, 'input', 'perf')
                        shm_files += [(Path('/', 'usr', 'bin', 'perf'), perf)]
                        cmd = f'{rs_cmd} {perf} {PERF_PREFIX} {events_str} {solver_cmd}'
                    else:
                        cmd = f'{rs_cmd} {solver_cmd}'

                    log_folder = f'~/{os.path.relpath(log_folder, start=starthome)}'

                    with open(job_path, 'w') as file:
                        file.write('#!/usr/bin/env bash\n\n')
                        file.write('uncompress () {\n')
                        file.write('    filename=$1\n')
                        file.write('    output=$2\n')
                        file.write('    type=$(file -b --mime-type $filename)\n')
                        file.write('    echo "Compressed file recognized as: " $type\n')
                        file.write('\n')
                        file.write('    if [ $type == "application/x-lzma" ] ; then\n')
                        file.write('         prep_cmd="lzcat $filename"\n')
                        file.write('    elif [ $type == "application/x-bzip2" ] ; then\n')
                        file.write('         prep_cmd="bzcat $filename"\n')
                        file.write('    elif [ $type == "application/x-xz" ] ; then\n')
                        file.write('         prep_cmd="xzcat $filename"\n')
                        file.write('    elif [ $type == "application/octet-stream" ] ; then\n')
                        file.write('         prep_cmd="lzcat $filename"\n')
                        file.write('    else\n')
                        file.write('         prep_cmd="zcat -f $filename"\n')
                        file.write('    fi\n')
                        file.write('    echo "Preparing instance in $output"\n')
                        file.write('    echo "$prep_cmd > $output"\n')
                        file.write('    $prep_cmd > $output\n')
                        file.write('}\n')
                        file.write('\n')
                        file.write('_cleanup() {\n')
                        if working_dir is not None and bench_config.symlink_working_dir:
                            file.write('\t# cleanup symlinks\n')
                            file.write('\tfind . -type l -delete\n')
                        file.write(f'\t# copy output into run dir\n')
                        file.write(f'\tcp * {log_folder}\n')
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
                        if working_dir is not None and bench_config.symlink_working_dir:
                            file.write('# create log files (so that symlinks cannot interfere)\n')
                            file.write('touch runsolver.log stdout.log stderr.log\n')
                            file.write('# create symlinks for working directory\n')
                            file.write(f'ln -s ~/{working_dir}/* .\n')
                        file.write('# move input_line into shared mem\n')
                        for orig_path, shm_path in shm_files:
                            file.write(f'cp {orig_path} {shm_path}\n')

                        file.write('# uncompress input files\n')
                        for shm_path, shm_path_uncompr in uncompress:
                            file.write(f'uncompress {shm_path} {shm_path_uncompr}\n')
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

        with open(Path(dir_prefix, benchmark_name, 'metadata.json'), 'w') as file:
            file.write(json.dumps(metadata, indent=4))

        with open(Path(dir_prefix, benchmark_name, 'start_list.txt'), 'w') as file:
            for p in start_scripts:
                file.write(str(p) + '\n')

        bench_path = os.path.relpath(Path(dir_prefix, benchmark_name), start=starthome)

        with open(Path(dir_prefix, benchmark_name, 'batch_job.slurm'), 'w') as file:
            file.write('#!/bin/bash\n')
            file.write('#\n')
            file.write(f'#SBATCH --job-name={benchmark_name}\n')
            file.write(f'#SBATCH --time={datetime.timedelta(seconds=slurm_time)}\n')
            file.write(f'#SBATCH --partition={bench_config.partition}\n')
            file.write(f'#SBATCH --cpus-per-task={cpus}\n')
            file.write(f'#SBATCH --mem-per-cpu={int(math.ceil(bench_config.mem_limit / cpus))}\n')
            file.write(f'#SBATCH --mem-per-cpu={int(math.ceil(bench_config.mem_limit / cpus))}\n')
            if bench_config.email:
                file.write(f'#SBATCH --mail-user={bench_config.email}\n')
                file.write(f"#SBATCH --mail-type=end\n")
            account = bench_config.billing
            if account:
                file.write(f'#SBATCH --account={account}\n')
            if bench_config.cache_pinning:
                file.write(f'#SBATCH --gres=cache:{cache_lines}\n')
            file.write(
                f'#SBATCH --cpu-freq={bench_config.cpu_freq * 1000}-{bench_config.cpu_freq * 1000}:performance\n')
            if bench_config.write_scheuler_logs:
                # environment variable HOME is required as absolute paths on HPC environments differ occasionally
                output_path = f"{os.environ['HOME']}/{os.path.relpath(os.path.abspath(bench_path))}/slurm_logs"
                if not os.path.exists(output_path):
                    os.makedirs(output_path)
                file.write(f'#SBATCH --output={output_path}/slurm-stdout_%A_%a.log\n')
                file.write(f'#SBATCH --error={output_path}/slurm-stderr_%A_%a.log\n\n')
            else:
                file.write(f'#SBATCH --output=/dev/null\n')
                file.write(f'#SBATCH --error=/dev/null\n')
            if bench_config.max_parallel_jobs:
                file.write(f'#SBATCH --array=1-{len(start_scripts)}%{bench_config.max_parallel_jobs}\n')
            else:
                file.write(f'#SBATCH --array=1-{len(start_scripts)}\n')
            if bench_config.exclusive:
                file.write(f"#SBATCH --exclusive=user\n")
            file.write('#SBATCH --ntasks=1\n\n')
            file.write(f'cd ~/{bench_path}\n')
            file.write('start=$( awk "NR==$SLURM_ARRAY_TASK_ID" start_list.txt )\n')
            file.write('srun $start')

        with open(Path(dir_prefix, benchmark_name, 'compress_results.slurm'), 'w') as file:
            file.write('#!/bin/bash\n')
            file.write('#\n')
            file.write(f'#SBATCH --job-name={benchmark_name}_compress\n')
            file.write(f'#SBATCH --partition={bench_config.partition}\n')
            file.write(f'#SBATCH --cpus-per-task=1\n')
            file.write(f'#SBATCH --output=/dev/null\n')
            file.write(f'#SBATCH --error=/dev/null\n')
            file.write('#SBATCH --ntasks=1\n\n')
            file.write(f'cd ~/{bench_path}\n')
            file.write('cd ..\n')
            file.write(f'srun tar czf {dir_prefix}/{benchmark_name}.tar.gz {benchmark_name}\n')

        submit_sh_path = Path(dir_prefix, benchmark_name, 'submit_all.sh')
        with open(submit_sh_path, 'w') as file:
            file.write('#!/bin/bash\n')
            file.write('#\n')
            file.write(
                f'cd ~/{os.path.relpath(Path(dir_prefix, benchmark_name), start=starthome)}\n')
            file.write(f'jid=$(sbatch --parsable batch_job.slurm)\n')
            file.write(f'sbatch --dependency=afterany:${{jid}} compress_results.slurm')

        os.chmod(submit_sh_path, st.st_mode | stat.S_IEXEC)
