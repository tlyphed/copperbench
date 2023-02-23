
import re
import os
import pandas as pd

## uncomment and fill in correct if copperbench is not installed as a module:
# sys.path.append('/Users/tgeibing/Documents/git/cobrabench/')
from copperbench import postprocess

regex_cost = re.compile(r"(?s:.*)((Optimization: )|(Cost: ))(?P<cost>\d+)")

alaspo_data = postprocess.process_bench_regex('bench_alaspo', regex_cost, metadata_file='names_alaspo.json')
clingo_data = postprocess.process_bench_regex('bench_clingo', regex_cost, metadata_file='names_clingo.json')
df = pd.DataFrame.from_records(alaspo_data + clingo_data)
os.makedirs('results', exist_ok=True)
df.to_csv('results/results.csv', index=False, sep=';')







