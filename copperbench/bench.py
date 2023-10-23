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
from typing import Optional, Union

import jinja2

from .__version__ import __version__

PERF_PREFIX = f'stat -B -e'
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
    instances: Union[Path, list, dict]
    configs: Union[Path, list, dict]
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
    cmd_cwd: Optional[bool] = False
    starexec_compatible: Optional[bool] = False


def main() -> None:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                     description=f'copperbench (version {__version__})')
    parser.add_argument('bench_config_file')
    args = parser.parse_args()

    bench_config_dir = os.path.dirname(os.path.realpath(args.bench_config_file))
    with open(os.path.realpath(args.bench_config_file)) as fh:
        bench_config = BenchConfig(**json.loads(fh.read()))

    starthome = os.path.realpath(Path.home())
    templateLoader = jinja2.FileSystemLoader(searchpath=f"{os.path.dirname(__file__)}/templates/")
    templateEnv = jinja2.Environment(loader=templateLoader)

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
    if isinstance(instance_conf, str):
        instance_dict[bench_config.name] = instance_conf
    elif isinstance(instance_conf, list):
        for e in instance_conf:
            instance_dict[f'{bench_config.name}_{os.path.splitext(e)[0]}'] = e
    elif isinstance(instance_conf, dict):
        instance_dict = instance_conf

    rs_time = bench_config.timeout + bench_config.slurm_time_buffer
    slurm_time = rs_time + bench_config.runsolver_kill_delay

    for instanceset_name, instancelist_filename in instance_dict.items():
        if (instanceset_name.startswith("%") or instanceset_name.startswith("#") or
                instancelist_filename.startswith("%") or instancelist_filename.startswith("#")):
            continue
        if os.path.isabs(instancelist_filename):
            instance_path = instancelist_filename
        else:
            instance_path = f'{bench_config_dir}/{instancelist_filename}'

        instancelist_dir = os.path.dirname(instance_path)

        instances = {}
        with open(instance_path) as file:
            i = 1
            for line in file:
                instance = line.strip()
                if not instance.startswith('#') and len(instance) > 0:
                    instances[f'instance{i}'] = instance
                    i += 1

        bench_config_dict = {}
        if isinstance(bench_config.configs, str):
            bench_config_dict[bench_config.name] = bench_config.configs
        elif isinstance(bench_config.configs, list):
            for e in bench_config.configs:
                bench_config_dict[f'{bench_config.name}_{os.path.splitext(e)[0]}'] = e
        elif isinstance(bench_config.configs, dict):
            for k,v in bench_config.configs.items():
                if k == '':
                    print(f'Skipping config {k}: {v} (empty name).')
                    continue
                elif k.startswith('#'):
                    print(f'Skipping config {k}: {v} (starts with #).')
                    continue
                bench_config_dict[k] = v

        for bench_config_name, benchmark_config in bench_config_dict.items():
            if os.path.isabs(benchmark_config):
                config_path = benchmark_config
            else:
                config_path = f'{bench_config_dir}/{benchmark_config}'

            configs = {}
            with open(config_path) as file:
                i = 1
                for line in file:
                    config = line.strip()
                    if not config.startswith('#') and len(config) > 0:
                        configs[f'config{i}'] = config
                        i += 1
                    else:
                        i += 1

            base_path = Path(bench_config.name)

            if not isinstance(bench_config.configs, str):
                base_path = base_path / bench_config_name

            if not isinstance(instance_conf, str):
                base_path = base_path / instanceset_name 

            if os.path.exists(base_path):
                if not bench_config.overwrite:
                    print(f"Directory {os.path.realpath(base_path)} exists. Exiting...")
                    exit(2)
            else:
                os.makedirs(base_path)

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
                        log_folder = Path(base_path, config_name, input_name, f'run{i}')
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
                        for m in re.finditer(r"\$(file|folder){([^}]*)}", cmd):
                            if m.group(1) == 'folder':
                                folder = True
                            else:
                                folder = False
                            path = m.group(2)
                            
                            if os.path.isabs(os.path.expanduser(path)):
                                path = Path(path)
                            else:
                                if working_dir is not None:
                                    path = os.path.realpath(os.path.expanduser(Path('~', working_dir, path)))
                                    path = Path('~', os.path.relpath(path, start=starthome))
                                else:
                                    dir_name = os.path.realpath(os.path.join(bench_config_dir, path))
                                    path = Path('~', os.path.relpath(dir_name, start=starthome))
                            if folder:
                                shm_path = Path(shm_dir, 'input')
                                path = os.path.dirname(path)
                                shm_files.append((f'-r {path}/*', shm_path))
                            else:
                                if str(path).startswith('~'):
                                    path = path
                                    shm_path = Path(shm_dir, 'input', os.path.basename(path))
                                else:
                                    path = Path('~', os.path.relpath(os.path.expanduser(path), start=starthome))
                                    shm_path = Path(shm_dir, 'input', path)
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
                                    instance_dir = os.path.realpath(os.path.join(instancelist_dir, e))
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
                            except IndexError as _:
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
                            repl = ''
                            for m in re.finditer(r"\$folder{([^}]*)}", cmd):
                                repl = f"{str(f)}/{os.path.basename(m.group(1))}"
                                break
                            cmd = re.sub(r"\$folder{([^}]*)}", repl, cmd, 2)

                        cmd = re.sub(r"\$timeout", str(bench_config.timeout * bench_config.timeout_factor), cmd)
                        cmd = re.sub(r"\$seed", str(random.randint(0, 2 ** 32)), cmd)

                        

                        rs_file = Path(bench_config.runsolver_path).name
                        runsolver_str = Path(shm_dir, 'input', rs_file)
                        shm_files += [(Path(bench_config.runsolver_path), runsolver_str)]
                        events_str = ','.join(PERF_EVENTS)
                        log_folder = f'~/{os.path.relpath(log_folder, start=starthome)}'
                        start_template = templateEnv.get_template('start.sh.jinja2')
                        symlink_working_dir = working_dir is not None and bench_config.symlink_working_dir
                        outputText = start_template.render(working_dir=working_dir,
                                                           symlink_working_dir=symlink_working_dir,
                                                           log_folder=log_folder, shm_uid=shm_uid, shm_dir=shm_dir,
                                                           shm_files=shm_files,
                                                           uncompress=uncompress,
                                                           use_perf=bench_config.use_perf, perf_events=events_str,
                                                           solver_cmd=cmd, runsolver_str=runsolver_str,
                                                           perf_prefix=PERF_PREFIX,
                                                           rs_time=rs_time, mem_limit=bench_config.mem_limit,
                                                           runsolver_kill_delay=bench_config.runsolver_kill_delay,
                                                           input_line=input_line, cmd_cwd=bench_config.cmd_cwd,
                                                           cmd_dir=os.path.dirname(cmd.split(' ')[0]),
                                                           starexec=bench_config.starexec_compatible)
                        with open(f"{job_path}", 'w') as fh:
                            fh.write(outputText)

                        st = os.stat(job_path)
                        os.chmod(job_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
                        start_scripts += [job_path]

            with open(base_path / 'metadata.json', 'w') as file:
                file.write(json.dumps(metadata, indent=4))

            with open(base_path / 'start_list.txt', 'w') as file:
                for p in start_scripts:
                    file.write(str(os.path.relpath(p, start=base_path)) + '\n')

            bench_path = os.path.relpath(base_path, start=starthome)
            slurm_template = templateEnv.get_template('batch_job.slurm.jinja2')
            slurm_timeout = datetime.timedelta(seconds=slurm_time)
            mem_per_cpu = int(math.ceil(bench_config.mem_limit / cpus))
            min_freq = bench_config.cpu_freq * 1000
            max_freq = bench_config.cpu_freq * 1000
            output_path = 'slurm_logs'
            os.makedirs(base_path / output_path, exist_ok=True)
            outputText = slurm_template.render(benchmark_name=instanceset_name, slurm_timeout=slurm_timeout,
                                               partition=bench_config.partition, cpus_per_task=cpus,
                                               mem_per_cpu=mem_per_cpu, email=bench_config.email,
                                               account=bench_config.billing,
                                               cache_pinning=bench_config.cache_pinning, cache_lines=cache_lines,
                                               min_freq=min_freq, max_freq=max_freq,
                                               write_scheduler_logs=bench_config.write_scheuler_logs,
                                               output_path=output_path,
                                               max_parallel_jobs=bench_config.max_parallel_jobs,
                                               lstart_scripts=len(start_scripts), exclusive=bench_config.exclusive,
                                               bench_path=bench_path)
            with open(base_path / 'batch_job.slurm', 'w') as fh:
                fh.write(outputText)

            compress_results_slurm = templateEnv.get_template('compress_results.slurm.jinja2')
            outputText = compress_results_slurm.render(benchmark_name=instanceset_name, partition=bench_config.partition,
                                                       bench_path=bench_path,
                                                       write_scheduler_logs=bench_config.write_scheuler_logs,
                                                       output_path=output_path)
            with open(base_path / 'compress_results.slurm', 'w') as fh:
                fh.write(outputText)

            submit_sh_path = Path(base_path, 'submit_all.sh')
            submit_all = templateEnv.get_template('submit_all.sh.jinja2')
            wd = os.path.relpath(base_path, start=starthome)
            outputText = submit_all.render(wd=wd)
            with open(submit_sh_path, 'w') as fh:
                fh.write(outputText)

            st = os.stat(submit_sh_path)
            os.chmod(submit_sh_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
