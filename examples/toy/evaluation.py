
from cobrabench import process_bench

def read_log(log_file):
    '''
    STUB

    parse log and return what should be added to the dataframe as a dict or None for no entry
    '''


df = process_bench('example_bench', read_log)
df.to_csv('results.csv')

