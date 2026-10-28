"""Paired comparison of optional public-state completion/chip scheduler."""
import os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchmark_ai_v37 import play
from mission_rules import CITY_ORDER
N=int(sys.argv[1]) if len(sys.argv)>1 else 20
rows={}
for city in CITY_ORDER:
    for mission in range(1,6):
        s={'off':0,'on':0,'off_only':0,'on_only':0}
        for seed in range(N):
            results=[]
            for mode in ('off','on'):
                os.environ['SORT5_SCHEDULER']=mode
                os.environ['SORT5_BELIEF_MODEL']='baseline'
                results.append(play(city,mission,seed)=='success')
            s['off']+=results[0];s['on']+=results[1]
            s['off_only']+=results==[True,False];s['on_only']+=results==[False,True]
        rows[f'{city}#{mission:02d}']=s
    print(city,{x:sum(v[x] for k,v in rows.items() if k.startswith(city+'#')) for x in ('off','on')},flush=True)
print('TOTAL',{x:sum(v[x] for v in rows.values()) for x in ('off','on','off_only','on_only')},flush=True)
Path('BENCHMARK_SCHEDULER_V41.json').write_text(json.dumps({'samples_per_mission':N,'rows':rows},indent=2))
