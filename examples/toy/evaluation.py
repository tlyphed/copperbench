import sys
import pandas as pd

## uncomment and fill in correct if copperbench is not installed as a module:
# sys.path.append('/Users/tgeibing/Documents/git/cobrabench/')
from copperbench import postprocess

def read_log(log_file):
    '''
    STUB

    parse log and return what should be added to the record as a dict or None for no entry
    '''


data = postprocess.process_bench('example_bench', read_log)
df = pd.DataFrame.from_records(data)
df.to_csv('results.csv')

