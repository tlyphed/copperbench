from typing import Dict, List, Any, Optional, Callable, Union
from re import Pattern
from pathlib import Path
import json
import os
import re

def process_bench(bench_folder: Union[Path, str], log_read_func: Callable[[Path], Optional[Dict[str, Any]]], 
                  metadata_file: Optional[Union[Path, str]] = None, include_node_info: bool = False) -> List[Dict[str, Any]]:
    bench_folder = Path(bench_folder)
    if metadata_file != None:
        metadata_file = Path(metadata_file)
        with open(metadata_file, 'r') as file:
            metadata = json.loads(file.read())
    else:
        metadata = None

    regex_slurm = re.compile(r"Node: (?P<slurm_node>.+)")
    regex_perf_cm = re.compile(r"(?P<perf_cache_misses>(\d+\.?)*)\s+cache-misses")
    regex_perf_cw = re.compile(r"(?P<perf_context_switches>(\d+\.?)*)\s+context-switches")
    regex_perf_time = re.compile(r"(?P<perf_user_time>(\d+(,|.)?\d*?)) seconds user")
    regex_perf_total_time = re.compile(r"(?P<perf_total_time>(\d+(,|.)?\d*?)) seconds time elapsed")

    data = []
    for exec_dir in os.scandir(bench_folder):
        if os.path.isdir(exec_dir):
            for config_dir in os.scandir(exec_dir):
                if config_dir.name.startswith('config') and os.path.isdir(config_dir):
                    for instance_dir in os.scandir(config_dir):
                        if instance_dir.name.startswith('instance') and os.path.isdir(instance_dir):
                            for run_dir in os.scandir(instance_dir):
                                if run_dir.name.startswith('run') and os.path.isdir(run_dir):
                                    result = log_read_func(Path(run_dir, 'stdout.log'))
                                    if result:
                                        if metadata != None:
                                            # conf_name = metadata['configs'][config_dir.name]
                                            conf_name = config_dir.name
                                            inst_name = metadata['instances'][instance_dir.name]
                                        else:
                                            conf_name = config_dir.name
                                            inst_name = instance_dir.name
                                        entry = {}
                                        entry['executable'] = exec_dir.name
                                        entry['config'] = conf_name
                                        entry['instance'] = inst_name
                                        entry['run'] = run_dir.name[3:]
                                        if include_node_info:
                                            with open(Path(run_dir, 'node_info.log'), 'r') as file:
                                                match = regex_slurm.match(file.read())
                                                if match != None:
                                                    entry = entry | match.groupdict()
                                            with open(Path(run_dir, 'perf.log'), 'r') as file:
                                                content = file.read()
                                                match = regex_perf_cm.search(content)
                                                if match != None:
                                                    entry['perf_cache_misses'] = int(match.group('perf_cache_misses').replace(".", ""))
                                                match = regex_perf_cw.search(content)
                                                if match != None:
                                                    entry['perf_context_switches'] = int(match.group('perf_context_switches').replace(".", ""))
                                                match = regex_perf_time.search(content)
                                                if match != None:
                                                    entry['perf_user_time'] = float(match.group('perf_user_time').replace(",", "."))
                                                match = regex_perf_total_time.search(content)
                                                if match != None:
                                                    entry['perf_total_time'] = float(match.group('perf_total_time').replace(",", "."))
                                        data += [entry | result]

    return data


def process_bench_regex(bench_folder: Union[Path, str], regex: Pattern, 
                  metadata_file: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:

    def read_log(log_file):
        with open(log_file, 'r') as file:
            match = regex.match(file.read())
            if match != None:
                return match.groupdict()

    return process_bench(bench_folder, read_log, metadata_file)
