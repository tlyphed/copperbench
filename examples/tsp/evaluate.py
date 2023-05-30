
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd

df = pd.read_csv('results/results.csv', sep=';')

df_pivot = df.pivot(index=['instance','run'], columns=['config'], values=['cost'])
df_agg = df_pivot.groupby('instance').agg(['mean','min','max'])
df_agg.to_csv('results/results_agg.csv', index=True, sep=';', decimal=',')

sns.set_style("whitegrid")

df_avg = df.groupby(['instance','config']).mean(numeric_only=True)
best_df = df_avg.groupby('instance').min()
df_avg['rel_to_best'] = (df_avg['cost'] - best_df['cost']) / best_df['cost']
df_avg.reset_index(inplace=True)

fig = sns.boxplot(data=df_avg, x="config", y="rel_to_best")

fig.set_ylabel("relative diff to best")
fig.set_xlabel("")

plt.savefig("results/boxplot.pdf", bbox_inches='tight') 
plt.clf()

fig = sns.catplot(x="instance", y="cost", hue="config", kind="bar", data=df, height=5, aspect=4/2.75)
fig.legend.set_title(None)
fig.set_xticklabels(rotation=90)
fig.set_xlabels("")

plt.savefig('results/barplot.pdf', bbox_inches='tight')
plt.clf()