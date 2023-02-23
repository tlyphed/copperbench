import sys
import pandas as pd

sys.path.append('/Users/tgeibing/Documents/git/cobrabench')
from cobrabench import process_bench

def read_log(log_file):
    '''
    STUB

    parse log and return what should be added to the record as a dict or None for no entry
    '''


data = process_bench('example_bench', read_log)
df = pd.DataFrame.from_records(data)
df.to_csv('results.csv')

