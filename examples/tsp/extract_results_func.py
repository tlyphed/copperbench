
import re
import sys
import os
import pandas as pd

sys.path.append('/Users/tgeibing/Documents/git/cobrabench')
from cobrabench import process_bench

regex_cost = re.compile(r"(?s:.*)((Optimization: )|(Cost: ))(?P<cost>\d+)")

def read_log(log_file):
    with open(log_file, 'r') as file:
        match = regex_cost.match(file.read())
        if match != None:
            return { 'cost' : int(match.group('cost')) }

            
alaspo_data = process_bench('bench_alaspo', read_log, metadata_file='names_alaspo.json')
clingo_data = process_bench('bench_clingo', read_log, metadata_file='names_clingo.json')
df = pd.DataFrame.from_records(alaspo_data + clingo_data)
os.makedirs('results', exist_ok=True)
df.to_csv('results/results.csv', index=False, sep=';')







