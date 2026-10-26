const app = document.getElementById('app');
let state = null;
let selectedCard = null;
let selectedTarget = null;
let missionSide = 'rules';
let errorText = '';
let polling = false;
let actionBusy = false;
let journalPerson = 'all';
let overlay = null;
let lastSnapshotSignature = '';
const PARAMS = new URLSearchParams(window.location.search);
const INSPECT = PARAMS.has('inspect') ? Number(PARAMS.get('inspect')) : null;
const qRoom = (PARAMS.get('room') || '').toUpperCase();
let credentials = null;
const escapeHTML = (x) => String(x == null ? '' : x).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const id = x => document.getElementById(x);
const assets = file => `/static/assets/${file}`;
const imageFor = card => {
  if(!card || !card.visible) return assets('cards_back.png');
  if(card.id === 'start') return assets('start_front.png');
  const [color, nn] = card.id.split('-');
  return assets(`${color === 'blue' ? 'cards' : 'card'}_${color}_${String(nn).padStart(2,'0')}.png`);
};
const charImg = char => char == null ? '' : assets(`character_${String(char+1).padStart(2,'0')}.png`);
function store(c){
  credentials = c;
  sessionStorage.setItem('sort5_credentials',JSON.stringify(c));
  if(c.debugOwner) localStorage.setItem(`sort5_debug_${c.code}`,c.token);
  window.history.replaceState({},'',`/?room=${c.code}`+(INSPECT !== null ? `&inspect=${INSPECT}` : ''));
}
async function request(url, body){
  const opts = body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {};
  const res = await fetch(url,opts);
  let data;
  try {data = await res.json();} catch {throw new Error(`Server error ${res.status}`);}
  if(!res.ok) throw new Error(data.detail || `Server error ${res.status}`);
  return data;
}
async function loadState(){
  if(!credentials || polling) return;
  polling = true;
  try {
    const u = `/api/state?code=${encodeURIComponent(credentials.code)}&token=${encodeURIComponent(credentials.token)}`+(INSPECT!==null?`&inspect=${INSPECT}`:'');
    const next=await request(u);
    const old = state;
    const sig=JSON.stringify(next);
    if(sig===lastSnapshotSignature && !errorText) return;
    lastSnapshotSignature=sig;
    state=next;
    if(old && (old.phase !== next.phase || old.turn !== next.turn || old.mission !== next.mission)) { selectedCard = null;selectedTarget=null; }
    errorText='';render();
  } catch(e){errorText=e.message;render();}
  finally {polling=false;}
}
async function action(type, extra={}){
  if(!credentials || actionBusy) return;
  actionBusy=true;
  try {
    const next=await request('/api/action',{type,code:credentials.code,token:credentials.token,...extra});
    state=next;
    lastSnapshotSignature=JSON.stringify(next);
    selectedCard=null;selectedTarget=null;errorText='';
    render();
    if(INSPECT!==null) await loadState();
  }catch(e){errorText=e.message;render();}
  finally{actionBusy=false;}
}
function topBar(){
  const subtitle = state ? `MISSION // SEOUL 0${state.mission}` : 'ONLINE CO-OP PLAYTEST';
  return `<header class="brandbar"><div class="brand">S.O.R.T. <b>5</b><small>${subtitle}</small></div><div class="header-right">${state?`<span class="chip">${state.humans} human · ${4-state.humans} AI</span><button type="button" class="chip code" data-do="copy">ROOM ${escapeHTML(state.code)} ⧉</button><button type="button" class="chip leave-btn" data-do="leave">Leave Game</button>`:''}</div></header>`;
}
function welcome(){
  app.innerHTML = `<div class="main welcome">${topBar()}<section class="hero"><div class="eyebrow">Happy Baobab / Digital Playtest</div><h1>Mission <span>S.O.R.T. 5</span></h1><p>Exchange information without speaking freely. Read each other's reactions, manage your Time Chips, and complete all four Information Sets.</p></section>
  <div class="welcome-grid"><section class="panel"><h2>Create a game room</h2><form id="create-form">
    <div class="field"><label>Your name</label><input name="name" maxlength="32" placeholder="e.g. Martin" required /></div>
    <div class="field"><label>Mission (Seoul)</label><select name="mission">${[1,2,3,4,5].map(n=>`<option value="${n}">Seoul #0${n}</option>`).join('')}</select></div>
    <div class="field"><label>Human players</label><select name="humans"><option value="1">1 human + 3 AI</option><option value="2">2 humans + 2 AI</option><option value="3">3 humans + 1 AI</option><option value="4">4 humans (online room)</option></select></div>
    <div class="field" style="flex-direction:row;align-items:center"><input type="checkbox" style="width:auto" name="debug" id="debug"><label for="debug" style="text-transform:none">Enable test-only seat inspection (host)</label></div>
    <button class="btn primary full" type="submit">Create room</button></form>
    <p class="small-note">Each human connects in their own browser. One player and three AI work immediately; 4-human online play requires a server reachable by all participants.</p></section>
  <section class="panel"><h2>Join an existing room</h2><form id="join-form">
    <div class="field"><label>Your name</label><input name="name" maxlength="32" placeholder="Your nickname" required /></div>
    <div class="field"><label>Room code</label><input name="code" id="join-code" value="${escapeHTML(qRoom)}" maxlength="6" placeholder="6-digit code" required /></div>
    <button class="btn full" type="submit">Join room</button></form>
    <p class="mini-title" style="margin-top:29px">How it works</p>
    <div class="status"><div class="status-line"><span>Information Cards</span>20 (4 colors × 1–5)</div><div class="status-line"><span>Starting Card</span>1</div><div class="status-line"><span>Mission Cards</span>Seoul #01–05</div><div class="status-line"><span>Goal</span>Complete 4 color sets</div></div></section></div>
  <div class="rule-strip"><span>Hidden hands by default</span><span>Face-up card exceptions</span><span>Server-checked turns</span><span>5 Seoul missions</span></div></div>`;
  id('create-form').onsubmit = async (e)=>{
    e.preventDefault();const f=new FormData(e.target);
    try{const ans=await request('/api/new',{name:f.get('name').trim(),mission:Number(f.get('mission')),humans:Number(f.get('humans')),debug:f.get('debug')==='on'});store({...ans,debugOwner:f.get('debug')==='on'});await loadState();}catch(ex){alert(ex.message);}
  };
  id('join-form').onsubmit = async (e)=>{
    e.preventDefault();const f=new FormData(e.target);
    try{const ans=await request('/api/join',{name:f.get('name').trim(),code:f.get('code').trim().toUpperCase()});store(ans);await loadState();}catch(ex){alert(ex.message);}
  };
}

// v0.4: one game surface, one action area, and one evidence journal.
function reactionToken(reaction, expanded=false) {
  if (!reaction) return `<span class="feedback-wait"><span class="dot-pulse"></span> Waiting for Reaction</span>`;
  const yes = reaction === 'positive';
  return `<span class="feedback-token ${yes?'yes':'no'}" aria-label="${yes?'Green Chip, Needed':'Red Chip, Not Needed'}"><span class="token-disc">${yes?'✓':'×'}</span>${expanded?`<span class="token-text"><b>${yes?'GREEN':'RED'}</b><small>${yes?'Needed':'Not Needed'}</small></span>`:''}</span>`;
}
function playerLabel(p){ return `${p.symbol || '○'} ${escapeHTML(p.name)}`; }
function ruleShort(){
  return {
    1: 'All players pass cards face up.',
    2: 'Before the mission, each player reveals 1 card. Revealed cards stay face up.',
    3: 'Before looking at their hand, each player randomly reveals 1 card. Revealed cards stay face up.',
    4: 'The ● character passes cards face up.',
    5: 'No additional mission rules. Follow the basic rules.'
  }[state.mission];
}
function missionRibbon(){
  const n=String(state.mission).padStart(2,'0');
  return `<section class="mission-ribbon" aria-label="Current mission">
    <div class="ribbon-title"><span class="ribbon-city">SEOUL</span><strong>#${n}</strong><span class="ribbon-star">★</span></div>
    <div class="ribbon-rule"><span class="rule-kicker">MISSION RULE</span><strong>${ruleShort()}</strong></div>
    <button class="secondary-pill" data-overlay="mission" title="View mission card">Mission Card <span>↗</span></button>
    <button class="secondary-pill" data-overlay="help" title="Basic game rules">Help <span>?</span></button>
  </section>`;
}
function playerBoard(){
  const me=state.me;
  const canTarget=state.inspect===null && state.phase==='turn' && state.turn===me && selectedCard;
  return `<section class="seat-board" aria-label="player status"><div class="section-top"><h2>Team Status <span>TEAM STATUS</span></h2><span class="tiny-label">Select a character to see cards they received</span></div>
    <div class="seat-grid">${state.players.map(p=>{
      const targetable=canTarget&&p.index!==me&&!p.done;
      const active=state.turn===p.index && ['turn','feedback'].includes(state.phase);
      const bits=['seat-card', p.is_me?'my-seat':'', active?'seat-active':'',p.done?'seat-done':'',targetable?'seat-targetable':'',selectedTarget===p.index?'seat-selected':''].join(' ');
      const cards=p.hand.map(c=>`<img class="seat-smallcard ${c.visible?'face-visible':''}" src="${imageFor(c)}" alt="${c.visible?'Face-up Card':'Face-down Card'}" title="${c.public?'Face-up Card':c.visible?'Your Hand':'Hidden Card'}" />`).join('');
      const last=state.turn_events?.slice().reverse().find(e=>e.to===p.index&&e.reaction);
      const chips=p.chips===null?'Preparing':`<span class="chip-value">${p.chips}</span>`;
      return `<article class="${bits}">
        <div class="seat-top">
          <img class="seat-avatar" src="${p.char===null?assets('cards_back.png'):charImg(p.char)}" alt="${escapeHTML(p.symbol||'Choose a character')}" />
          <div class="seat-identity"><div class="seat-name">${escapeHTML(p.name)}${p.is_me?'<span class="you-dot">YOU</span>':''}${p.bot?'<span class="bot-dot">AI</span>':''}</div><div class="seat-sub">${escapeHTML(p.symbol||'—')} ${p.char===null?'Choose a character':''}</div></div>
          ${active?'<span class="turn-dot">TURN</span>':p.done?'<span class="done-dot">DONE</span>':''}
        </div>
        <div class="seat-facts"><span><span class="tiny-fact-label">TIME</span> ${chips}</span><span><span class="tiny-fact-label">CARDS</span> <b>${p.hand_size}</b>  cards</span></div>
        <div class="seat-hand" aria-label="${escapeHTML(p.name)} public cards and hidden hand">${cards||'<span class="empty-seat">Set complete · No cards left</span>'}</div>
        <div class="seat-footer">
          <span class="seat-last">${last?`Last received #${last.step} ${reactionToken(last.reaction)}`:'No received cards yet'}</span>
          ${targetable?`<button class="seat-send" data-target="${p.index}">${selectedTarget===p.index?'✓ Recipient':'Pass to this player →'}</button>`:`<button class="seat-history" data-journal="${p.index}">${journalPerson===String(p.index)?'History Selected':'Received History ↗'}</button>`}
        </div>
      </article>`;
    }).join('')}</div>
  </section>`;
}
function currentStage(){
  const events=state.turn_events||[];
  const recent=events.length?events[events.length-1]:null;
  const actor=state.turn!==null?state.players[state.turn]:null;
  const phase=state.phase;
  let top='Next Action', summary='Card passes and reactions will appear here after the mission begins.';
  if(phase==='lobby') summary=`${state.human_joined}/${state.humans} joined · The host must deal the cards.`;
  else if(phase==='characters') summary='Review your hand and choose a character.';
  else if(phase==='reveal') summary='Reveal a card as required by the mission.';
  else if(phase==='ended') summary=state.result==='success'?'Mission Success!':'Mission Failed';
  else if(phase==='feedback') summary=`Waiting for ${escapeHTML(state.players[state.pending?.to]?.name||'recipient')} to show a Time Chip.`;
  else if(actor) summary=`It is ${playerLabel(actor)}${actor.bot?' (AI)':''}'s turn.`;
  const recentMarkup=recent?(()=>{
     const from=state.players[recent.from],to=state.players[recent.to];
     const card=recent.face_up && recent.card ? {id:recent.card,visible:true}:null;
     return `<div class="transfer-display"><div class="transfer-persona"><img src="${charImg(from.char)}" alt="${escapeHTML(from.name)}"/><b>${escapeHTML(from.name)}</b><small>Sender</small></div>
       <div class="transfer-middle"><div class="transfer-card-row"><span class="flow-arrow">→</span><img src="${imageFor(card)}" alt="${card?'Face-up Card':'Face-down Card'}"><span class="flow-arrow">→</span></div><small>${recent.face_up?'Face-up Card':'Card identity hidden'}</small></div>
       <div class="transfer-persona"><img src="${charImg(to.char)}" alt="${escapeHTML(to.name)}"/><b>${escapeHTML(to.name)}</b><small>Recipient</small></div>
       <div class="transfer-response"><span class="tiny-fact-label">Recipient Reaction</span>${reactionToken(recent.reaction,true)}</div></div>`;
  })():`<div class="stage-empty"><div class="stage-start">▲</div><div><b>Before the First Pass</b><p>The ▲ character holding the Starting Card takes the first turn.</p></div></div>`;
  return `<section class="stage-panel" aria-live="polite"><div class="section-top"><h2>Live Turn <span>LIVE TURN</span></h2><span class="turn-counter">Passes ${state.moves}${recent?` · #${recent.step}`:''}</span></div>
    <div class="stage-content"><div class="stage-context"><span class="stage-context-dot"></span><strong>${summary}</strong></div>${recentMarkup}</div>
    ${phase==='feedback' && state.pending?.to===state.me && state.inspect===null?'<div class="stage-hint">Choose a green or red Time Chip in Your Hand below.</div>':''}
    ${phase==='turn' && actor && !actor.bot && actor.index!==state.me?'<div class="stage-hint">The card pass will appear here when that player takes their turn.</div>':''}
    ${phase==='ended'?`<div class="stage-result ${state.result==='success'?'win':'lose'}">${escapeHTML(state.reason)}</div>`:''}
  </section>`;
}
function aiTurnActionPanel(){
 // AI turn controls are deliberately separate from the player's hand/action bar.
 // Inspection tabs must never be able to advance a turn.
 if(state.phase!=='turn' || !state.ai_waiting || state.inspect!==null) return '';
 const actor=state.players[state.turn];
 if(!actor || !actor.bot) return '';
 return `<section class="journal-ai-action" aria-label="AI Turn Sequence">
   <div class="journal-ai-header"><span class="journal-ai-indicator" aria-hidden="true">●</span><span>AI Turn · ${escapeHTML(actor.symbol||'')} ${escapeHTML(actor.name)}</span></div>
   <button class="btn primary journal-ai-button" type="button" data-do="advance_ai">▶ Advance AI Turn <small>One turn at a time</small></button>
 </section>`;
}
function journalPanel(){
 const ev=state.turn_events||[];
 const selected=journalPerson==='all'?ev:ev.filter(e=>e.to===Number(journalPerson));
 const chronological=selected.slice().reverse();
 return `<aside class="journal-panel" aria-label="Deduction History"><div class="journal-top"><div><h2>Deduction History</h2><span>DEDUCTION HISTORY · ${ev.length} events</span></div><span class="history-symbol">⌕</span></div>
   <div class="journal-filters" role="group" aria-label="Filter received cards">
     <button data-journal="all" class="${journalPerson==='all'?'active':''}">All</button>
     ${state.players.filter(p=>p.char!==null).map(p=>`<button data-journal="${p.index}" class="${journalPerson===String(p.index)?'active':''}">${escapeHTML(p.symbol)} ${escapeHTML(p.name)}</button>`).join('')}
   </div>
   <p class="journal-explainer">${journalPerson==='all'?'All passes · Newest first':`${escapeHTML(state.players[Number(journalPerson)]?.name||'selected player')} received cards & reactions · Newest first`}</p>
   <div class="journal-scroll" id="journal-scroll" tabindex="0" aria-label="Turn history">
     ${chronological.length?chronological.map(e=>{
       const f=state.players[e.from],t=state.players[e.to];
       const card=e.face_up&&e.card?{id:e.card,visible:true}:null;
       return `<article class="journal-event"><div class="event-number">#${String(e.step).padStart(2,'0')}</div><div class="event-main"><div class="event-route"><b>${escapeHTML(f.symbol||'')}${escapeHTML(f.name)}</b><span>→</span><b>${escapeHTML(t.symbol||'')}${escapeHTML(t.name)}</b></div><div class="event-sub">${e.face_up?'Face-up pass':'Face-down pass'}</div></div><img class="journal-card-img" src="${imageFor(card)}" alt="${card?'Face-up Card':'Face-down Card'}">${reactionToken(e.reaction)}</article>`;
     }).join(''):`<div class="journal-empty">${journalPerson==='all'?'No passes recorded yet.':'No cards received by this player yet.'}<small>Only information made public during play is shown.</small></div>`}
   </div>
   <div class="journal-foot"><span class="legend-item"><i class="legend-chip green"></i> Needed</span><span class="legend-item"><i class="legend-chip red"></i> Not Needed</span><span class="legend-item"><i class="legend-card"></i> Face down</span></div>
 </aside>`;
}
function playerHandDock(){
 const p=state.players[state.me],readOnly=state.inspect!==null||p.bot;
 const isMyTurn=state.phase==='turn'&&state.turn===state.me&&!readOnly;
 const reveal=state.phase==='reveal'&&!p.revealed&&!readOnly;
 const choosing=isMyTurn||reveal;
 let instruction='Review your cards';
 if(state.phase==='turn')instruction=isMyTurn?'① Choose a card → ② Choose a recipient → ③ Pass':'Another player is taking their turn';
 if(state.phase==='characters')instruction='Review your hand and choose a character';
 if(state.phase==='reveal')instruction=p.revealed?'Waiting for other players to reveal their cards':'Choose 1 card to reveal';
 if(state.phase==='feedback')instruction=state.pending?.to===state.me?'Respond to the received card':'Waiting for the recipient’s reaction';
 if(state.phase==='ended')instruction='Mission Result';
 const hand=p.hand.map(c=>{
   if(!c.id)return '';
   const enabled=choosing && (state.phase!=='reveal'||c.id!=='start');
   return `<button class="hand-item ${selectedCard===c.id?'picked':''}" data-card="${escapeHTML(c.id)}" ${enabled?'':'disabled'} aria-pressed="${selectedCard===c.id}" title="${c.public?'Face up':''}"><img src="${imageFor(c)}" alt="${escapeHTML(c.id)}"/>${c.public?'<span class="known-card">PUBLIC</span>':''}</button>`;
 }).join('');
 let actions='';
 if(state.phase==='lobby'){
   const ready=state.human_joined===state.humans;
   actions=state.is_owner?`<button class="btn primary dock-button" data-do="begin" ${ready?'':'disabled'}>Deal Cards & Start →</button>`:`<span class="dock-wait">Waiting for the host to start the game.</span>`;
 } else if(state.phase==='characters'){
   const taken=state.players.filter(x=>x.char!==null).map(x=>x.char);
   actions=p.char===null&&!readOnly?`<div class="char-row">${[0,1,2,3].map(x=>`<button class="char-tile" data-char="${x}" ${taken.includes(x)?'disabled':''}><img src="${charImg(x)}" alt="${['▲','●','■','★'][x]}"><span>${['▲','●','■','★'][x]}</span></button>`).join('')}</div>`:`<span class="dock-wait">Waiting for other players to choose characters.</span>`;
 } else if(state.phase==='reveal'){
   actions=reveal?`<button class="btn primary dock-button" data-do="reveal" ${selectedCard?'':'disabled'}>Reveal Selected Card</button>`:`<span class="dock-wait">Card revealed · Waiting</span>`;
 } else if(state.phase==='feedback'&&state.pending?.to===state.me&&!readOnly){
   actions=`<div class="feedback-actions"><button class="feedback-button green" data-feedback="true"><span>✓</span><b>Green Chip</b><small>Needed</small></button><button class="feedback-button red" data-feedback="false"><span>×</span><b>Red Chip</b><small>Not Needed</small></button></div>`;
 } else if(isMyTurn){
   actions=`<div class="selected-destination">${selectedCard?`Selected card: <b>${escapeHTML(selectedCard==='start'?'Starting Card':selectedCard)}</b>`:'Select a card'}<br>${selectedTarget!==null?`Recipient: <b>${escapeHTML(state.players[selectedTarget].name)}</b>`:'Select the receiving player above'}</div><button class="btn primary dock-button" data-do="pass" ${selectedCard&&selectedTarget!==null?'':'disabled'}>Pass Card →</button>`;
 } else if(state.phase==='ended'){
   const success=state.result==='success';
   actions=state.is_owner?`<button class="btn primary dock-button" data-do="${success&&state.mission<5?'next':'retry'}">${success&&state.mission<5?'Next Seoul Mission →':success?'Play Mission Again':'Retry Mission →'}</button>`:`<span class="dock-wait">Waiting for the host to continue.</span>`;
 } else if(state.phase==='turn' && state.ai_waiting && !readOnly && state.inspect===null){
   actions=`<span class="dock-wait">It is an AI turn. Use the <b>Advance AI Turn</b> button above Deduction History to advance one turn at a time.</span>`;
 } else if(state.phase==='feedback'){
   actions=`<span class="dock-wait">${escapeHTML(state.players[state.pending?.to]?.name||'Recipient')} is choosing a reaction.</span>`;
 } else {
   actions=`<span class="dock-wait">${state.inspect!==null?'Inspection mode · Read only':'It is not your turn.'}</span>`;
 }
 return `<section class="hand-dock" aria-label="Your hand and game controls">
   <div class="dock-head"><div><h2>Your Hand <span>${p.hand_size} cards</span></h2><p>${instruction}</p></div><div class="dock-pills"><span class="dock-seat">${escapeHTML(p.symbol||'○')} ${escapeHTML(p.name)}</span>${p.chips!==null?`<span class="dock-chip">◷ ${p.chips}</span>`:''}</div></div>
   <div class="dock-body"><div class="dock-hand">${hand||'<div class="no-hand">Waiting for the game to start.</div>'}</div><div class="dock-controls">${actions}</div></div>
 </section>`;
}
function overlayPanel(){
 if(!overlay)return '';
 const n=String(state.mission).padStart(2,'0');
 const links=state.debug&&state.is_owner?`<section class="debug-sub"><h3>Developer Test · Player Views</h3><p>Inspection mode lets the host see private hands. Do not use it in a real game.</p><div class="debug-actions">${state.players.map(p=>`<a target="_blank" rel="noopener" href="/?room=${encodeURIComponent(state.code)}&inspect=${p.index}">${escapeHTML(p.name)} ↗</a>`).join('')}</div></section>`:'';
 let content='';
 if(overlay==='leave'){
  content=`<div class="leave-confirm"><h3>Leave this game?</h3><p>Your current play session will be closed on this device. You will return to the home screen.</p><p class="help-warning">Other players may remain in the room. This does not end the room for everyone.</p><div class="leave-actions"><button class="btn ghost" data-overlay="close">Stay in Game</button><button class="btn warn" data-do="confirm_leave">Leave Game</button></div></div>`;
 }else if(overlay==='mission'){
  content=`<div class="mission-view-tabs"><button data-side="rules" class="${missionSide==='rules'?'active':''}">Mission Rules</button><button data-side="story" class="${missionSide==='story'?'active':''}">Mission Story</button></div>
  <img class="mission-full" src="${assets(`seoul_${n}_${missionSide==='rules'?'back':'front'}.png`)}" alt="Seoul ${n} mission ${missionSide}"/><p class="modal-rule">${missionSide==='rules'?ruleShort():'The story is shown on the card above.'}</p>`;
 }else{
  content=`<div class="help-content"><h3>Game Objective</h3><p>Work together to complete four Information Sets, one per color, each containing cards 1–5. Players must not reveal the contents of their hands through conversation.</p>
  <h3>Turn Sequence</h3><ol><li>The ▲ character holding the Starting Card takes the first turn.</li><li>Pass one card to another active player, face down unless a mission rule requires face-up passing.</li><li>The recipient spends a Time Chip, showing green if the card is needed or red if it is not.</li><li>The recipient takes the next turn.</li><li>When a player completes a color set, they reveal their cards and leave the mission.</li><li>All four sets completed: success. Running out of Time Chips before completing a set: failure.</li></ol>
  <h3>Deduction History</h3><p>Only cards that were face up during play are identified. Face-down cards remain hidden. Select a character to filter their received-card history.</p>
  <p class="help-warning">Provisional rule: receiving the Starting Card costs one red Time Chip. This exception is not explicitly addressed in the supplied rulebook.</p>${links}</div>`;
 }
 return `<div class="modal-shade" data-backdrop="true"><section class="modal-dialog" role="dialog" aria-modal="true" aria-label="${overlay==='mission'?'Mission Card':overlay==='leave'?'Leave Game':'Game Rules'}"><header class="modal-header"><div><span class="eyebrow">S.O.R.T. 5</span><h2>${overlay==='mission'?`SEOUL #${n}`:overlay==='leave'?'Leave Game':'Game Rules'}</h2></div><button class="modal-close" data-overlay="close" aria-label="Close">✕</button></header>${content}</section></div>`;
}
function render(){
 if(!state){welcome();return;}
 const journalScroll=document.getElementById('journal-scroll');
 const scrollY=journalScroll?journalScroll.scrollTop:0;
 if(journalPerson!=='all' && (!state.players[Number(journalPerson)]))journalPerson='all';
 app.innerHTML=`<main class="main game-main">${topBar()}${errorText?`<div class="alert" role="alert">${escapeHTML(errorText)}</div>`:''}${missionRibbon()}
   ${state.inspect!==null?'<div class="inspect-banner">TEST MODE · Viewing another player’s screen. Controls are disabled.</div>':''}
   <div class="play-grid"><div class="board-column">${playerBoard()}${currentStage()}</div><div class="journal-column">${aiTurnActionPanel()}${journalPanel()}</div></div>${playerHandDock()}
   <footer class="foot">SORT 5 · SEOUL PLAYTEST v0.8 · Private hands are kept separate by the server.</footer>
   ${overlayPanel()}</main>`;
 if(journalScroll && document.getElementById('journal-scroll'))document.getElementById('journal-scroll').scrollTop=scrollY;
 document.querySelectorAll('[data-card]').forEach(b=>b.addEventListener('click',()=>{selectedCard=b.dataset.card;selectedTarget=null;render();}));
 document.querySelectorAll('[data-target]').forEach(b=>b.addEventListener('click',()=>{selectedTarget=Number(b.dataset.target);render();}));
 document.querySelectorAll('[data-char]').forEach(b=>b.addEventListener('click',()=>action('character',{character:Number(b.dataset.char)})));
 document.querySelectorAll('[data-feedback]').forEach(b=>b.addEventListener('click',()=>action('feedback',{positive:b.dataset.feedback==='true'})));
 document.querySelectorAll('[data-journal]').forEach(b=>b.addEventListener('click',()=>{journalPerson=b.dataset.journal;render();}));
 document.querySelectorAll('[data-overlay]').forEach(b=>b.addEventListener('click',()=>{overlay=b.dataset.overlay==='close'?null:b.dataset.overlay;render();}));
 document.querySelectorAll('[data-side]').forEach(b=>b.addEventListener('click',()=>{missionSide=b.dataset.side;render();}));
 document.querySelector('[data-backdrop]')?.addEventListener('click',e=>{if(e.target===e.currentTarget){overlay=null;render();}});
 document.querySelectorAll('[data-do]').forEach(b=>b.addEventListener('click',async()=>{
   const a=b.dataset.do;
   if(a==='leave'){overlay='leave';render();}
   else if(a==='confirm_leave'){
     const currentCode=credentials?.code;
     credentials=null;state=null;overlay=null;errorText='';selectedCard=null;selectedTarget=null;journalPerson='all';lastSnapshotSignature='';
     sessionStorage.removeItem('sort5_credentials');
     if(currentCode)localStorage.removeItem(`sort5_debug_${currentCode}`);
     window.history.replaceState({},'',window.location.pathname);
     render();
   }
   else if(a==='advance_ai'){await action('advance_ai');}
   else if(a==='copy'){
     const invite=`${location.origin}/?room=${state.code}`;
     try{await navigator.clipboard.writeText(invite);b.textContent='Copied ✓';}catch{window.prompt('Copy invite link',invite)}
   }else if(['begin','retry','next'].includes(a)){
     if(a==='retry'||a==='next')journalPerson='all';
     await action(a);
   }else if(a==='reveal'&&selectedCard){await action('reveal',{card:selectedCard});}
   else if(a==='pass'&&selectedCard&&selectedTarget!==null){await action('pass',{card:selectedCard,target:selectedTarget});}
 }));
}
function initialize(){
 try{const c=JSON.parse(sessionStorage.getItem('sort5_credentials'));if(c?.token&&(!qRoom||qRoom===c.code))credentials=c;}catch{}
 if(!credentials&&qRoom&&INSPECT!==null){
   const ownerToken=localStorage.getItem(`sort5_debug_${qRoom}`);
   if(ownerToken)credentials={code:qRoom,token:ownerToken,debugOwner:true};
 }
 if(credentials)loadState();else render();
 document.addEventListener('keydown', e=>{if(e.key==='Escape'&&overlay){overlay=null;render();}});
 setInterval(()=>{if(credentials&&document.visibilityState==='visible')loadState();},1500);
}
initialize();
