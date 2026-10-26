"""SORT 5 Seoul: server-authoritative, private-hand cooperative playtest.
Run: uvicorn server:app --host 0.0.0.0 --port 8000
No third-party AI API; bots use only public information and cards they possess.
"""
from __future__ import annotations

from collections import Counter
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
MISSION_CHIPS = {
    1: [6, 6, 6, 6],
    2: [5, 5, 5, 5],
    3: [5, 4, 5, 5],
    4: [6, 6, 4, 5],
    5: [6, 6, 6, 6],
}
MISSION_RULES = {
    1: "All players pass cards face up.",
    2: "Before the mission, each player reveals 1 card from their hand. Those cards remain face up; other cards are passed face down.",
    3: "Before looking at their initial hand, each player randomly reveals 1 card. Those cards remain face up.",
    4: "The ● character passes cards face up.",
    5: "Standard rules apply.",
}

# A non-information Starting Card is treated as 'not needed' on receipt in this
# playtest. The rulebook does not state a special exception; verify with publisher.
START_RECEIPT_POLICY = "consume_negative_chip"

class CreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    humans: int = Field(default=1, ge=1, le=4)
    mission: int = Field(default=1, ge=1, le=5)
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

@dataclass
class Player:
    name: str
    token: str
    bot: bool = False
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

@dataclass
class Room:
    code: str
    humans: int
    mission: int
    debug: bool
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
    for p in room.players:
        p.chips = MISSION_CHIPS[room.mission][p.char]
    starter = next(i for i, p in enumerate(room.players) if p.char == 0)
    room.players[starter].hand.append("start")
    # A bot's color is a working hypothesis, not a fixed assignment.
    for i, p in enumerate(room.players):
        if p.bot:
            p.goal = bot_goal(room, i)
    append_history(room, "Characters assigned. The ▲ character receives the Starting Card.")
    if room.mission == 2:
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
            start_turn(room)
    else:
        start_turn(room)

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

def start_game(room: Room):
    if room.phase != "lobby":
        raise ValueError("Game already started")
    if len(room.players) != room.humans:
        raise ValueError(f"Waiting for {room.humans - len(room.players)} more human player(s)")
    room.players = room.players[:room.humans] + [
        Player(name=f"BOT {i+1}", token="", bot=True)
        for i in range(4 - room.humans)
    ]
    deck = [cid(c, n) for c in COLORS for n in range(1, 6)]
    random.shuffle(deck)
    room.public.clear();room.history.clear();room.result = None;room.reason = ""
    room.turn = None;room.pending = None;room.move_count = 0
    room.evidence.clear();room.pending_transfer = None;room.turn_events.clear()
    for p in room.players:
        p.hand = [deck.pop() for _ in range(5)]
        p.char = None;p.chips = 0;p.done = False;p.reveal_done = False;p.goal = None
        p.last_received = None;p.last_sender = None;p.observed_offers.clear()
    if room.mission == 3:
        # Random selection is committed before any player can view initial hands.
        for p in room.players:
            room.public.add(random.choice(p.hand))
    room.phase = "characters"
    append_history(room, f"Seoul #{room.mission:02d}: Information Cards dealt; choose characters.")
    if room.mission == 3:
        append_history(room, "One random card from every hand is now face up, before the hands were viewed.")

def can_pass(room: Room, i: int, c: str, target: int):
    return (room.phase == "turn" and room.turn == i
        and c in room.players[i].hand and target != i
        and 0 <= target < 4 and not room.players[target].done)

def complete_player(room: Room, i: int, final=False):
    p = room.players[i]
    if p.done:
        return
    p.done = True
    room.public.update(p.hand)
    append_history(room, f"{p.name} completed a set and revealed their hand.")
    p.chips = 0  # remaining Time Chips cannot be used

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
            finish(room, True, "Seoul mission cleared! All four Information Sets are complete.")
        else:
            room.public.update(room.players[target].hand)
            finish(room, False, "The final player revealed an incomplete Information Set.")
        return
    p = room.players[target]
    if p.chips <= 0:
        finish(room, False, f"{p.name} has no Time Chips available to receive another card.")
        return
    if card == "start":
        apply_feedback(room, target, False, is_start=True)
    elif p.bot:
        # Re-evaluate *after* receiving the card and *before* signaling need.
        # The decision is based on its own hand and observable clues.
        p.goal = bot_goal(room, target)
        apply_feedback(room, target, bot_need(p, card))
    else:
        room.phase = "feedback"
        room.pending = {"to": target, "card": card}

def pass_card(room: Room, i: int, card: str, target: int):
    if not can_pass(room, i, card, target):
        raise ValueError("Illegal card transfer or wrong player's turn")
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
    face_up = room.mission == 1 or (room.mission == 4 and source.char == 1)
    if face_up:
        room.public.add(card)
    label = "face up" if card in room.public else "face down"
    append_history(room, f"{source.name} passed a card to {receiver.name} ({label}).")
    room.turn_events.append({"step": room.move_count, "from": i, "to": target,
                             "card": card if card in room.public else None,
                             "face_up": card in room.public, "reaction": None})
    if info_set(source.hand):
        complete_player(room, i)
    room.turn = target
    room.pending_transfer = {"sender": i, "to": target, "card":card, "public": card in room.public}
    after_received(room, target, card)
    # Do not automatically take AI turns; one click = one transfer.

def apply_feedback(room: Room, i: int, positive: bool, is_start=False):
    p = room.players[i]
    if p.chips <= 0:
        finish(room, False, f"{p.name} has no remaining Time Chips.")
        return
    if room.turn_events and room.turn_events[-1]["to"] == i and room.turn_events[-1]["reaction"] is None:
        room.turn_events[-1]["reaction"] = "positive" if positive else "negative"
    if room.pending_transfer is not None:
        transfer = room.pending_transfer
        if transfer["to"] == i and transfer["card"] != "start":
            room.evidence.append({
                "sender": transfer["sender"], "to": i,
                "color": col(transfer["card"]), "positive": positive,
                "public": transfer["public"],
                "card": transfer["card"], "step": room.move_count,
            })
        room.pending_transfer = None
    p.chips -= 1
    p_text = "red / not needed" if (not positive) else "green / needed"
    append_history(room, f"{p.name}: {p_text} feedback. ({p.chips} Time Chips left)")
    room.pending = None
    room.phase = "turn"
    # No one is declared complete merely by receiving, except the last player.
    if p.chips == 0 and not p.done:
        finish(room, False, f"{p.name} ran out of Time Chips before completing a set.")

def bot_need(p: Player, card: str):
    """Signal whether the last card supports the bot's *current* plan."""
    return card != "start" and p.goal == col(card)


def visible_preference(room: Room, bot_i: int, dest_i: int, color: str) -> float:
    """Estimate another player's color needs from information this bot can know.

    Private reactions alone do not expose a card's color. Color-specific evidence
    is usable only when this bot passed that card or the card was public.
    """
    weight = 0.0
    for event in room.evidence:
        if event["to"] != dest_i or event["color"] != color:
            continue
        if event["sender"] != bot_i and not event["public"]:
            continue
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


def bot_goal(room: Room, bot_i: int) -> str:
    """Select a working color from OWN cards, publicly visible cards and clues.

    The old implementation assigned `goal` only when characters were chosen.
    Now this is called after each incoming card and before every AI choice.
    Small hysteresis discourages oscillations when scores are close.
    """
    bot = room.players[bot_i]
    counts = Counter(col(c) for c in bot.hand if c != "start")
    active = [j for j, other in enumerate(room.players) if j != bot_i and not other.done]
    scores = {}
    for color in COLORS:
        n = counts[color]
        # Completing 5 distinct numbers is more important than transient feedback.
        score = 2.25*n + 0.42*(n*n)
        if bot.goal == color:
            score += 0.75  # stable preference, not an irreversible lock
        for j in active:
            claim = visible_preference(room, bot_i, j, color)
            if claim > 1.2:
                # Others have shown signs of gathering this color.
                score -= min(3.6, 0.43*claim)
            # A visibly exposed card held by another player may be recoverable,
            # but don't overvalue a color with several such cards elsewhere.
            publicly_elsewhere = sum(col(c) == color for c in room.players[j].hand
                                     if c in room.public)
            score -= 0.19 * publicly_elsewhere
        scores[color] = score
    return max(COLORS, key=lambda c: (scores[c], -COLORS.index(c)))


def known_preference(room: Room, bot_i: int, dest_i: int, color: str):
    """Backward-compatible helper: preference supported by public/owned evidence."""
    return visible_preference(room, bot_i, dest_i, color)


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
    info_cards = [c for c in p.hand if c != "start"]
    counts = Counter(col(c) for c in info_cards)

    # When a set of five is ready, pass the Starting Card to complete it.
    if "start" in p.hand and info_set(info_cards):
        candidates = ["start"]
    else:
        unwanted = [c for c in info_cards if col(c) != p.goal]
        if unwanted:
            candidates = unwanted
        elif "start" in p.hand:
            candidates = ["start"]
        else:
            candidates = info_cards  # unavoidable if the hand contains one color

    ranked = []
    for card in candidates:
        color = col(card)
        for target in others:
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
                score += 1.45 * pref
                # Refuse to blindly send cards to someone who has repeatedly
                # responded red to this color.
                if pref < -2.0:
                    score += pref * 0.8
                # Favor handing a color to someone who publicly holds several
                # of it already, without peeking at private information.
                public_count = sum(col(x) == color for x in dest.hand if x in room.public)
                score += 0.72 * public_count
                if public_count >= 4:
                    score += 7.0
                # Do not give up our own chosen color unless forced.
                if color == p.goal:
                    score -= 6.0 + 1.3 * counts[color]
                else:
                    # Slight urgency to stop carrying colors not being collected.
                    score += 0.2 * (len(info_cards) - counts[color])
            # A player with one chip cannot afford repeated low-value transfers.
            if dest.chips <= 1:
                score -= 3.0
            elif dest.chips <= 2:
                score -= 1.2
            else:
                score += 0.1 * dest.chips
            # Do not bounce the exact same rejected card straight back.
            if p.last_received == card and p.last_sender == target:
                score -= 7.0
            # Small stochastic tie break to avoid identical loops.
            score += random.random() * 0.18
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
    pass_card(room, i, card, target)


def snapshot(room: Room, viewer: int, inspect: Optional[int] = None):
    if inspect is not None and (not room.debug or room.players[viewer].token != room.owner):
        raise HTTPException(403, "Debug inspect requires the room owner and test mode")
    view = viewer if inspect is None else inspect
    owner = room.players[viewer]
    players = []
    for i, p in enumerate(room.players):
        show = view == i
        players.append({
            "index": i, "name": p.name, "bot": p.bot, "char": p.char,
            "symbol": SYMBOLS[p.char] if p.char is not None else None,
            "chips": p.chips if room.phase not in ("lobby", "characters") else None,
            "done": p.done, "is_me": i == view,
            "hand": [visible_card(c, c in room.public, show) for c in p.hand],
            "hand_size": len(p.hand), "revealed": p.reveal_done,
        })
    pending = room.pending.copy() if room.pending else None
    if pending and view != pending["to"]:
        pending.pop("card", None)
    return {
        "code": room.code, "phase": room.phase, "humans": room.humans,
        "human_joined": len([p for p in room.players if not p.bot]),
        "mission": room.mission, "rules": MISSION_RULES[room.mission],
        "players": players, "me": view, "original_me": viewer,
        "my_token": owner.token, "my_character": room.players[view].char,
        "is_owner": owner.token == room.owner,
        "debug": room.debug, "inspect": inspect,
        "turn": room.turn, "pending": pending,
        "starting_player": next((i for i, p in enumerate(room.players) if "start" in p.hand), None) if room.move_count == 0 else None,
        "history": room.history[-40:], "moves": room.move_count,
        "turn_events": room.turn_events[-120:],
        "ai_waiting": (room.phase == "turn" and room.turn is not None and room.players[room.turn].bot),
        "result": room.result, "reason": room.reason,
        "start_policy": START_RECEIPT_POLICY,
    }

@APP.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")

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
            room = Room(code=code, humans=body.humans, mission=body.mission, debug=(body.debug and allow_debug),
                        players=[Player(name=body.name.strip(), token=token)], owner=token)
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
        room.players.append(Player(name=name, token=token))
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
                pass_card(room, i, body.card, body.target)
            elif body.type == "feedback":
                if (room.phase != "feedback" or room.pending is None
                        or room.pending.get("to") != i or body.positive is None):
                    raise ValueError("It is not your feedback turn")
                apply_feedback(room, i, body.positive)
            elif body.type == "advance_ai":
                # Any participating human can request the next single AI action.
                advance_bot(room)
            elif body.type == "retry":
                if room.phase != "ended":
                    raise ValueError("You can restart only after a mission ends")
                if room.owner != p.token:
                    raise ValueError("Only the room owner can restart")
                room.players = room.players[:room.humans]
                room.phase = "lobby"
                room.turn = None;room.pending = None
                for human in room.players:
                    human.char = None;human.hand.clear();human.chips = 0;human.done = False
                room.history.clear();room.turn_events.clear();room.public.clear();room.result=None;room.reason=""
            elif body.type == "next":
                if room.phase != "ended" or room.result != "success" or room.owner != p.token:
                    raise ValueError("Only the host may start the next mission after success")
                if room.mission == 5:
                    raise ValueError("All five Seoul missions are complete")
                room.mission += 1
                room.phase = "lobby"
                room.players = room.players[:room.humans]
                room.turn = None;room.pending = None
                for human in room.players:
                    human.char = None;human.hand.clear();human.chips = 0;human.done = False
                room.history.clear();room.turn_events.clear();room.public.clear();room.result=None;room.reason=""
            else:
                raise ValueError("Unknown action")
        except ValueError as e:
            raise HTTPException(400, str(e))
        save_room(room)
        return snapshot(room, i)


# FastAPI application name recognized by Vercel Python runtime.
app = APP
