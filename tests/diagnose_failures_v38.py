"""Aggregate failure diagnostics; never exports any private cards/tokens.

Usage: python tests/diagnose_failures_v38.py --samples 120 --output failure_diagnostics_v38.json
This imports the reproducible benchmark play function and records only
room-level completion / failure statistics, not card identities.
"""
import argparse, collections, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from diagnose_v38 import play
from mission_rules import CITY_ORDER


def reason_group(room):
    if room.result=='success':return 'success'
    reason=room.reason.lower()
    if 'chip' in reason:return 'time_chips'
    if 'position' in reason or 'required' in reason or 'must be' in reason:return 'completion_order'
    if 'legal recipient' in reason or 'illegal' in reason:return 'no_legal_transfer'
    if 'incomplete' in reason:return 'incomplete_last_set'
    if 'two-card' in reason:return 'two_card_offer'
    return 'other_failure'


def make_report(samples):
    entries=[]
    aggregate=collections.Counter()
    for city in CITY_ORDER:
        for m in range(1,6):
            cats=collections.Counter();turns=[];completed=[]
            for seed in range(samples):
                room=play(city,m,seed)
                category=reason_group(room)
                cats[category]+=1;aggregate[category]+=1
                turns.append(room.move_count)
                completed.append(len(room.completion_order))
            entries.append({'city':city,'mission':m,'games':samples,'wins':cats['success'],
                            'success_rate':round(cats['success']/samples,4),
                            'failure_reasons':dict(sorted((k,v) for k,v in cats.items() if k!='success')),
                            'average_transfers':round(sum(turns)/samples,2),
                            'average_completed_sets':round(sum(completed)/samples,2)})
    return {'method':'AI-only server simulation; not human play difficulty',
            'samples_per_mission':samples,'total_games':len(entries)*samples,
            'wins':aggregate['success'],'failure_totals':dict(aggregate),'missions':entries}


if __name__=='__main__':
    cli=argparse.ArgumentParser()
    cli.add_argument('--samples',type=int,default=120)
    cli.add_argument('--output',default='failure_diagnostics_v38.json')
    args=cli.parse_args()
    report=make_report(args.samples)
    Path(args.output).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Games:',report['total_games'],'Wins:',report['wins'],'Failures:',report['failure_totals'])
    for row in report['missions']:
        print(f"{row['city']:9} {row['mission']:02}  {row['wins']:3}/{row['games']}  {row['failure_reasons']}")
