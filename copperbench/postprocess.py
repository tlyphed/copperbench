from typing import Dict, List, Any, Optional, Callable, Union
from re import Pattern
from pathlib import Path
import json
import os
import re


def process_bench(bench_folder: Union[Path, str], log_read_func: Callable[[Path], Optional[Dict[str, Any]]],
                  metadata_file: Optional[Union[Path, str]] = None, include_metrics: bool = False,
                  err_read_func: Callable[[Path], Optional[Dict[str, Any]]] = lambda x: None) -> List[Dict[str, Any]]:
    bench_folder = Path(bench_folder)
    if metadata_file != None:
        metadata_file = Path(metadata_file)
        with open(metadata_file, 'r') as file:
            metadata = json.loads(file.read())
    else:
        metadata = None

    regex_slurm = re.compile(r"Date:\s+(?P<slurm_date>.+)\nNode:\s+(?P<slurm_node>.+)\n(?s:.)*Cpus_allowed:\s+(?P<slurm_cpumask>.+)\nresctrl cache mask:\s+(?P<slurm_cachemask>.+)\nSlurm Job ID:\s+(?P<slurm_jobid>.+)")
    regex_runsolver = re.compile(r"(?s:.*)Max\. virtual memory \(cumulated for all children\) \(KiB\): (?P<runsolver_max_virt_mem_kb>\d+)\nMax\. memory \(cumulated for all children\) \(KiB\): (?P<runsolver_max_mem_kb>\d+)(?s:.*)user time used= (?P<runsolver_user_time>.+)\nsystem time used= (?P<runsolver_system_time>.+)\nmaximum resident set size= (?P<runsolver_max_rss>\d+)")

    data = []
    for config_dir in os.scandir(bench_folder):
        if config_dir.name.startswith('config') and os.path.isdir(config_dir):
            for instance_dir in os.scandir(config_dir):
                if instance_dir.name.startswith('instance') and os.path.isdir(instance_dir):
                    for run_dir in os.scandir(instance_dir):
                        if run_dir.name.startswith('run') and os.path.isdir(run_dir):
                            result = {}
                            
                            stdout_log = Path(run_dir, 'stdout.log')
                            if stdout_log.exists():
                                result_log = log_read_func(stdout_log)
                                if result_log:
                                    result = result | result_log
                                    
                            stderr_log = Path(run_dir, 'stderr.log')
                            if stderr_log.exists():
                                result_err = err_read_func(stderr_log)
                                if result_err:
                                    result = result | result_err                            
                            
                            if metadata != None:
                                conf_name = metadata['configs'][config_dir.name].strip()
                                inst_name = metadata['instances'][instance_dir.name].strip()
                            else:
                                conf_name = config_dir.name
                                inst_name = instance_dir.name
                            entry = {}
                            entry['config'] = conf_name
                            entry['config_id'] = config_dir.name[6:]
                            entry['instance'] = inst_name
                            entry['instance_id'] = instance_dir.name[8:]
                            entry['run'] = run_dir.name[3:]

                            if include_metrics:
                                node_log = Path(run_dir, 'node_info.log')
                                if node_log.exists():
                                    with open(node_log, 'r') as file:
                                        match = regex_slurm.match(file.read())
                                        if match != None:
                                            entry = entry | match.groupdict()
                                runsolver_log = Path(run_dir, 'runsolver.log')
                                if runsolver_log.exists():
                                    with open(runsolver_log, 'r') as file:
                                        match = regex_runsolver.match(file.read())
                                        if match != None:
                                            entry = entry | match.groupdict()
                                perf_log = Path(run_dir, 'perf.log')
                                if perf_log.exists():
                                    with open(perf_log, 'r') as file:
                                        lines = [ l.strip() for l in file.readlines() ]
                                        lines = [ l for l in lines if len(l) > 0 ]
                                        events = lines[2:-3]
                                        times = lines[-3:]
                                        for event in events:
                                            split = [ e for e in event.split(' ') if len(e) > 0 ]
                                            value = int(split[0].replace(",", "").replace(".", ""))
                                            variable = split[1]
                                            entry[f'perf_{variable}'] = value
                                        for time in times:
                                            t = time.split(' ')
                                            value = float(t[0].replace(",", "."))
                                            variable = '-'.join(t[1:])
                                            entry[f'perf_{variable}'] = value
                                        
                            data += [entry | result]

    return data


def process_bench_regex(bench_folder: Union[Path, str], regex: Pattern,
                        metadata_file: Optional[Union[Path, str]] = None, include_metrics: bool = False) -> List[Dict[str, Any]]:

    def read_log(log_file):
        with open(log_file, 'r') as file:
            match = regex.match(file.read())
            if match != None:
                return match.groupdict()

    return process_bench(bench_folder, read_log, metadata_file, include_metrics=include_metrics)

