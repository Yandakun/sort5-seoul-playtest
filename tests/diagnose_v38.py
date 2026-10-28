import random, collections, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from mission_rules import M,CITY_ORDER

def play(city,mission,seed):
 random.seed(1600000+list(M).index((city,mission))*5000+seed)
 r=server.Room(code='D',humans=0,city=city,mission=mission,debug=False)
 server.start_game(r);server.assign_bot_characters(r)
 for t in range(180):
  if r.phase=='ended':break
  if r.phase=='reveal':
   for p in r.players:
    if not p.reveal_done:r.public.add(random.choice([c for c in p.hand if c!='start']));p.reveal_done=True
   server.start_turn(r)
  elif r.phase=='initial_pass':
   for i,p in enumerate(r.players):
    if str(i) not in r.initial_passes:r.initial_passes[str(i)]=random.choice([c for c in p.hand if c!='start'])
   server.resolve_initial_pass(r)
  elif r.phase=='offer_choice':server.choose_offer(r,r.pending['to'],server.bot_offer_choice(r,r.pending['to']))
  elif r.phase=='guess':server.guess_received_card(r,r.pending['to'],server.bot_number_guess(r,r.pending['to']))
  elif r.phase=='feedback':server.apply_feedback(r,r.pending['to'],server.bot_need(r.players[r.pending['to']],r.pending['card']))
  elif r.phase=='turn':server.advance_bot(r)
  else:raise Exception(r.phase)
 return r
if __name__=='__main__':
 for city in CITY_ORDER:
  res=collections.Counter();m=collections.defaultdict(list)
  for mission in range(1,6):
   for seed in range(40):
    r=play(city,mission,seed)
    k='success' if r.result=='success' else ('chips' if 'chip' in r.reason.lower() else 'order' if 'position' in r.reason.lower() or 'required' in r.reason.lower() or 'must be' in r.reason.lower() else r.reason[:35])
    res[k]+=1
    m[k].append(r.move_count)
  print(city,dict(res),'turns', {k:round(sum(v)/len(v),1) for k,v in m.items()},flush=True)
