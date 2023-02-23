import re
from typing import Dict, Optional
import pandas as pd
from pathlib import Path

## uncomment and fill in correct if copperbench is not installed as a module:
# import sys
# sys.path.append('/Users/tgeibing/Documents/git/cobrabench/')
from copperbench import postprocess


regex_results = re.compile(r'Total result: \n\t- Hard conflicts: (?P<conflicts>\d+)\n\t- Soft penalties: (?P<penalty>\d+)')
regex_optimal = re.compile(r'found optimal solution')
regex_penalties = re.compile(r"- Same employee: (?P<sameEmployee>\d+)\n\t- Project completion time: (?P<projectCompletionTime>\d+)\n\t- Preferred employees: (?P<preferredEmployees>\d+)\n\t- Job target date: (?P<targetDate>\d+)")


def read_log(log_file: Path) -> Optional[Dict[str, int]]:
    '''
    parse log and return what should be added to the dataframe as a dict or None for no entry
    '''
    with open(log_file, 'r') as file:
        s = file.read()
        match_result = regex_results.search(s)
        if match_result:
            conflicts = int(match_result.group('conflicts'))
            if conflicts == 0:
                penatly = int(match_result.group('penalty'))
                opt = regex_optimal.search(s) != None
                return { 'objective' : penatly, 'optimal' : opt }


data = postprocess.process_bench('bench_vlns', read_log)
df = pd.DataFrame.from_records(data)
df.to_csv('results_vlns.csv')

