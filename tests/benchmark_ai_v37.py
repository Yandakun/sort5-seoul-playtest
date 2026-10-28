"""Reproducible 4-bot benchmark, 120 initial deals per mission.

Run from project root:
    python tests/benchmark_ai_v37.py --samples 120
Only tests the current version; for paired comparisons, use the same
seed function and procedure in the prior version checkout as well.
"""
import argparse
import collections
import random
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from mission_rules import M, CITY_ORDER


def play(city, mission, seed):
    random.seed(1600000 + list(M).index((city, mission)) * 5000 + seed)
    room = server.Room(code='BENCH', humans=0, city=city, mission=mission, debug=False)
    server.start_game(room)
    server.assign_bot_characters(room)
    for _ in range(180):
        if room.phase == 'ended':
            return room.result
        if room.phase == 'reveal':
            for p in room.players:
                if not p.reveal_done:
                    room.public.add(random.choice([c for c in p.hand if c != 'start']))
                    p.reveal_done = True
            server.start_turn(room)
        elif room.phase == 'initial_pass':
            for i, p in enumerate(room.players):
                if str(i) not in room.initial_passes:
                    room.initial_passes[str(i)] = random.choice([c for c in p.hand if c != 'start'])
            server.resolve_initial_pass(room)
        elif room.phase == 'offer_choice':
            server.choose_offer(room, room.pending['to'], server.bot_offer_choice(room, room.pending['to']))
        elif room.phase == 'guess':
            server.guess_received_card(room, room.pending['to'], server.bot_number_guess(room, room.pending['to']))
        elif room.phase == 'feedback':
            server.apply_feedback(room, room.pending['to'],
                                  server.bot_need(room.players[room.pending['to']],room.pending['card']))
        elif room.phase == 'turn':
            server.advance_bot(room)
        else:
            raise AssertionError((city, mission, room.phase))
    raise AssertionError(('stalled', city, mission, seed))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--samples', type=int, default=120)
    args = parser.parse_args()
    total = 0
    for city in CITY_ORDER:
        row = [sum(play(city, mission, seed) == 'success' for seed in range(args.samples))
               for mission in range(1, 6)]
        total += sum(row)
        print(f'{city:9s}', row, 'total', sum(row), flush=True)
    print('TOTAL',total,'/',len(M)*args.samples,
          'rate',f'{100*total/(len(M)*args.samples):.2f}%')
