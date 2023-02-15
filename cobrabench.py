
import os
import stat
import string
import random
import math
import json
import sys
import pandas as pd
import datetime

SUBMIT_TEMPLATE = '''#!/bin/bash
#
#SBATCH --job-name=${job_name}
#
#SBATCH --ntasks=1
#SBATCH --time=${request_time}
#SBATCH --cpus-per-task=${request_cpu}
#SBATCH --mem-per-cpu=${request_memory}
#SBATCH --output=${batch_output}
#SBATCH --error=${batch_output}
#
#SBATCH --array=0-${n_jobs}

FILES=(config*/instance*/run*/job.sh)

'''

RUN_SOLVER_KILL_DELAY = 10

def process_bench(bench_folder, log_read_func):
    data = []
    for config_dir in os.scandir(bench_folder):
        if config_dir.name.startswith('config') and os.path.isdir(config_dir):
            for instance_dir in os.scandir(config_dir):
                if instance_dir.name.startswith('instance') and os.path.isdir(instance_dir):
                    for run_dir in os.scandir(instance_dir):
                        if run_dir.name.startswith('run') and os.path.isdir(run_dir):
                            result = log_read_func(run_dir.path + '/stdout.log')
                            if result:
                                result['config'] = config_dir.name
                                result['instance'] = instance_dir.name
                                result['run'] = run_dir.name
                                data += [result]

    df = pd.DataFrame.from_dict(data)
    return df

def write_sub(queue_cmds, filename):
    with open(filename, 'w') as file:
        for cmd in queue_cmds:
            file.write(cmd)
            file.write('\n')

def main(cobra_config_file, bench_config_file, configs_file, instances_file):

    with open(cobra_config_file, 'r') as file:
        cobra_config = json.loads(file.read())
    runsolver_path = cobra_config['runsolver_path']
    mem_lines = cobra_config['mem_lines']
    cpu_per_node = cobra_config['cpu_per_node']

    with open(bench_config_file, 'r') as file:
        bench_config = json.loads(file.read())
    bench_name = bench_config['name']
    timeout = bench_config['timeout']
    n_runs = bench_config['runs']
    mem_limit = bench_config['mem_limit']
    request_cpu = bench_config['request_cpus']
    if 'working_dir' in bench_config:
        working_dir = bench_config['working_dir']
    else:
        working_dir = None

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
            if not line.startswith('#'):
                instances[f'instance{i}'] = line.strip()
                i += 1

    configs = {}
    with open(configs_file, 'r') as file:
        i = 1
        for line in file:
            if not line.startswith('#'):
                configs[f'config{i}'] = line.strip()
                i += 1
    
    os.mkdir(bench_name)
    os.chdir(bench_name)

    with open('instance_names.json', 'w') as file:
        file.write(json.dumps(instances))
    with open('config_names.json', 'w') as file:
        file.write(json.dumps(configs))

    counter = 0
    for config_name, config in configs.items():
        for instance_name, data in instances.items():
            for i in range(1, n_runs + 1):

                log_folder = f'{config_name}/{instance_name}/run{i}/'
                os.makedirs(log_folder)

                job_file = 'job.sh'
                job_path = log_folder + '/' + job_file

                log_file = 'stdout.log'
                log_path = log_folder + '/' + log_file

                err_file = 'stderr.log' 
                err_path = log_folder + '/' + err_file

                runsolver_log = 'runsolver.log'
                runsolver_log_path = log_folder + '/' + runsolver_log

                run =  f'{config} {data}'

                if exec_path != None:
                    run =  f'{exec_path} {run}'
                    
                cmd = f'{runsolver_path} -w {runsolver_log_path} -W {timeout} -V {mem_limit} -d {RUN_SOLVER_KILL_DELAY} {run} 2> {err_path} 1> {log_path}'

                with open(job_path, 'w') as file:
                    file.write('#!/bin/sh\n')
                    if working_dir != None:
                        file.write(f'cd {working_dir}\n')
                    cmd = string.Template(cmd).substitute(timeout=timeout * timeout_factor, seed=random.randint(0,2**32), log_folder=log_folder)
                    file.write(cmd)

                st = os.stat(job_path)
                os.chmod(job_path, st.st_mode | stat.S_IEXEC)
                counter += 1
    
    with open(f'{bench_name}.sbatch', 'w') as file:
        file.write(string.Template(SUBMIT_TEMPLATE).substitute(request_time=datetime.timedelta(seconds=timeout), batch_output=f'{bench_name}.log',
                   request_memory=int(math.ceil(mem_limit/cpus)), request_cpu=cpus, job_name=bench_name, n_jobs=counter-1))
        file.write('srun ${FILES[$SLURM_ARRAY_TASK_ID]}')
        
if __name__ == "__main__":
    main(*sys.argv[1:])