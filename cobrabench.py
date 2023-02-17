
import os
import stat
import string
import random
import math
import json
import sys
import pandas as pd
import datetime

DEFAULT_RUN_SOLVER_KILL_DELAY = 10
DEFAULT_TIME_BUFFER = 1
DEFAULT_N_MEM_LINES = 4
DEFAULT_N_CPUS = 24
DEFAULT_PARTITION = 'broadwell'

def process_bench(bench_folder, log_read_func, metadata_file=None):
    if metadata_file != None:
        with open(metadata_file, 'r') as file:
            metadata = json.loads(file.read())

    data = []
    for config_dir in os.scandir(bench_folder):
        if config_dir.name.startswith('config') and os.path.isdir(config_dir):
            for instance_dir in os.scandir(config_dir):
                if instance_dir.name.startswith('instance') and os.path.isdir(instance_dir):
                    for run_dir in os.scandir(instance_dir):
                        if run_dir.name.startswith('run') and os.path.isdir(run_dir):
                            result = log_read_func(run_dir.path + '/stdout.log')
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

    df = pd.DataFrame.from_dict(data)
    return df


def main(cobra_config, bench_config):

    if 'runsolver_path' in cobra_config:
        runsolver_path = cobra_config['runsolver_path']
    else:
        runsolver_path = "runsolver"
    if 'mem_lines' in cobra_config:
        mem_lines = cobra_config['mem_lines']
    else:
        mem_lines = DEFAULT_N_MEM_LINES
    if 'cpu_per_node' in cobra_config:
        cpu_per_node = cobra_config['cpu_per_node']
    else:
        cpu_per_node = DEFAULT_N_CPUS 
    if 'partition' in cobra_config:
        partition = cobra_config['partition']
    else:
        partition = DEFAULT_PARTITION

    bench_name = bench_config['name']
    timeout = bench_config['timeout']
    if 'runs' in bench_config:
        n_runs = bench_config['runs']
    else:
        n_runs = 1

    mem_limit = bench_config['mem_limit']
    request_cpu = bench_config['request_cpus']
    working_dir = os.path.abspath('.')
    if 'runsolver_kill_delay' in bench_config:
        runsolver_kill_delay = bench_config['runsolver_kill_delay']
    else:
        runsolver_kill_delay = DEFAULT_RUN_SOLVER_KILL_DELAY
    if 'slurm_time_buffer' in bench_config:
        time_buffer = bench_config['slurm_time_buffer']
    else:
        time_buffer = DEFAULT_TIME_BUFFER
    
    instances_file = bench_config['instances']
    configs_file = bench_config['configs']

    cpus = int(math.ceil(request_cpu / (cpu_per_node / mem_lines)) * (cpu_per_node / mem_lines))

    if 'executable' in bench_config:
        exec_path = bench_config['executable']
    else:
        exec_path = None

    if 'timeout_factor' in bench_config:
        timeout_factor = bench_config['timeout_factor']
    else:
        timeout_factor = 1

    if 'initial_seed' in bench_config:
        random.seed(bench_config['initial_seed'])

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

    with open(f'{bench_name}/metadata.json', 'w') as file:
        metadata = {}
        metadata['instances'] = instances
        metadata['configs'] = configs
        file.write(json.dumps(metadata, indent=4))

    counter = 0
    for config_name, config in configs.items():
        for instance_name, data in instances.items():
            for i in range(1, n_runs + 1):

                log_folder = f'{bench_name}/{config_name}/{instance_name}/run{i}/'
                os.makedirs(log_folder)

                job_file = 'job.sh'
                job_path = log_folder + job_file

                log_file = 'stdout.log'
                log_path = log_folder + log_file

                err_file = 'stderr.log' 
                err_path = log_folder + err_file

                runsolver_log = 'runsolver.log'
                runsolver_log_path = log_folder + runsolver_log

                run =  f'{config} {data}'

                if exec_path != None:
                    run =  f'{exec_path} {run}'
                    
                cmd = f'{runsolver_path} -w {runsolver_log_path} -W {timeout+time_buffer} -V {mem_limit} -d {runsolver_kill_delay} {run} 2> {err_path} 1> {log_path}'

                with open(job_path, 'w') as file:
                    file.write('#!/bin/sh\n')
                    cmd = string.Template(cmd).substitute(timeout=timeout * timeout_factor, seed=random.randint(0,2**32), log_folder=log_folder)
                    file.write(cmd)

                st = os.stat(job_path)
                os.chmod(job_path, st.st_mode | stat.S_IEXEC)
                counter += 1
    
    with open(f'{bench_name}/sbatch.sh', 'w') as file:
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
        file.write(f'cd {working_dir}\n\n')
        file.write(f'FILES=({bench_name}/config*/instance*/run*/job.sh)\n\n')
        file.write('srun ${FILES[$SLURM_ARRAY_TASK_ID]}\n')
        
if __name__ == "__main__":
    if len(sys.argv) == 3:
        cobra_config_file, bench_config_file = sys.argv[1:]
        with open(cobra_config_file, 'r') as file:
            cobra_config = json.loads(file.read())
    elif len(sys.argv) == 2:
        bench_config_file = sys.argv[1:]
        cobra_config = {}
    else:
        print("usage: cobrabench.py [cobra_config_file] <bench_config_file>")
        sys.exit(1)
    
    with open(bench_config_file, 'r') as file:
        bench_config = json.loads(file.read())

    main(cobra_config, bench_config)