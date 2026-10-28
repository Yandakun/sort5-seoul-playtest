"""SORT 5 Seoul: server-authoritative, private-hand cooperative playtest.
Run: uvicorn server:app --host 0.0.0.0 --port 8000
No third-party AI API; bots use only public information and cards they possess.
"""
from __future__ import annotations

from collections import Counter
from itertools import permutations
import math
from dataclasses import dataclass, field
from pathlib import Path
import random
import secrets
import string
import threading
import os
import json
import time
import urllib.request
import urllib.error
from contextlib import contextmanager
from dataclasses import asdict
from typing import Optional
from mission_rules import M, CITY_ORDER, CITY_NAMES, ALL

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
APP = FastAPI(title="SORT 5 Seoul Playtest", version="0.1")
APP.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

CHARS = ["triangle", "circle", "square", "star"]
SYMBOLS = ["▲", "●", "■", "★"]
COLORS = ["brown", "green", "magenta", "blue"]
MISSION_CHIPS = {i:M[('seoul',i)].chips for i in range(1,6)}
MISSION_RULES = {i:M[('seoul',i)].description for i in range(1,6)}
def rule(room): return M[(room.city,room.mission)]

# A non-information Starting Card is treated as 'not needed' on receipt in this
# playtest. The rulebook does not state a special exception; verify with publisher.
START_RECEIPT_POLICY = "consume_negative_chip"

class CreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    humans: int = Field(default=1, ge=1, le=4)
    mission: int = Field(default=1, ge=1, le=5)
    city: str = "seoul"
    debug: bool = False

class JoinBody(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    code: str

class ActionBody(BaseModel):
    code: str
    token: str
    type: str
    character: Optional[int] = None
    card: Optional[str] = None
    target: Optional[int] = None
    positive: Optional[bool] = None
    cards: Optional[list[str]] = None
    choice: Optional[str] = None
    guess: Optional[int] = None

@dataclass
class Player:
    name: str
    token: str
    bot: bool = False
    seat: Optional[int] = None  # immutable clockwise/counterclockwise table position; independent of character
    char: Optional[int] = None
    hand: list[str] = field(default_factory=list)
    chips: int = 0
    done: bool = False
    reveal_done: bool = False
    goal: Optional[str] = None
    last_received: Optional[str] = None
    last_sender: Optional[int] = None
    # Cards this bot directly received, a legal source of inference about senders.
    observed_offers: list[dict] = field(default_factory=list)
    held_card: Optional[str] = None
    start_pass_confirmed: bool = False

@dataclass
class Room:
    code: str
    humans: int
    mission: int
    debug: bool
    city: str = "seoul"
    players: list[Player] = field(default_factory=list)
    owner: str = ""
    phase: str = "lobby"
    turn: Optional[int] = None
    pending: Optional[dict] = None
    public: set[str] = field(default_factory=set)
    history: list[dict] = field(default_factory=list)
    result: Optional[str] = None
    reason: str = ""
    move_count: int = 0
    evidence: list[dict] = field(default_factory=list)
    pending_transfer: Optional[dict] = None
    turn_events: list[dict] = field(default_factory=list)
    shared_chips: Optional[int] = None
    completion_order: list[dict] = field(default_factory=list)
    initial_passes: dict[str,str] = field(default_factory=dict)
    last_guess_wrong: bool = False
    lock: threading.RLock = field(default_factory=threading.RLock)

ROOMS: dict[str, Room] = {}
ROOMS_LOCK = threading.RLock()

# Shared persistence for Vercel. The local development server keeps using memory
# when no Redis configuration is present. Vercel requires the shared store.
REDIS_URL = (os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("KV_REST_API_URL") or "").rstrip("/")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN") or os.getenv("KV_REST_API_TOKEN") or ""
REMOTE_STORE = bool(REDIS_URL and REDIS_TOKEN)
ROOM_TTL_SECONDS = 60 * 60 * 24  # inactive test rooms expire after one day


def redis_command(*args):
    if not REMOTE_STORE:
        raise RuntimeError("Upstash Redis has not been configured")
    req = urllib.request.Request(
        REDIS_URL,
        data=json.dumps(list(args), ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={"Authorization": f"Bearer {REDIS_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=9) as response:
            result = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(503, "Shared room storage temporarily unavailable") from exc
    if "error" in result:
        raise HTTPException(503, "Shared room storage error")
    return result.get("result")


def room_key(code: str) -> str:
    return f"sort5:room:{code.strip().upper()}"


def room_to_json(room: Room) -> str:
    fields = dict(vars(room))
    fields.pop("lock", None)
    fields.pop("_guess_resolved",None)
    fields["public"] = sorted(room.public)
    fields["players"] = [asdict(p) for p in room.players]
    return json.dumps(fields, separators=(",", ":"), ensure_ascii=False)


def room_from_json(value: str) -> Room:
    data = json.loads(value)
    data["players"] = [Player(**p) for p in data["players"]]
    data["public"] = set(data["public"])
    return Room(**data)


def get_room(code: str) -> Optional[Room]:
    code = code.strip().upper()
    if REMOTE_STORE:
        value = redis_command("GET", room_key(code))
        return room_from_json(value) if value is not None else None
    if os.getenv("VERCEL"):
        raise HTTPException(503, "Connect Upstash Redis to this Vercel project and redeploy")
    return ROOMS.get(code)


def save_room(room: Room, *, new: bool = False) -> bool:
    if REMOTE_STORE:
        args = ["SET", room_key(room.code), room_to_json(room), "EX", ROOM_TTL_SECONDS]
        if new:
            args.append("NX")
        return redis_command(*args) == "OK"
    if os.getenv("VERCEL"):
        raise HTTPException(503, "Connect Upstash Redis to this Vercel project and redeploy")
    if new and room.code in ROOMS:
        return False
    ROOMS[room.code] = room
    return True


@contextmanager
def exclusive_room(code: str):
    """Serialize mutations across serverless instances to avoid lost updates."""
    code = code.strip().upper()
    if not REMOTE_STORE:
        room = get_room(code)
        if room is None:
            raise HTTPException(404, "Room not found")
        with room.lock:
            yield
        return

    # The lease bounds stale-lock recovery if an instance is interrupted.
    # Lock TTL is 20 seconds; each game action is expected to finish well before.
    key = f"sort5:lock:{code}"
    owner = secrets.token_urlsafe(18)
    acquired = False
    for attempt in range(20):
        if redis_command("SET", key, owner, "NX", "EX", 20) == "OK":
            acquired = True
            break
        time.sleep(0.10)
    if not acquired:
        raise HTTPException(409, "Room is busy. Try again in a moment.")
    try:
        yield
    finally:
        # Release only the lock this request owns.
        try:
            redis_command(
                "EVAL",
                "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end",
                1, key, owner,
            )
        except HTTPException:
            pass

def new_code() -> str:
    for _ in range(100):
        code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        if get_room(code) is None:
            return code
    raise RuntimeError("Unable to allocate room")

def cid(color, number):
    return f"{color}-{number}"

def col(card):
    return None if card == "start" else card.rsplit("-", 1)[0]

def num(card):
    return None if card == "start" else int(card.rsplit("-", 1)[1])

def info_set(hand, *, final=False):
    cs = [c for c in hand if c != "start"]
    if ("start" in hand and not final) or len(cs) != 5:
        return False
    return len({col(c) for c in cs}) == 1 and {num(c) for c in cs} == {1, 2, 3, 4, 5}

def visible_card(card: str, public: bool, owner: bool) -> dict:
    return {"id": card if (owner or public) else None,
            "visible": public or owner,
            "public": public,
            "start": card == "start" if (owner or public) else False}

def append_history(room: Room, msg: str):
    room.history.append({"step": room.move_count, "text": msg})
    if len(room.history) > 120:
        room.history = room.history[-120:]

def room_and_player(code: str, token: str):
    room = get_room(code.strip().upper())
    if room is None:
        raise HTTPException(404, "Room not found")
    for i, p in enumerate(room.players):
        if p.token == token and not p.bot:
            return room, i
    raise HTTPException(403, "Invalid player token")

def assign_bot_characters(room: Room):
    chosen = {p.char for p in room.players if p.char is not None}
    left = [c for c in range(4) if c not in chosen]
    random.shuffle(left)
    for p in room.players:
        if p.bot:
            p.char = left.pop()
    assert sorted(p.char for p in room.players) == [0, 1, 2, 3]
    cfg=rule(room)
    # For missions with an unseen card, players pick their characters BEFORE
    # any Information Cards are dealt or inspected. This is essential: ▲ must
    # not see the card that is set aside. Other missions keep original setup.
    if cfg.held_player is not None:
        if any(p.hand for p in room.players):
            raise ValueError("Held-card mission must deal only after characters are assigned")
        deal_information_cards(room)
    room.shared_chips=cfg.pool
    for p in room.players:
        p.chips = cfg.chips[p.char] if cfg.chips else 0
    if cfg.held_player is not None:
        held=next(p for p in room.players if p.char==cfg.held_player)
        held.held_card=random.choice(held.hand)
        held.hand.remove(held.held_card)
        append_history(room,"The ▲ character set aside one random Information Card face down without seeing it.")
    starter = next(i for i, p in enumerate(room.players) if p.char == 0)
    room.players[starter].hand.append("start")
    # A bot's color is a working hypothesis, not a fixed assignment.
    for i, p in enumerate(room.players):
        if p.bot:
            p.goal = bot_goal(room, i)
    append_history(room, "Characters assigned. The ▲ character receives the Starting Card.")
    if cfg.setup_reveal == "choose":
        room.phase = "reveal"
        for p in room.players:
            if p.bot:
                # Bots reveal one card they currently hope to collect.
                # This communicates a truthful, public clue without seeing any rival hand.
                options = [c for c in p.hand if c != "start"]
                strong = [c for c in options if col(c) == p.goal]
                room.public.add(random.choice(strong or options))
                p.reveal_done = True
        append_history(room, "Seoul #02: Each player reveals one chosen Information Card.")
        if all(p.reveal_done for p in room.players):
            if cfg.setup_pass_right: begin_initial_pass(room)
            else: start_turn(room)
    elif cfg.setup_pass_right:
        begin_initial_pass(room)
    else:
        start_turn(room)

def begin_initial_pass(room: Room):
    """New York #02: simultaneous hidden selections, then transfer to right."""
    room.phase="initial_pass"
    room.turn=None
    room.initial_passes={}
    for i,p in enumerate(room.players):
        if p.bot:
            options=[c for c in p.hand if c!='start']
            if options:
                room.initial_passes[str(i)]=random.choice(options)
    append_history(room,"Each player secretly selects one card to pass to the right.")
    resolve_initial_pass(room)


def resolve_initial_pass(room: Room):
    if len(room.initial_passes)!=4:return
    outgoing={int(i):c for i,c in room.initial_passes.items()}
    for i,card in outgoing.items():
        if card not in room.players[i].hand: raise ValueError("Selected initial card is no longer in hand")
        room.players[i].hand.remove(card)
    for i,card in outgoing.items():
        room.players[relative_seat(room, i, "right")].hand.append(card)
    append_history(room,"All four selected cards were passed simultaneously to the right.")
    room.initial_passes.clear()
    start_turn(room)


def offer_cards(room: Room, i: int, cards: list[str], target: int):
    cfg=rule(room)
    if room.phase!='turn' or room.turn!=i or room.players[i].char not in cfg.two_cards:
        raise ValueError("This turn does not permit a two-card offer")
    if len(cards)!=2 or cards[0]==cards[1] or not all(can_pass(room,i,c,target) for c in cards):
        raise ValueError("Offer exactly two different cards to an eligible recipient")
    room.phase='offer_choice'
    room.pending={'from':i,'to':target,'cards':cards[:], 'public_cards':[c if c in room.public or room.players[i].char in cfg.faceup else None for c in cards],
                  'recipient_cards': cards[:] if room.city == 'berlin' and room.mission == 3 else None}
    append_history(room,f"{room.players[i].name} offered two cards to {room.players[target].name}.")
    if room.players[target].bot:
        # Only publicly shown cards can affect the receiving bot's choice.
        # Never inspect the undisclosed second card in room.pending['cards'].
        choose_offer(room, target, bot_offer_choice(room, target))


def choose_offer(room: Room, receiver: int, choice: int):
    if room.phase!='offer_choice' or not room.pending or room.pending['to']!=receiver or choice not in (0,1):
        raise ValueError("No pending offer for this recipient")
    pending=room.pending
    source=pending['from'];selected=pending['cards'][choice]
    room.phase='turn';room.turn=source;room.pending=None
    pass_card(room,source,selected,receiver)
    append_history(room,"One card was accepted; the other returned to its original owner.")


def guess_received_card(room: Room, receiver: int, guess: int):
    if room.phase!='guess' or not room.pending or room.pending['to']!=receiver:
        raise ValueError("No pending number guess")
    if guess not in range(1,6):raise ValueError("Guess must be from 1 through 5")
    pending=room.pending
    if pending['card']=='start':raise ValueError("Starting Card has no number")
    wrong_guess=(num(pending['card'])!=guess)
    room.last_guess_wrong=wrong_guess
    append_history(room, f"{room.players[receiver].name} guessed number {guess}: {'incorrect' if wrong_guess else 'correct'}.")
    room.phase='turn';room.turn=pending['from'];room.pending=None
    room._guess_resolved=True
    try:pass_card(room,pending['from'],pending['card'],receiver)
    finally:room._guess_resolved=False
    if room.turn_events:
        room.turn_events[-1]['guessed_number']=guess
        room.turn_events[-1]['guess_wrong']=wrong_guess
    if room.phase!='feedback' and room.phase!='ended':room.last_guess_wrong=False


def start_turn(room: Room):
    # The Starting Card decides first turn, regardless of who created the room.
    holders = [i for i, p in enumerate(room.players) if "start" in p.hand]
    if len(holders) != 1:
        raise ValueError("There must be exactly one Starting Card holder")
    room.phase = "turn"
    room.turn = holders[0]
    room.pending = None
    append_history(room, f"{room.players[room.turn].name} holds the Starting Card and plays first.")
    # Bots wait for a human to click Advance AI Turn.

def deal_information_cards(room: Room):
    """Deal exactly 20 cards in one operation, after any required blind setup."""
    if any(p.hand for p in room.players):
        raise ValueError("Information Cards already dealt")
    deck = [cid(c,n) for c in COLORS for n in range(1,6)]
    random.shuffle(deck)
    for player in room.players:
        player.hand = [deck.pop() for _ in range(5)]
    assert not deck


def start_game(room: Room):
    if room.phase != "lobby":
        raise ValueError("Game already started")
    if len(room.players) != room.humans:
        raise ValueError(f"Waiting for {room.humans - len(room.players)} more human player(s)")
    room.players = room.players[:room.humans] + [
        Player(name=f"BOT {i+1}", token="", bot=True, seat=room.humans+i)
        for i in range(4 - room.humans)
    ]
    room.public.clear();room.history.clear();room.result = None;room.reason = ""
    room.turn = None;room.pending = None;room.move_count = 0
    room.evidence.clear();room.pending_transfer = None;room.turn_events.clear()
    room.completion_order.clear();room.initial_passes.clear();room.shared_chips=None
    for p in room.players:
        p.hand = []
        p.char = None;p.chips = 0;p.done = False;p.reveal_done = False;p.goal = None
        p.last_received = None;p.last_sender = None;p.observed_offers.clear()
        p.held_card=None;p.start_pass_confirmed=False
    # Defer the deal for held-card missions; all players choose a character
    # while their hands are empty. After assignment, deal and reserve unseen.
    if rule(room).held_player is None:
        deal_information_cards(room)
    if rule(room).setup_reveal == "random":
        # Random selection is committed before any player can view initial hands.
        for p in room.players:
            room.public.add(random.choice(p.hand))
    cfg=rule(room)
    if cfg.held_player is not None:
        # Character determined later; reserve an unrevealed random card once assigned.
        pass
    room.phase = "characters"
    setup_info=("Choose characters BEFORE the blind Information Card deal."
                if cfg.held_player is not None else "Information Cards dealt; choose characters.")
    append_history(room, f"{CITY_NAMES[room.city]} #{room.mission:02d}: {setup_info}")
    if rule(room).setup_reveal == "random":
        append_history(room, "One random card from every hand is now face up, before the hands were viewed.")

def relative_seat(room: Room, player_index: int, direction: str, skip_done: bool = False) -> int:
    """Resolve physical seats; optionally skip players who have completed sets.

    The table never rearranges. Only left/right directional *targets* skip
    completed seats. Opposite always means the fixed physical opposite seat.
    """
    shifts={"left":-1,"right":1,"opposite":2}
    if direction not in shifts: raise ValueError("Unknown table direction")
    current_seat=room.players[player_index].seat
    if current_seat is None: current_seat=player_index
    step=shifts[direction]
    candidates=[]
    for k in range(1,4 if skip_done and direction in ("left","right") else 2):
        target_seat=(current_seat+step*k)%4
        idx=next((j for j,p in enumerate(room.players)
                  if (p.seat if p.seat is not None else j)==target_seat),None)
        if idx is None: continue
        candidates.append(idx)
        if not skip_done or not room.players[idx].done: return idx
    # No eligible next player: caller will reject an unavailable target.
    return -1 if skip_done else candidates[0] if candidates else -1


def ai_transfer_routes(room: Room, source: int) -> list[int]:
    """Structural next-hop possibilities, not opponent hand knowledge.

    This uses the same physical-seat restrictions as normal card passes, but
    does not require it to be that player's turn or inspect their hand.
    Opposite restrictions exist only while all four seats are active.
    """
    cfg = rule(room)
    ch = room.players[source].char
    active = sum(not x.done for x in room.players)
    left = relative_seat(room, source, "left", skip_done=True)
    right = relative_seat(room, source, "right", skip_done=True)
    opposite = relative_seat(room, source, "opposite")
    out = []
    for j, p in enumerate(room.players):
        if source == j or p.done:
            continue
        if ch in cfg.left_only and j != left:
            continue
        if active == 4 and ch in cfg.forbidden_opposite and j == opposite:
            continue
        if ch in cfg.forbidden_right and j == right and active > 2:
            continue
        out.append(j)
    return out


def ai_two_turn_value(room: Room, sender: int, recipient: int, color: str,
                      beliefs: dict[int, dict[str, float]]) -> float:
    """Cheap, information-safe two-transfer forecast.

    Forecast (a) whether this player is likely to want the color and (b) if
    they do not, whether their legal NEXT transfer can relay it to someone
    who probably does. This is an expected *route value*, not a determinized
    look into any recipient's hand. Never use card identities of other hands.
    """
    direct = beliefs[recipient].get(color, .25)
    options = [j for j in ai_transfer_routes(room, recipient)
               if j != sender]
    if not options:
        return 0.0
    best = max(beliefs[j].get(color, .25) for j in options)
    # A relay consumes another reception and is worthwhile mainly for cards
    # that the immediate recipient is unlikely to retain.
    relay_gain = max(0., best - direct)
    future_cost = 0.48 if room.shared_chips is None else 0.58
    return max(0., relay_gain - future_cost * .20) * 5.0


def can_pass(room: Room, i: int, c: str, target: int):
    basic=(room.phase=="turn" and room.turn==i and c in room.players[i].hand
           and target!=i and 0<=target<4 and not room.players[target].done)
    if not basic: return False
    cfg=rule(room); ch=room.players[i].char
    active=sum(not p.done for p in room.players)
    left=relative_seat(room, i, "left", skip_done=True)
    right=relative_seat(room, i, "right", skip_done=True)
    opposite=relative_seat(room, i, "opposite")
    if ch in cfg.left_only and target!=left: return False
    if active==4 and ch in cfg.forbidden_opposite and target==opposite: return False
    if ch in cfg.forbidden_right and target==right and active>2: return False
    return True

def complete_player(room: Room, i: int, final=False):
    p = room.players[i]
    if p.done:
        return
    cfg=rule(room)
    next_pos=len(room.completion_order)+1
    fixed=dict(cfg.completion_positions)
    color_requirements=dict(cfg.color_positions)
    colors={col(c) for c in p.hand if c!='start'}
    if p.char in fixed and fixed[p.char]!=next_pos:
        finish(room,False,f"{p.name} completed in position {next_pos}, required {fixed[p.char]}.")
        return
    for color,position in color_requirements.items():
        if color in colors and next_pos!=position:
            finish(room,False,f"{color} set completed in position {next_pos}, required {position}.")
            return
        if next_pos==position and color not in colors:
            finish(room,False,f"Position {position} must be the {color} set.")
            return
    room.completion_order.append({'player':i,'character':p.char,'color':next(iter(colors),None),'position':next_pos})
    p.done = True
    room.public.update(p.hand)
    append_history(room, f"{p.name} completed a set and revealed their hand.")
    p.chips = 0  # remaining Time Chips cannot be used
    for q in room.players:
        if q.held_card is not None:
            q.hand.append(q.held_card);q.held_card=None
            append_history(room,f"{q.name} recovered a set-aside card.")

def finish(room: Room, ok: bool, msg: str):
    room.phase = "ended"
    room.result = "success" if ok else "failure"
    room.reason = msg
    room.turn = None;room.pending = None
    if not ok:
        # The original tabletop rules do not require revealing failed hands.
        pass
    append_history(room, msg)

def after_received(room: Room, target: int, card: str):
    active = [i for i, p in enumerate(room.players) if not p.done]
    if len(active) == 1 and active[0] == target:
        if info_set(room.players[target].hand, final=True):
            complete_player(room, target, final=True)
            if room.phase!='ended': finish(room,True,"Mission cleared! All required Information Sets are complete.")
        else:
            room.public.update(room.players[target].hand)
            finish(room, False, "The final player revealed an incomplete Information Set.")
        return
    p = room.players[target]
    if (room.shared_chips if room.shared_chips is not None else p.chips) <= 0:
        finish(room, False, f"{p.name} has no Time Chips available to receive another card.")
        return
    cfg = rule(room)
    forced_negative = (cfg.feedback in ('negative_only', 'count_color') or
                       (cfg.feedback == 'negative_only_triangle' and p.char == 0))
    if card == "start":
        # Starting Card is a normal feedback decision for a human recipient.
        # Bots make the choice automatically; forced-red missions still enforce red.
        if p.bot:
            apply_feedback(room, target, False, is_start=True)
        else:
            room.phase = "feedback"
            room.pending = {"to": target, "card": card}
    elif cfg.feedback == 'count_color':
        # Berlin #05: a human must publicly announce the count; AI announces automatically.
        # Only the recipient knows the received color unless the card was face up.
        if p.bot:
            p.goal = bot_goal(room, target)
            apply_feedback(room, target, False)
        else:
            room.phase = 'announce'
            room.pending = {'to': target, 'card': card}
    elif forced_negative:
        if p.bot:
            p.goal = bot_goal(room, target)
        apply_feedback(room, target, False)
    elif p.bot:
        p.goal = bot_goal(room, target)
        apply_feedback(room, target, bot_need(p, card))
    else:
        room.phase = "feedback"
        room.pending = {"to": target, "card": card}

def pass_card(room: Room, i: int, card: str, target: int):
    if not can_pass(room, i, card, target):
        raise ValueError("Illegal card transfer or wrong player's turn")
    cfg=rule(room)
    if cfg.guess_number and card!='start' and not getattr(room,'_guess_resolved',False):
        room.phase='guess'
        room.pending={'from':i,'to':target,'card':card}
        append_history(room,f"{room.players[target].name} must guess the received card's number before seeing it.")
        if room.players[target].bot:
            guess_received_card(room, target, bot_number_guess(room, target))
        return
    source = room.players[i]
    receiver = room.players[target]
    source.hand.remove(card)
    receiver.hand.append(card)
    receiver.last_received = card
    receiver.last_sender = i
    room.move_count += 1
    if receiver.bot and card != "start":
        # The receiving bot knows the exact card it saw and who gave it.
        receiver.observed_offers.append({"from": i, "color": col(card), "step": room.move_count})
    cfg=rule(room)
    face_up = source.char in cfg.faceup
    if face_up:
        room.public.add(card)
    label = "face up" if card in room.public else "face down"
    append_history(room, f"{source.name} passed a card to {receiver.name} ({label}).")
    room.turn_events.append({"step": room.move_count, "from": i, "to": target,
                             "card": card if card in room.public else None,
                             "face_up": card in room.public, "reaction": None, "number":num(card)})
    if info_set(source.hand):
        if not cfg.require_start_pass or card=='start':
            complete_player(room,i)
    # A completed set may end the mission on this transfer. Resolve that
    # outcome before charging the receiving player any feedback chip.
    # complete_player() can also end the mission on a completion-order violation.
    if room.phase == "ended":
        return
    if len(room.completion_order) >= cfg.target_sets:
        finish(room, True, f"Mission cleared! {cfg.target_sets} sets completed.")
        return
    room.turn = target
    room.pending_transfer = {"sender": i, "to": target, "card": card, "public": card in room.public}
    after_received(room, target, card)
    # Do not automatically take AI turns; one click = one transfer.

def apply_feedback(room: Room, i: int, positive: bool, is_start=False):
    p = room.players[i]
    if (room.shared_chips if room.shared_chips is not None else p.chips) <= 0:
        finish(room, False, f"{p.name} has no remaining Time Chips.")
        return
    cfg=rule(room)
    actual=(False if cfg.feedback in ('negative_only','count_color') or (cfg.feedback=='negative_only_triangle' and p.char==0) else positive)
    if room.turn_events and room.turn_events[-1]["to"] == i and room.turn_events[-1]["reaction"] is None:
        room.turn_events[-1]["reaction"] = "positive" if actual else "negative"
        if cfg.feedback=='count_color' and room.pending_transfer is not None:
            received_color=col(room.pending_transfer['card'])
            room.turn_events[-1]['announced_count']=sum(col(c)==received_color for c in p.hand)
            room.turn_events[-1]['announced_at']=time.time()
    if room.pending_transfer is not None:
        transfer = room.pending_transfer
        if transfer["to"] == i and transfer["card"] != "start":
            room.evidence.append({
                "sender": transfer["sender"], "to": i,
                "color": col(transfer["card"]), "positive": actual,
                "public": transfer["public"],
                "card": transfer["card"], "step": room.move_count,
            })
        room.pending_transfer = None
    cfg=rule(room)
    incoming=room.turn_events[-1].get("number") if room.turn_events else None
    extra=int(cfg.extra_even_chip and incoming is not None and incoming%2==0)
    if cfg.guess_number:
        extra+=int(room.last_guess_wrong)
        room.last_guess_wrong=False
    cost=1+extra
    if room.shared_chips is not None:
        room.shared_chips=max(0,room.shared_chips-cost)
        left=room.shared_chips
    else:
        p.chips=max(0,p.chips-cost)
        left=p.chips
    p_text = "red / not needed" if (not actual) else "green / needed"
    if cfg.feedback == 'count_color' and room.turn_events:
        count = room.turn_events[-1].get('announced_count')
        if count is not None:
            append_history(room, f"{p.name} announced {count} cards of the received color; red chip. ({left} Time Chips left)")
        else:
            append_history(room, f"{p.name}: {p_text} feedback. ({left} Time Chips left; spent {cost})")
    else:
        append_history(room, f"{p.name}: {p_text} feedback. ({left} Time Chips left; spent {cost})")
    room.pending = None
    room.phase = "turn"
    # Spending the final chip is legal. A player fails only when they receive
    # another card and cannot pay the required feedback chip (after_received).
    # This applies to individual and shared chip pools alike.

def bot_number_guess(room: Room, receiver: int) -> int:
    """Guess based on the four copies of each number in the full deck.

    The receiver knows its own cards and every *public* card, but not any
    opponent's private hand or the pending card. Public cards already in its
    own hand are counted only once. This is intentionally a modest inference,
    not privileged server knowledge.
    """
    known = set(c for c in room.players[receiver].hand if c != 'start')
    known.update(c for c in room.public if c != 'start')
    distribution = [max(0, 4 - sum(num(c) == n for c in known)) for n in range(1, 6)]
    best = max(distribution)
    return random.choice([n for n, w in enumerate(distribution, 1) if w == best])


def bot_offer_choice(room: Room, receiver: int) -> int:
    """Pick one offered card using only what the recipient actually sees.

    The two *internal* card IDs remain hidden from this function. Hidden offers
    have indistinguishable backs, so pick at random. Visible offerings can be
    compared against the bot's current hypothesis and owned numbers.
    """
    offered = room.pending.get('recipient_cards') or room.pending['public_cards']
    bot = room.players[receiver]
    if not any(offered):
        return random.randrange(2)
    goal = bot_goal(room, receiver)
    held = set(bot.hand)
    scores = []
    for c in offered:
        if c is None:
            scores.append(0.0)
        elif c == 'start':
            scores.append(-2.0)
        else:
            scores.append((6.0 if col(c) == goal else 0.0)
                          + (1.0 if c not in held else 0.0))
    highest = max(scores)
    return random.choice([i for i, score in enumerate(scores) if score == highest])


def bot_second_offer(room: Room, sender: int, primary: str, target: int) -> Optional[str]:
    """Choose the least costly legal companion to a two-card offer.

    For an unrevealed offer, the receiver may choose either card. Preserve our
    working collection color where possible and prefer a card the receiver has
    previously signaled it needs. Never use the receiver's private hand.
    """
    player = room.players[sender]
    choices = [c for c in player.hand if c != primary and can_pass(room, sender, c, target)]
    if not choices:
        return None
    def score(card):
        if card == 'start':
            return -12.0
        color = col(card)
        score = 1.0 * visible_preference(room, sender, target, color)
        if color == player.goal:
            score -= 10.0
        if card == player.last_received and player.last_sender == target:
            score -= 3.0
        remaining = player.hand.copy()
        remaining.remove(card)
        if info_set(remaining) and not ai_can_finish_now(room, sender, col(remaining[0])):
            score -= 1000.0  # The recipient could choose this offered card.
        return score
    best = max(score(c) for c in choices)
    return random.choice([c for c in choices if score(c) == best])


def bot_need(p: Player, card: str):
    """Signal whether the last card supports the bot's *current* plan."""
    return card != "start" and p.goal == col(card)


def visible_preference(room: Room, bot_i: int, dest_i: int, color: str) -> float:
    """Estimate another player's color needs from information this bot can know.

    Private reactions alone do not expose a card's color. Color-specific evidence
    is usable only when this bot passed that card or the card was public.
    """
    weight = 0.0
    feedback_mode = rule(room).feedback
    for event in room.evidence:
        if event["to"] != dest_i or event["color"] != color:
            continue
        if event["sender"] != bot_i and not event["public"]:
            continue
        receiver_char=room.players[dest_i].char
        is_forced = (feedback_mode in ('count_color','negative_only') or
                     (feedback_mode == 'negative_only_triangle' and receiver_char == 0))
        if is_forced:
            # Berlin #05 announces a quantity instead of positive/negative.
            # The observer knows the COLOR only for its own sent card or a
            # publicly shown card (enforced above). Quantity itself is public.
            if feedback_mode == 'count_color':
                announced = next((e.get('announced_count') for e in reversed(room.turn_events)
                                  if e.get('step') == event.get('step')
                                  and e.get('to') == dest_i), None)
                if announced is not None:
                    age = max(0, room.move_count - event.get('step', 0))
                    weight += (1.65 * (announced - 1) - 0.25) * (0.96 ** age)
            continue  # Forced red does not mean the card was unwanted.
        age = max(0, room.move_count - event.get("step", 0))
        weight += (3.0 if event["positive"] else -4.2) * (0.94 ** age)
    # Publicly revealed cards currently in that player's hand are extra clues,
    # but they do not prove which color the other player plans to collect.
    dest = room.players[dest_i]
    visible = sum(col(c) == color for c in dest.hand if c in room.public)
    weight += min(visible, 4) * 0.95
    # A player who willingly passed this color to us may be collecting another
    # color. This is weak evidence (forced transfers happen), and it decays.
    bot = room.players[bot_i]
    for offer in bot.observed_offers:
        if offer["from"] == dest_i and offer["color"] == color:
            age = max(0, room.move_count - offer["step"])
            weight -= 0.9 * (0.90 ** age)
    return weight


def feedback_priority_v47(room: Room, observer: int, target: int, color: str) -> float:
    """Observable recent feedback, compared against other recipients' demand.

    A bot may connect a reaction to a color only for a card it sent or a
    publicly visible card. Forced-negative modes are not rejections. This
    score NEVER reads other players' private hands or internal goals.
    """
    cfg = rule(room)
    if cfg.feedback in ('count_color', 'negative_only'):
        return 0.0
    if cfg.feedback == 'negative_only_triangle' and room.players[target].char == 0:
        return 0.0

    def strongest_recent(recipient):
        latest = None
        for e in room.evidence:
            if e['to'] != recipient or e['color'] != color:
                continue
            if e['sender'] != observer and not e['public']:
                continue
            # Ignore feedback that was compulsory for this recipient.
            if cfg.feedback == 'negative_only_triangle' and room.players[recipient].char == 0:
                continue
            if latest is None or e['step'] > latest['step']:
                latest = e
        if latest is None:
            return 0.0
        age = max(0, room.move_count - latest['step'])
        return (1.0 if latest['positive'] else -1.0) * (0.90 ** age)

    direct = strongest_recent(target)
    if direct == 0:
        return 0.0
    # Recent red: strongly discourage repeating the color to this player.
    if direct < 0:
        return 7.0 * direct
    # Recent green: prioritize this known need, unless an *observably*
    # competing player has a stronger recent claim. Not a permanent lock.
    competitors = [strongest_recent(j) for j, p in enumerate(room.players)
                   if j != target and j != observer and not p.done]
    competition = max([0.0] + competitors)
    return 5.0 * direct - 2.0 * max(0.0, competition - direct)


def bayesian_assignment_beliefs(room: Room, observer: int) -> dict[int, dict[str, float]]:
    """An optional, *observer-limited* posterior over the 24 unique color roles.

    This is a dynamic-goal approximation, not a claim that a player's target
    remains constant. Recent directly observed reactions carry more weight,
    while old feedback decays toward an uninformative likelihood.
    """
    me = room.players[observer]
    cfg = rule(room)
    finished = {e['player']: e['color'] for e in room.completion_order}
    char_pos = dict(cfg.completion_positions)
    color_pos = dict(cfg.color_positions)
    fixed = {(ch, c) for ch, rank in char_pos.items()
             for c, cr in color_pos.items() if rank == cr}
    # Baseline counts are visible only to the owning bot, or if public.
    own_counts = Counter(col(c) for c in me.hand if c != 'start')
    public_counts = {i: Counter(col(c) for c in p.hand if c in room.public)
                     for i, p in enumerate(room.players)}
    # Only evidence directly witnessed by the observer, or globally public,
    # is eligible. The sender's knowledge of card identity is not public.
    observations=[]
    for e in room.evidence:
        if e.get('sender') != observer and not e.get('public'):
            continue
        if e.get('card') == 'start':
            continue
        target=e.get('to'); color=e.get('color')
        if target is None or color not in COLORS:
            continue
        receiver_char=room.players[target].char
        forced=(cfg.feedback in ('count_color','negative_only') or
                (cfg.feedback == 'negative_only_triangle' and receiver_char == 0))
        if forced:
            continue  # Forced red carries no preference information.
        age=max(0,room.move_count-e.get('step',0))
        strength=0.88**age
        observations.append((target,color,bool(e.get('positive')),strength))
    candidates=[]
    for assignment in permutations(COLORS):
        if any(assignment[i] != color for i,color in finished.items() if color is not None):
            continue
        if any(p.char in char_pos and assignment[i] in color_pos and
               char_pos[p.char] != color_pos[assignment[i]]
               for i,p in enumerate(room.players)):
            continue
        if any(p.char==ch and assignment[i]!=color
               for i,p in enumerate(room.players) for ch,color in fixed):
            continue
        if any(assignment[i] in [v for j,v in finished.items() if j!=i]
               for i in range(4)):
            continue
        logp=0.0
        for i,c in enumerate(assignment):
            if i==observer:
                n=own_counts[c]
                logp += 0.75*n + 0.12*n*n
                if c==me.goal: logp+=0.20
            else:
                logp+=0.65*public_counts[i][c]
        for target,color,positive,strength in observations:
            is_target=assignment[target]==color
            # A signal is imperfect because targets can change during play.
            p_green=0.82 if is_target else 0.18
            prob=p_green if positive else 1-p_green
            logp += strength * math.log(prob)
        candidates.append((logp,assignment))
    if not candidates:
        return {i:{c:0.25 for c in COLORS} for i in range(4)}
    maximum=max(logp for logp,_ in candidates)
    weights=[math.exp(max(-60.0,logp-maximum)) for logp,_ in candidates]
    total=sum(weights)
    return {i:{c:sum(w for (logp,assignment),w in zip(candidates,weights)
                       if assignment[i]==c)/total for c in COLORS} for i in range(4)}


def bot_color_beliefs(room: Room, observer: int) -> dict[int, dict[str, float]]:
    """Infer *different* color assignments using the observer's legal information.

    A finished set owns its revealed color. The observing bot can inspect its
    own hand, public cards wherever they currently are, its own sent-card
    reactions, and reactions to cards shown publicly. It cannot use other
    players' hidden cards or their private bot goals.

    These are probabilistic estimates, NOT secret team-wide coordination.
    """
    if os.getenv('SORT5_BELIEF_MODEL', 'baseline').lower() == 'bayesian':
        return bayesian_assignment_beliefs(room, observer)
    me = room.players[observer]
    finished = {event['player']: event['color'] for event in room.completion_order}
    affinity = {}
    for i, p in enumerate(room.players):
        affinity[i] = {}
        for color in COLORS:
            if i == observer:
                n = sum(col(c) == color for c in me.hand if c != 'start')
                score = 2.55*n + 0.43*n*n
                if me.goal == color:
                    score += 0.5
            else:
                n = sum(col(c) == color for c in p.hand if c in room.public)
                score = 2.0*n + 0.45*n*n
                # Each bot only knows colors of offers made by that bot or
                # offers shown to everyone. The absence of feedback in Paris
                # and Berlin's count variant is not a red-card rejection.
                score += 1.25*visible_preference(room, observer, i, color)
            affinity[i][color] = score
    cfg=rule(room)
    char_pos=dict(cfg.completion_positions)
    color_pos=dict(cfg.color_positions)
    # When both a specific character and a specific color must finish at
    # the same rank, their assignment is fixed (even before any feedback).
    matching = {(ch,color) for ch,rank in char_pos.items()
                for color, cr in color_pos.items() if rank==cr}
    for i,p in enumerate(room.players):
        for ch,color in matching:
            if p.char == ch:
                affinity[i][color] += 18.0
    assignments=[]
    for colors in permutations(COLORS):
        if any(colors[i] != color for i,color in finished.items() if color is not None):
            continue
        # Public constraints on finishing ranks eliminate impossible
        # character/color pairings before planning the team assignment.
        if any(p.char in char_pos and colors[i] in color_pos and
               char_pos[p.char] != color_pos[colors[i]]
               for i,p in enumerate(room.players)):
            continue
        if any(p.char == ch and colors[i] != color
               for i,p in enumerate(room.players) for ch,color in matching):
            continue
        # Never let an unfinished player claim a set that has already been
        # completed by someone else.
        if any(colors[i] in [x for j,x in finished.items() if j != i] for i in range(4)):
            continue
        score = sum(affinity[i][colors[i]] for i in range(4))
        assignments.append((score,colors))
    if not assignments:
        return {i:{c:0.25 for c in COLORS} for i in range(4)}
    # Marginalize over consistent permutations. Softmax avoids a brittle
    # forced choice when there is very little public evidence.
    top=max(x[0] for x in assignments)
    weights=[math.exp(max(-60.0,(x[0]-top)/1.5)) for x in assignments]
    z=sum(weights)
    base = {i:{c:sum(w for (score,cols),w in zip(assignments,weights)
                       if cols[i]==c)/z for c in COLORS} for i in range(4)}
    if os.getenv('SORT5_BELIEF_MODEL', 'baseline').lower() == 'blend':
        alternative = bayesian_assignment_beliefs(room, observer)
        # Low-weight research variant: keep existing goal stability intact.
        return {i:{c:0.8*base[i][c] + 0.2*alternative[i][c] for c in COLORS}
                for i in range(4)}
    return base


def ai_estimated_target_holdings(room: Room, observer: int, recipient: int,
                                 color: str) -> float:
    """Estimated number of likely retained cards using only observed transfers.

    Old positive signals decay because cards could be silently passed on. We
    count currently public cards separately; do not double-count the same ID.
    """
    other = room.players[recipient]
    public_held = {c for c in other.hand if c in room.public and col(c)==color}
    count = float(len(public_held))
    own_cards = set(room.players[observer].hand)
    seen = set(public_held)
    for ev in reversed(room.evidence):
        if ev['to'] != recipient or ev.get('color') != color or not ev.get('positive'):
            continue
        if ev['sender'] != observer and not ev.get('public'):
            continue
        card = ev.get('card')
        if not card or card in seen or card in own_cards:
            continue
        seen.add(card)
        age=max(0,room.move_count-ev.get('step',0))
        count += 0.72 * (0.85 ** age)
    return count


def bot_goal(room: Room, bot_i: int) -> str:
    """Reconsider collection color as the game reveals new information.

    Strong personal holdings matter, but also avoid competing with the colors
    other teammates appear to collect. No hidden teammate hands are read.
    """
    estimates=bot_color_beliefs(room,bot_i)[bot_i]
    p=room.players[bot_i]
    counts=Counter(col(c) for c in p.hand if c!='start')
    cfg=rule(room)
    next_position=len(room.completion_order)+1
    forced=dict(cfg.color_positions)
    char_fixed=dict(cfg.completion_positions).get(p.char)
    def score(color):
        n=counts[color]
        x= 3.8*estimates[color] + 0.9*n
        if color==p.goal:x+=0.4
        if forced.get(color, next_position) < next_position: x-=12
        if char_fixed == next_position and forced.get(color) == next_position: x+=12
        return x
    return max(COLORS,key=lambda c:(score(c),-COLORS.index(c)))


def known_preference(room: Room, bot_i: int, dest_i: int, color: str):
    """Backward-compatible helper: preference supported by public/owned evidence."""
    return visible_preference(room, bot_i, dest_i, color)


def ai_completion_constraints(room: Room, bot_i: int) -> dict:
    """Public mission order + publicly recorded completions; no private hands."""
    cfg = rule(room)
    position = len(room.completion_order) + 1
    char_pos = dict(cfg.completion_positions)
    color_pos = dict(cfg.color_positions)
    required_char = next((ch for ch, rank in char_pos.items() if rank == position), None)
    required_color = next((color for color, rank in color_pos.items() if rank == position), None)
    return {'position':position, 'character':required_char, 'color':required_color,
            'character_order':char_pos, 'color_order':color_pos}


def ai_can_finish_now(room: Room, player_idx: int, color: str) -> bool:
    """Whether publicly defined completion restrictions allow that finish."""
    x = ai_completion_constraints(room, player_idx)
    char = room.players[player_idx].char
    if char in x['character_order'] and x['character_order'][char] != x['position']:
        return False
    if x['character'] is not None and char != x['character']:
        return False
    if color in x['color_order'] and x['color_order'][color] != x['position']:
        return False
    if x['color'] is not None and color != x['color']:
        return False
    return True


def ai_safe_to_leave_table(room: Room, finisher: int) -> bool:
    """Completing a set never strands two players due to opposite restriction.

    Once anyone completes a set, there are fewer than four active seats,
    and the opposite-seat prohibition no longer applies. Other restrictions
    (left-only/right-forbidden) continue to use their own mission rules.
    """
    return True


def ai_public_completion_schedules(room: Room) -> list[tuple[int, ...]]:
    """Enumerate possible finishing orders using public mission constraints only.

    This is a planning aid, not a prediction of hidden hand contents. Each
    returned tuple lists player indices from next finisher to last finisher.
    """
    cfg = rule(room)
    done = {ev["player"]: rank + 1 for rank, ev in enumerate(room.completion_order)}
    char_fixed = dict(cfg.completion_positions)
    color_fixed = dict(cfg.color_positions)
    unfinished = tuple(i for i, p in enumerate(room.players) if not p.done)
    starts = len(room.completion_order)
    possible = []
    for order in permutations(unfinished):
        ranks = dict(done)
        ranks.update({player: starts + offset + 1 for offset, player in enumerate(order)})
        if any(ranks[i] != char_fixed[p.char] for i,p in enumerate(room.players)
               if p.char in char_fixed):
            continue
        # An explicit color position must be feasible at that rank. Known
        # completed colors are public; unknown future colors remain unknown.
        feasible = True
        for color, position in color_fixed.items():
            holder = next((x['player'] for x in room.completion_order
                           if x.get('color') == color), None)
            if holder is not None and ranks[holder] != position:
                feasible = False
                break
        if feasible:
            possible.append(order)
    return possible


def ai_scheduler_value(room: Room, sender: int, recipient: int, color: str,
                       beliefs: dict[int, dict[str, float]]) -> float:
    """Public-order and seating-aware receiver/chip scheduling heuristic.

    No opponent hidden hand or private goal reads. Completion rank, seats and
    remaining chips are visible. This is deliberately an optional ablation.
    """
    schedules = ai_public_completion_schedules(room)
    if not schedules:
        return 0.0
    active = [i for i,p in enumerate(room.players) if not p.done]
    ranks = {idx: sum(order.index(idx) for order in schedules)/len(schedules)
             for idx in active}
    # Lower expected rank means a player should finish sooner.
    urgency = (len(active)-1-ranks[recipient])/max(1,len(active)-1)
    fit = beliefs[recipient].get(color,0.25)
    score = 1.8 * urgency * (fit-0.25)
    # Spending a reception on low-probability colors is riskier for a nearly
    # exhausted receiver; keep this modest because the baseline already has
    # explicit imminent-failure penalties.
    if room.shared_chips is None:
        chips = room.players[recipient].chips
        if chips <= 3:
            score -= (4-chips)*1.4*max(0.,0.55-fit)
    return score


def bot_choice(room: Room, i: int):
    """Choose one legal transfer using a changing goal and observable evidence.

    The bot never reads opponents' hidden card identities or internal bot goals.
    Rather than pick an arbitrary target, it prioritizes recipients who signaled
    that they need the color, avoids recently rejected colors, and weighs chips.
    """
    p = room.players[i]
    others = [j for j, other in enumerate(room.players) if j != i and not other.done]
    if not others:
        return None
    p.goal = bot_goal(room, i)
    team_beliefs = bot_color_beliefs(room, i)
    info_cards = [c for c in p.hand if c != "start"]
    counts = Counter(col(c) for c in info_cards)

    # When a set of five is ready, pass the Starting Card to complete it.
    completed_color = col(info_cards[0]) if info_cards and info_set(info_cards) else None
    if "start" in p.hand and completed_color:
        # Passing START would immediately finish our set. Never deliberately
        # trigger a forbidden finish just because our hand is monochromatic.
        if ai_can_finish_now(room, i, completed_color) and ai_safe_to_leave_table(room, i):
            candidates = ["start"]
        else:
            candidates = info_cards  # delay our completion; pass one color card
    else:
        unwanted = [c for c in info_cards if col(c) != p.goal]
        if unwanted:
            candidates = (info_cards if (rule(room).completion_positions or rule(room).color_positions) else unwanted)
            # A hand with six Information Cards may contain five of our
            # chosen color plus one unwanted card. Discarding that unwanted
            # card would immediately complete a set, which is illegal when
            # a teammate or another color must finish first. Sacrifice one
            # collecting-color card instead of knowingly failing the mission.
            if any(info_set([x for j,x in enumerate(p.hand) if j != idx]) and
                   (not ai_can_finish_now(room, i, next((col(x) for x in p.hand if x != 'start' and x != card), None)) or not ai_safe_to_leave_table(room, i))
                   for idx, card in enumerate(p.hand) if card in unwanted):
                candidates = info_cards
        elif "start" in p.hand:
            candidates = ["start"]
        else:
            candidates = info_cards  # unavoidable if the hand contains one color

    ranked = []
    cfg = rule(room)
    next_position = len(room.completion_order) + 1
    fixed_positions = dict(cfg.completion_positions)
    color_positions = dict(cfg.color_positions)
    for card in candidates:
        color = col(card)
        for target in others:
            if not can_pass(room,i,card,target):
                continue
            dest = room.players[target]
            # Conserve turns on very constrained receivers unless a meaningful
            # preference is known; chip shortage is a *cost*, not perfect knowledge.
            score = 0.0
            if card == "start":
                # Starting Card cannot help form an Information Set.
                score -= 3.0
                if info_set(info_cards):
                    score += 30.0
                # Prefer a receiver with enough chips to continue.
                score += 0.18 * dest.chips
            else:
                pref = visible_preference(room, i, target, color)
                # A four-way matching prior discounts transfers that cause
                # several agents to compete for the same color.
                estimated_fit = team_beliefs[target].get(color, 0.25)
                score += 10.5 * (estimated_fit - 0.25)
                score += ai_two_turn_value(room, i, target, color, team_beliefs)
                if os.getenv("SORT5_SCHEDULER", "off").lower() == "on":
                    score += ai_scheduler_value(room, i, target, color, team_beliefs)
                score += 1.10 * pref
                if os.getenv('SORT5_FEEDBACK_V47', 'off').lower() == 'on':
                    score += feedback_priority_v47(room, i, target, color)
                # Refuse to blindly send cards to someone who has repeatedly
                # responded red to this color.
                if pref < -2.0:
                    score += pref * 0.8
                # Favor handing a color to someone who publicly holds several
                # of it already, without peeking at private information.
                public_count = sum(col(x) == color for x in dest.hand if x in room.public)
                score += 0.72 * public_count
                likely_held = ai_estimated_target_holdings(room, i, target, color)
                # Forecast whether this unique card probably brings the
                # receiver close to a complete five-card set.
                if likely_held >= 1.3 and estimated_fit >= 0.35:
                    score += min(8.0, (likely_held - 0.9) * 3.8) * estimated_fit
                if public_count >= 4:
                    score += 7.0
                # Public mission finish order changes who should receive
                # useful cards. Private hands and other bots' goals are not used.
                route = ai_completion_constraints(room, i)
                if route['color'] == color:
                    score += 3.5
                if route['character'] is not None and dest.char == route['character']:
                    score += 5.5
                    if route['color'] == color:
                        score += 6.5
                # Berlin #01: favor cards that the required first finisher
                # has *actually* signaled as useful. Avoid forcing speculative
                # passes based on unseen hands (tested against baseline).
                if room.city == 'berlin' and room.mission == 1 and route['character'] is not None and dest.char == route['character'] and pref > 0:
                    score += 2.0 * min(pref, 3.0)
                # Avoid accelerating a visibly nearly-finished wrong-order
                # player. They could be holding the needed set already.
                if public_count >= 3 and not ai_can_finish_now(room, target, color):
                    score -= 19.0 + 3.0 * (public_count - 3)
                # A required finishing color must reach an eligible character,
                # not just any player reacting positively to that color.
                if route['color'] == color and not ai_can_finish_now(room, target, color):
                    score -= 10.0
                # Do not give up our own chosen color unless forced.
                if color == p.goal:
                    score -= 6.0 + 1.3 * counts[color]
                else:
                    # Slight urgency to stop carrying colors not being collected.
                    score += 0.2 * (len(info_cards) - counts[color])
            # A player with one chip cannot afford repeated low-value transfers.
            available=room.shared_chips if room.shared_chips is not None else dest.chips
            # An ordinary reception at the last chip *fails immediately*
            # unless the receiver is the last active player. Do not burn the
            # team's entire run when another recipient is available.
            if room.shared_chips is None:
                if available <= 1 and (sum(not q.done for q in room.players) > 2 or not info_set([x for x in p.hand if x != card])):
                    score -= 55.0
                elif available <= 2:
                    score -= 5.0
                else:
                    score += 0.08 * available
            else:
                # Shared pool: changing recipients does not change the cost.
                # Only the information value of this action can help.
                if available <= 2:
                    score -= 1.5
            # Do not bounce the exact same rejected card straight back.
            if p.last_received == card and p.last_sender == target:
                score -= 7.0
            # Predict whether *our own* remaining hand would complete a set.
            # The original engine treats the completion as immediate and a wrong
            # finishing position loses the mission. Avoid it whenever possible.
            remainder = list(p.hand)
            remainder.remove(card)
            if info_set(remainder):
                finish_color = next(iter({col(c) for c in remainder if c != 'start'}), None)
                wrong = (not ai_can_finish_now(room, i, finish_color) or not ai_safe_to_leave_table(room, i))
                if cfg.require_start_pass and card != 'start':
                    wrong = False  # This mission requires a later Starting Card pass.
                if wrong: score -= 1000.0
                else: score += 15.0
            # Maintain the position reserve for teammates, using only public completed sets.
            if p.char in fixed_positions and fixed_positions[p.char] > next_position:
                score -= 0.7 if col(card) == p.goal else 0.0
            score += random.random() * 0.10
            ranked.append((score, card, target))
    if not ranked:
        return None
    _, card, target = max(ranked)
    return card, target

def advance_bot(room: Room):
    """Perform exactly one AI card transfer and its receiver feedback, if AI.
    All actions are server-side and never expose a hidden card in public events.
    """
    if room.phase != "turn" or room.turn is None or not room.players[room.turn].bot:
        raise ValueError("There is no AI turn to advance")
    i = room.turn
    decision = bot_choice(room, i)
    if decision is None:
        finish(room, False, "No legal recipient remains.")
        return
    card, target = decision
    if room.players[i].char in rule(room).two_cards:
        second = bot_second_offer(room, i, card, target)
        if second is None:
            finish(room,False,"AI cannot assemble the mandatory two-card offer.")
        else:
            offer_cards(room,i,[card,second],target)
    else:pass_card(room, i, card, target)


def snapshot(room: Room, viewer: int, inspect: Optional[int] = None):
    if inspect is not None and (not room.debug or room.players[viewer].token != room.owner):
        raise HTTPException(403, "Debug inspect requires the room owner and test mode")
    view = viewer if inspect is None else inspect
    owner = room.players[viewer]
    players = []
    for i, p in enumerate(room.players):
        show = view == i
        players.append({
            "index": i, "seat": p.seat if p.seat is not None else i, "name": p.name, "bot": p.bot, "char": p.char,
            "symbol": SYMBOLS[p.char] if p.char is not None else None,
            "chips": p.chips if room.phase not in ("lobby", "characters") else None,
            "done": p.done, "is_me": i == view,
            "hand": [visible_card(c, c in room.public, show) for c in p.hand],
            # Only the holder sees the newest received card's identity.
            "last_received": p.last_received if show and p.last_received in p.hand else None,
            "hand_size": len(p.hand), "revealed": p.reveal_done,
            "held_face_down": p.held_card is not None,
        })
    pending = room.pending.copy() if room.pending else None
    if pending:
        if room.phase=='guess':
            pending.pop('card',None)  # receiver must guess before looking
        if room.phase in ('feedback', 'announce') and view!=pending['to']:
            pending.pop('card',None)
        if room.phase=='offer_choice':
            pending.pop('cards',None) # sender hand remains confidential
        if room.phase=='initial_pass':pending=None
    return {
        "code": room.code, "phase": room.phase, "humans": room.humans,
        "human_joined": len([p for p in room.players if not p.bot]),
        "mission": room.mission, "city":room.city, "rules": rule(room).description,
        "shared_chips":room.shared_chips,"completion_order":room.completion_order,
        "initial_pass_ready": len(room.initial_passes),
        "initial_pass_submitted": str(viewer) in room.initial_passes,
        # Never return internal pending card IDs or the unguessed number to other players.
        "offer": ({"from": room.pending["from"], "to": room.pending["to"],
                   "public_cards": (room.pending.get("recipient_cards") or room.pending["public_cards"]) if viewer == room.pending["to"] else room.pending["public_cards"]}
                  if room.phase == 'offer_choice' and room.pending else None),
        "players": players, "me": view, "original_me": viewer,
        "my_token": owner.token, "my_character": room.players[view].char,
        "is_owner": owner.token == room.owner,
        "debug": room.debug, "inspect": inspect,
        "announcement_count": (sum(col(c)==col(room.pending['card']) for c in room.players[view].hand)
                               if room.phase == 'announce' and room.pending and room.pending['to']==view else None),
        "turn": room.turn, "pending": pending,
        "starting_player": next((i for i, p in enumerate(room.players) if "start" in p.hand), None) if room.move_count == 0 else None,
        "history": room.history[-40:], "moves": room.move_count,
        "turn_events": [{k:v for k,v in event.items() if k!='number'} for event in room.turn_events[-120:]],
        "legal_targets": (
            [j for j in range(len(room.players))
             if j != view and not room.players[j].done
             and any(can_pass(room, view, c, j) for c in room.players[view].hand)]
            if room.phase == "turn" and room.turn == view and inspect is None else []
        ),
        "ai_waiting": (room.phase == "turn" and room.turn is not None and room.players[room.turn].bot),
        "result": room.result, "reason": room.reason,
        "start_policy": START_RECEIPT_POLICY,
        "allowed_actions": (['initial_pass'] if room.phase=='initial_pass' else
                            ['choose_offer'] if room.phase=='offer_choice' and pending and pending.get('to')==viewer else
                            ['guess_number'] if room.phase=='guess' and pending and pending.get('to')==viewer else
                            ['offer'] if room.phase=='turn' and room.turn==viewer and room.players[viewer].char in rule(room).two_cards else []),
    }

@APP.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")

@APP.get("/api/missions")
def available_missions():
    """Mission metadata for UI integration. Artwork is supplied separately."""
    return {"cities":[{"id":city,"name":CITY_NAMES[city],"missions":[{
        "number":n,"description":M[(city,n)].description,
        "chips":M[(city,n)].chips,"shared_chips":M[(city,n)].pool,
        "artwork_prefix":f"{'newyork' if city=='new_york' else city}_{n:02d}"
    } for n in range(1,6)]} for city in CITY_ORDER]}

@APP.get("/health")
def health():
    return {"ok": True, "storage": "upstash" if REMOTE_STORE else ("unconfigured" if os.getenv("VERCEL") else "local"), "rooms_local": len(ROOMS) if not REMOTE_STORE else None}

@APP.post("/api/new")
def create(body: CreateBody):
    # Inspection can reveal every player's private hand. Keep it off for publicly
    # distributed rooms; a trusted local developer can opt in explicitly.
    allow_debug = os.getenv("SORT5_ALLOW_DEBUG", "").lower() in ("1", "true", "yes")
    with ROOMS_LOCK:
        token = secrets.token_urlsafe(24)
        for _ in range(100):
            code = new_code()
            if (body.city,body.mission) not in M: raise HTTPException(422,"Invalid city or mission")
            room = Room(code=code, humans=body.humans, mission=body.mission, city=body.city,debug=(body.debug and allow_debug),
                        players=[Player(name=body.name.strip(), token=token, seat=0)], owner=token)
            if save_room(room, new=True):
                return {"code": code, "token": token}
    raise HTTPException(503, "Unable to allocate game room")

@APP.post("/api/join")
def join(body: JoinBody):
    code = body.code.strip().upper()
    with exclusive_room(code):
        room = get_room(code)
        if room is None:
            raise HTTPException(404, "Room not found")
        if room.phase != "lobby" or len(room.players) >= room.humans:
            raise HTTPException(409, "This room cannot accept more players")
        name = body.name.strip()
        if name in [p.name for p in room.players]:
            raise HTTPException(409, "This nickname is already in use")
        token = secrets.token_urlsafe(24)
        room.players.append(Player(name=name, token=token, seat=len(room.players)))
        save_room(room)
    return {"code": code, "token": token}

@APP.get("/api/state")
def state(code: str = Query(...), token: str = Query(...), inspect: Optional[int] = Query(default=None, ge=0, le=3)):
    room, i = room_and_player(code, token)
    return snapshot(room, i, inspect)

@APP.post("/api/action")
def action(body: ActionBody):
    with exclusive_room(body.code):
        room, i = room_and_player(body.code, body.token)
        p = room.players[i]
        try:
            if body.type == "begin":
                if room.owner != p.token:
                    raise ValueError("Only the host can start the game")
                start_game(room)
            elif body.type == "character":
                if room.phase != "characters" or p.char is not None:
                    raise ValueError("You cannot choose a character now")
                if body.character is None or body.character not in range(4):
                    raise ValueError("Select a valid character")
                if any(x.char == body.character for x in room.players):
                    raise ValueError("That character is already taken")
                p.char = body.character
                append_history(room, f"{p.name} selected the {SYMBOLS[p.char]} character.")
                if all(x.char is not None for x in room.players if not x.bot):
                    assign_bot_characters(room)
            elif body.type == "reveal":
                if room.phase != "reveal" or p.reveal_done or not body.card or body.card not in p.hand or body.card == "start":
                    raise ValueError("Choose one valid Information Card to reveal")
                room.public.add(body.card)
                p.reveal_done = True
                append_history(room, f"{p.name} revealed one Information Card.")
                if all(x.reveal_done for x in room.players):
                    start_turn(room)
            elif body.type == "pass":
                if body.card is None or body.target is None:
                    raise ValueError("Select a card and another active player")
                if p.char in rule(room).two_cards:
                    raise ValueError("This character must offer two cards; use offer action")
                pass_card(room, i, body.card, body.target)
            elif body.type == "offer":
                if body.cards is None or body.target is None:raise ValueError("Select two cards and a recipient")
                offer_cards(room,i,body.cards,body.target)
            elif body.type == "choose_offer":
                if room.phase!='offer_choice' or not room.pending or room.pending['to']!=i:
                    raise ValueError("You are not choosing from an offer")
                choose_offer(room,i,0 if body.choice=='0' else 1 if body.choice=='1' else -1)
            elif body.type == "guess_number":
                guess_received_card(room,i,body.guess if body.guess is not None else -1)
            elif body.type == "initial_pass":
                if room.phase!='initial_pass' or not body.card or body.card=='start' or body.card not in p.hand:
                    raise ValueError("Choose an Information Card for the initial pass")
                if str(i) in room.initial_passes:raise ValueError("Already selected")
                room.initial_passes[str(i)]=body.card
                resolve_initial_pass(room)
            elif body.type == "feedback":
                if (room.phase != "feedback" or room.pending is None
                        or room.pending.get("to") != i or body.positive is None):
                    raise ValueError("It is not your feedback turn")
                apply_feedback(room, i, body.positive)
            elif body.type == "announce":
                if (rule(room).feedback != 'count_color' or room.phase != 'announce'
                        or room.pending is None or room.pending.get('to') != i):
                    raise ValueError('Only the receiving player may confirm the announcement')
                # Count is derived server-side, never trusted from the client.
                apply_feedback(room, i, False)
            elif body.type == "advance_ai":
                # Any participating human can request the next single AI action.
                advance_bot(room)
            elif body.type == "retry":
                if room.owner != p.token:
                    raise ValueError("Only the room owner can restart")
                # The host explicitly confirmed restarting the current mission.
                # Keep participant credentials and room code, clear the old deal.

                room.players = room.players[:room.humans]
                room.phase = "lobby"
                room.turn = None;room.pending = None
                for human in room.players:
                    human.char = None;human.hand.clear();human.chips = 0;human.done = False
                    human.held_card=None;human.start_pass_confirmed=False
                room.history.clear();room.turn_events.clear();room.public.clear();room.result=None;room.reason=""
                room.completion_order.clear();room.initial_passes.clear();room.shared_chips=None;room.last_guess_wrong=False
                room.move_count=0;room.evidence.clear();room.pending_transfer=None
            elif body.type == "next":
                if room.phase != "ended" or room.result != "success" or room.owner != p.token:
                    raise ValueError("Only the host may start the next mission after success")
                if room.mission == 5:
                    current_index = CITY_ORDER.index(room.city)
                    if current_index == len(CITY_ORDER) - 1:
                        raise ValueError("All 30 missions are complete")
                    room.city = CITY_ORDER[current_index + 1]
                    room.mission = 1
                else:
                    room.mission += 1
                room.phase = "lobby"
                room.players = room.players[:room.humans]
                room.turn = None;room.pending = None
                for human in room.players:
                    human.char = None;human.hand.clear();human.chips = 0;human.done = False
                    human.held_card=None;human.start_pass_confirmed=False
                room.history.clear();room.turn_events.clear();room.public.clear();room.result=None;room.reason=""
                room.completion_order.clear();room.initial_passes.clear();room.shared_chips=None;room.last_guess_wrong=False
            else:
                raise ValueError("Unknown action")
        except ValueError as e:
            raise HTTPException(400, str(e))
        save_room(room)
        return snapshot(room, i)


# FastAPI application name recognized by Vercel Python runtime.
app = APP
