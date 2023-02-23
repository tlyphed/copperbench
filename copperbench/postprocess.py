from typing import Dict, List, Any, Optional, Callable, Union
from re import Pattern
from pathlib import Path
import json
import os


def process_bench(bench_folder: Union[Path, str], log_read_func: Callable[[Path], Optional[Dict[str, Any]]], 
                  metadata_file: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:
    bench_folder = Path(bench_folder)
    if metadata_file != None:
        metadata_file = Path(metadata_file)
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


def process_bench_regex(bench_folder: Union[Path, str], regex: Pattern, 
                  metadata_file: Optional[Union[Path, str]] = None) -> List[Dict[str, Any]]:

    def read_log(log_file):
        with open(log_file, 'r') as file:
            match = regex.match(file.read())
            if match != None:
                return match.groupdict()

    return process_bench(bench_folder, read_log, metadata_file)
