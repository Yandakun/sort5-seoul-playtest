"""Paired baseline-vs-Bayesian benchmark, same initial seeds per mission."""
import os, sys, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchmark_ai_v37 import play
from mission_rules import M,CITY_ORDER
import argparse
p=argparse.ArgumentParser();p.add_argument('--samples',type=int,default=20);args=p.parse_args()
rows={};changed=[]
for city in CITY_ORDER:
 for mission in range(1,6):
  stats={'baseline':0,'bayesian':0,'baseline_only':0,'bayesian_only':0}
  for seed in range(args.samples):
   results=[]
   for model in ('baseline','bayesian'):
    os.environ['SORT5_BELIEF_MODEL']=model
    results.append(play(city,mission,seed)=='success')
   for model,win in zip(('baseline','bayesian'),results):stats[model]+=win
   if results==[True,False]:stats['baseline_only']+=1
   if results==[False,True]:stats['bayesian_only']+=1
  rows[f'{city}#{mission:02d}']=stats
  print(city,mission,stats,flush=True)
print('TOTAL', {key:sum(row[key] for row in rows.values()) for key in ('baseline','bayesian','baseline_only','bayesian_only')},flush=True)
Path('BENCHMARK_BELIEFS_V40.json').write_text(json.dumps({'samples_per_mission':args.samples,'rows':rows},indent=2))
