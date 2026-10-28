"""Observer-limited strategic color assignments and order-safe routing."""
import random
import server


def room(city='seoul', mission=5, turn=0):
    return server.Room(code='STRAT37', city=city, mission=mission, humans=0,
                       debug=False, phase='turn', turn=turn,
                       players=[server.Player(name=f'BOT {i}', token='', bot=True,
                                              char=i, seat=i, chips=6)
                                for i in range(4)])


def test_distinct_team_colors_are_estimated_from_own_and_public_clues():
    r = room(turn=0)
    r.players[0].hand = ['green-1', 'green-2', 'green-3', 'green-4', 'blue-1']
    r.players[1].hand = ['blue-3', 'blue-4', 'brown-1']
    r.public.update(['blue-3', 'blue-4'])
    beliefs = server.bot_color_beliefs(r, 0)
    assert beliefs[0]['green'] > beliefs[0]['blue']
    assert beliefs[1]['blue'] > beliefs[1]['green']
    # Every permutation gives one color to exactly one player.
    for color in server.COLORS:
        assert abs(sum(beliefs[i][color] for i in range(4)) - 1.0) < 1e-8


def test_no_hidden_opponent_hand_or_goal_is_used_in_assignment_or_transfer():
    r = room('paris', 4, turn=0)
    r.players[0].hand = ['blue-1', 'blue-3', 'green-2', 'magenta-4', 'brown-5', 'start']
    for j in range(1, 4):
        r.players[j].hand = ['brown-1', 'blue-2']
        r.players[j].goal = 'brown'
    random.seed(342)
    old = server.bot_choice(r, 0)
    old_beliefs = server.bot_color_beliefs(r, 0)
    for j in range(1, 4):
        r.players[j].hand = ['green-4', 'magenta-5', 'blue-5']
        r.players[j].goal = 'magenta'
    random.seed(342)
    assert server.bot_choice(r, 0) == old
    assert server.bot_color_beliefs(r, 0) == old_beliefs


def test_no_color_leak_from_private_third_party_reactions():
    r = room(turn=0)
    r.players[0].hand = ['green-1', 'green-3', 'blue-4', 'magenta-5', 'brown-2', 'start']
    a = server.bot_color_beliefs(r, 0)
    r.evidence.append({'sender': 1, 'to': 2, 'card': 'green-5',
                       'color': 'green', 'positive': True, 'public': False, 'step': 1})
    assert server.bot_color_beliefs(r, 0) == a


def test_forced_red_is_not_a_rejection_signal():
    r = room('paris', 2)
    r.evidence.append({'sender': 0, 'to': 1, 'card': 'green-1',
                       'color': 'green', 'positive': False, 'public': False, 'step': 1})
    assert server.visible_preference(r, 0, 1, 'green') == 0


def test_berlin_count_feedback_can_be_used_by_original_sender_only():
    r = room('berlin', 5)
    r.turn_events.append({'step': 3, 'from': 0, 'to': 1, 'announced_count': 4})
    r.evidence.append({'sender': 0, 'to': 1, 'color': 'blue', 'positive': False,
                       'public': False, 'step': 3})
    assert server.visible_preference(r, 0, 1, 'blue') > 3
    assert server.visible_preference(r, 2, 1, 'blue') == 0


def test_forced_char_color_pairing_eliminates_impossible_assignments():
    r = room('paris', 4, turn=2)
    # Triangle is required first, magenta second, Square third.
    r.players[2].hand = ['blue-1', 'green-1', 'magenta-1', 'brown-1', 'start']
    beliefs = server.bot_color_beliefs(r, 2)
    assert beliefs[0]['magenta'] == 0
    assert beliefs[2]['magenta'] == 0


def test_never_complete_out_of_order_with_six_information_cards():
    r = room('paris', 1, turn=1)
    r.players[1].hand = [f'blue-{n}' for n in range(1, 6)] + ['green-1']
    r.players[1].goal = 'blue'
    random.seed(41)
    c, target = server.bot_choice(r, 1)
    assert server.col(c) == 'blue', 'Must defer Circle finishing until Triangle completes.'
    assert target != 1
    assert not server.info_set([x for j, x in enumerate(r.players[1].hand)
                                if j != r.players[1].hand.index(c)])


def test_eligible_first_character_finishes_when_complete():
    r = room('paris', 1, turn=0)
    r.players[0].hand = [f'blue-{n}' for n in range(1, 6)] + ['green-1']
    r.players[0].goal = 'blue'
    random.seed(41)
    c, _ = server.bot_choice(r, 0)
    assert c == 'green-1'


def test_completed_sets_occupy_distinct_colors():
    r = room(turn=2)
    r.completion_order = [{'player': 1, 'character': 1, 'color': 'blue', 'position': 1}]
    r.players[1].done = True
    r.players[2].hand = ['green-1', 'green-2', 'magenta-3']
    beliefs = server.bot_color_beliefs(r, 2)
    assert beliefs[1]['blue'] == 1
    assert all(beliefs[i]['blue'] == 0 for i in [0, 2, 3])


def test_two_card_offer_companion_does_not_force_early_completion():
    r = room('paris', 1, turn=1)
    r.players[1].hand = [f'blue-{n}' for n in range(1, 6)] + ['green-1']
    r.players[1].goal = 'blue'
    random.seed(12)
    second = server.bot_second_offer(r, 1, 'blue-1', 0)
    assert second is not None
    assert server.col(second) == 'blue', 'Do not offer green: taking it would wrongly finish Circle.'


def test_no_prior_guess_from_hidden_opponent_color_even_if_many_cards():
    r = room('berlin', 5)
    r.players[0].hand = ['green-1', 'green-2', 'blue-3', 'brown-4', 'magenta-5']
    r.players[1].hand = ['green-3', 'green-4', 'green-5', 'brown-2']
    b = server.bot_color_beliefs(r, 0)
    r.players[1].hand = ['blue-1', 'blue-2', 'blue-4', 'brown-2']
    assert b == server.bot_color_beliefs(r, 0)
