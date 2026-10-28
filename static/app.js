const app = document.getElementById('app');
let state = null;
let selectedCard = null;
let secondOfferCard = null;
let selectedTarget = null;
let missionSide = 'rules';
let selectedHomeMission = 1;
let selectedHomeCity = 'seoul';
const CITIES = [{id:'seoul',name:'Seoul',stars:1,ready:true},{id:'berlin',name:'Berlin',stars:2,ready:true},{id:'new_york',name:'New York',stars:3,ready:true},{id:'tokyo',name:'Tokyo',stars:4,ready:true},{id:'london',name:'London',stars:5,ready:true},{id:'paris',name:'Paris',stars:6,ready:true}];
const cityLabel = city => CITIES.find(c=>c.id===city)?.name || 'Seoul';
const currentCity = () => state?.city || 'seoul';
let homeCardSide = 'story';
let errorText = '';
let polling = false;
let actionBusy = false;
let journalPerson = 'all';
let lastAnnouncementSeen = '';
let announcementVisibleUntil = 0;
let announcementTimer = null;
let historyUnlocked = false;
let historyVisible = false;
let historyWarningOpen = false;
let overlay = null;
let lastSnapshotSignature = '';
const PARAMS = new URLSearchParams(window.location.search);
const INSPECT = PARAMS.has('inspect') ? Number(PARAMS.get('inspect')) : null;
const qRoom = (PARAMS.get('room') || '').toUpperCase();
let credentials = null;
// Keep lobby input values through UI re-renders (including mission previews).
const lobbyDraft = { createName: '', joinName: '', joinCode: qRoom, humans: '1', debug: false };
function captureLobbyDraft() {
  const create = id('create-form'), join = id('join-form');
  if (create) {
    lobbyDraft.createName = create.elements.namedItem('name')?.value ?? lobbyDraft.createName;
    lobbyDraft.humans = create.elements.namedItem('humans')?.value ?? lobbyDraft.humans;
    lobbyDraft.debug = !!create.elements.namedItem('debug')?.checked;
  }
  if (join) {
    lobbyDraft.joinName = join.elements.namedItem('name')?.value ?? lobbyDraft.joinName;
    lobbyDraft.joinCode = join.elements.namedItem('code')?.value ?? lobbyDraft.joinCode;
  }
}
function bindLobbyDraft() {
  const update = () => captureLobbyDraft();
  for (const formId of ['create-form', 'join-form']) {
    const form = id(formId);
    if (form) {
      form.addEventListener('input', update);
      form.addEventListener('change', update);
    }
  }
}

const escapeHTML = (x) => String(x == null ? '' : x).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const id = x => document.getElementById(x);
const assets = file => `/static/assets/${file}`;
const cityAssetPrefix = city => city === 'new_york' ? 'newyork' : city;
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
    if(old && (old.phase !== next.phase || old.turn !== next.turn || old.mission !== next.mission)) { selectedCard = null;secondOfferCard=null;selectedTarget=null; }
    if(old && old.mission !== next.mission) {historyUnlocked=false;historyVisible=false;historyWarningOpen=false;journalPerson='all';}
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
    selectedCard=null;secondOfferCard=null;selectedTarget=null;errorText='';
    render();
    if(INSPECT!==null) await loadState();
  }catch(e){errorText=e.message;render();}
  finally{actionBusy=false;}
}
function topBar(){
  const subtitle = state ? `MISSION // ${cityLabel(currentCity()).toUpperCase()} 0${state.mission}` : 'ONLINE CO-OP PLAYTEST';
  return `<header class="brandbar"><div class="brand">S.O.R.T. <b>5</b><small>${subtitle}</small></div><div class="header-right">${state?`<span class="chip">${state.humans} human · ${4-state.humans} AI</span><button type="button" class="chip code" data-do="copy">ROOM ${escapeHTML(state.code)} ⧉</button>${state.is_owner?'<button type="button" class="chip retry-top-btn" data-do="retry_confirm">↻ Retry</button>':''}<button type="button" class="chip leave-btn" data-do="leave">Leave Game</button>`:''}</div></header>`;
}
function missionImage(mission,side,city=selectedHomeCity){
  return assets(`${cityAssetPrefix(city)}_${String(mission).padStart(2,'0')}_${side==='story'?'front':'back'}.png`);
}
function homePreview(){
  return `<div class="preview-title"><strong>${cityLabel(selectedHomeCity).toUpperCase()} #${String(selectedHomeMission).padStart(2,'0')}</strong><span>Preview before creating a room</span></div>
    <div class="preview-tabs"><button type="button" data-home-side="story" class="${homeCardSide==='story'?'active':''}">Story</button><button type="button" data-home-side="rules" class="${homeCardSide==='rules'?'active':''}">Rules</button></div>
    <button type="button" class="home-card-open" data-home-open="true" title="Click to enlarge ${homeCardSide} card"><img src="${missionImage(selectedHomeMission,homeCardSide,selectedHomeCity)}" alt="${cityLabel(selectedHomeCity)} mission ${selectedHomeMission} ${homeCardSide} card" loading="lazy"><span>Click card to enlarge ↗</span></button>`;
}
function wireHomePreview(){
  document.querySelectorAll('[data-home-side]').forEach(b=>b.addEventListener('click',()=>{homeCardSide=b.dataset.homeSide;renderHomePreview();}));
  document.querySelector('[data-home-open]')?.addEventListener('click',()=>openMissionLightbox(selectedHomeMission,homeCardSide,selectedHomeCity));
}
function renderHomePreview(){
  const el=id('home-mission-preview');if(!el)return;
  el.innerHTML=homePreview();wireHomePreview();
}
function openMissionLightbox(mission,side,city=selectedHomeCity){
  const existing=id('mission-lightbox');if(existing)existing.remove();
  const shade=document.createElement('div');shade.id='mission-lightbox';shade.className='mission-lightbox';
  shade.setAttribute('role','presentation');
  shade.innerHTML=`<div class="mission-lightbox-dialog" role="dialog" aria-modal="true" aria-label="${cityLabel(city)} Mission ${mission} ${side} card">
    <header><strong>${cityLabel(city).toUpperCase()} #${String(mission).padStart(2,'0')}</strong><div><button type="button" data-lightbox-side="story" class="${side==='story'?'active':''}">Story</button><button type="button" data-lightbox-side="rules" class="${side==='rules'?'active':''}">Rules</button><button type="button" class="lightbox-close" aria-label="Close">✕</button></div></header>
    <img src="${missionImage(mission,side,city)}" alt="${cityLabel(city)} mission ${mission} ${side} card" />
    <p>Click outside or press Escape to close.</p></div>`;
  document.body.appendChild(shade);
  shade.addEventListener('click',e=>{if(e.target===shade || e.target.closest('.lightbox-close'))shade.remove();});
  shade.querySelectorAll('[data-lightbox-side]').forEach(b=>b.addEventListener('click',()=>openMissionLightbox(mission,b.dataset.lightboxSide,city)));
  shade.querySelector('.lightbox-close').focus();
}
function welcome(){
  captureLobbyDraft();
  app.innerHTML = `<div class="main welcome">${topBar()}<section class="hero"><div class="eyebrow">Happy Baobab / Digital Playtest</div><h1>Mission <span>S.O.R.T. 5</span></h1><p>Exchange information without speaking freely. Read each other's reactions, manage your Time Chips, and complete all four Information Sets.</p></section>
  <div class="welcome-grid"><section class="panel"><h2>Create a game room</h2><form id="create-form">
    <div class="field"><label>Your name</label><input name="name" maxlength="32" placeholder="e.g. Martin" value="${escapeHTML(lobbyDraft.createName)}" required /></div>
    <div class="field"><label for="home-city">City</label><select id="home-city" name="city" aria-label="Select city">${CITIES.map(c=>`<option value="${c.id}" ${c.id===selectedHomeCity?'selected':''} ${!c.ready?'disabled':''}>${c.name} · ${'★'.repeat(c.stars)} (${c.stars}/6)${c.ready?'':' · Artwork pending'}</option>`).join('')}</select><label id="mission-picker-label" style="margin-top:10px">Mission</label><input type="hidden" id="home-mission" name="mission" value="${selectedHomeMission}" /><div class="mission-pick-buttons" role="group" aria-labelledby="mission-picker-label">${[1,2,3,4,5].map(n=>`<button type="button" class="mission-pick ${selectedHomeMission===n?'active':''}" data-pick-mission="${n}" aria-pressed="${selectedHomeMission===n}">#0${n}</button>`).join('')}</div></div>
    <div id="home-mission-preview" class="home-mission-preview">${homePreview()}</div><p class="small-note" id="city-dev-note" style="margin:4px 0 12px">${'Development playtest: some city-specific rules are still under review.'}</p>
    <div class="field"><label>Human players</label><select name="humans"><option value="1" ${lobbyDraft.humans==='1'?'selected':''}>1 human + 3 AI</option><option value="2" ${lobbyDraft.humans==='2'?'selected':''}>2 humans + 2 AI</option><option value="3" ${lobbyDraft.humans==='3'?'selected':''}>3 humans + 1 AI</option><option value="4" ${lobbyDraft.humans==='4'?'selected':''}>4 humans (online room)</option></select></div>
    
    <button class="btn primary full" type="submit">Create room</button></form>
    <p class="small-note">Each human connects in their own browser. One player and three AI work immediately; Share the invitation link so everyone can join from their own device.</p></section>
  <section class="panel"><h2>Join an existing room</h2><form id="join-form">
    <div class="field"><label>Your name</label><input name="name" maxlength="32" placeholder="Your nickname" value="${escapeHTML(lobbyDraft.joinName)}" required /></div>
    <div class="field"><label>Room code</label><input name="code" id="join-code" value="${escapeHTML(lobbyDraft.joinCode)}" maxlength="6" placeholder="6-digit code" required /></div>
    <button class="btn full" type="submit">Join room</button></form>
    <p class="mini-title" style="margin-top:29px">How it works</p>
    <div class="status"><div class="status-line"><span>Information Cards</span>20 (4 colors × 1–5)</div><div class="status-line"><span>Starting Card</span>1</div><div class="status-line"><span>Mission Cards</span>Seoul, Berlin, New York &amp; London #01–05</div><div class="status-line"><span>Goal</span>Complete 4 color sets</div></div></section></div>
  <div class="rule-strip"><span>Hidden hands by default</span><span>Face-up card exceptions</span><span>Server-checked turns</span><span>City mission previews</span></div></div>`;
  id('home-city').addEventListener('change',e=>{ selectedHomeCity=e.target.value; selectedHomeMission=1; id('home-mission').value='1'; document.querySelectorAll('[data-pick-mission]').forEach(b=>{const active=Number(b.dataset.pickMission)===1;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));}); renderHomePreview(); id('city-dev-note').textContent= 'Development playtest: some city-specific rules are still under review.'; });
  document.querySelectorAll('[data-pick-mission]').forEach(button=>button.addEventListener('click',()=>{
    selectedHomeMission=Number(button.dataset.pickMission);
    id('home-mission').value=String(selectedHomeMission);
    document.querySelectorAll('[data-pick-mission]').forEach(b=>{
      const active=Number(b.dataset.pickMission)===selectedHomeMission;
      b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));
    });
    renderHomePreview();
  }));
  wireHomePreview();
  bindLobbyDraft();
  id('create-form').onsubmit = async (e)=>{
    e.preventDefault();const f=new FormData(e.target);
    try{const ans=await request('/api/new',{name:f.get('name').trim(),city:f.get('city'),mission:Number(f.get('mission')),humans:Number(f.get('humans')),debug:false});store({...ans,debugOwner:false});await loadState();}catch(ex){alert(ex.message);}
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
  const berlin = {
    1:'● must complete an Information Set first.',
    2:'★ may only pass cards to the player on their left.',
    3:'★ passes 2 cards; recipient selects 1 and returns the other.',
    4:'● must finish first; ■ may only pass to the left.',
    5:'All players announce their count of the received card color; use only the negative chip face.'
  };
  const seoul = {
    1:'All players pass cards face up.',
    2:'Before the mission, each player reveals 1 card. Revealed cards stay face up.',
    3:'Before looking at their hand, each player randomly reveals 1 card. Revealed cards stay face up.',
    4:'The ● character passes cards face up.',
    5:'No additional mission rules. Follow the basic rules.'
  };
  return state?.rules || ((currentCity()==='berlin'?berlin:seoul)[state.mission] || 'See Mission Rules card.');
}
function missionCardPanel(){
  const n=String(state.mission).padStart(2,'0');
  return `<section class="mission-card-side" aria-label="Current mission cards">
    <header class="mission-card-heading"><strong>${state.phase==='lobby'?'SELECTED MISSION':'MISSION CARDS'}</strong><span>${cityLabel(currentCity()).toUpperCase()} #${n}</span></header>
    <div class="mission-card-grid mission-card-vertical">
      <button type="button" class="mission-card-thumb" data-open-mission="story" title="Enlarge mission story"><img src="${missionImage(state.mission,'story',currentCity())}" alt="Mission story card" loading="lazy"/><span>Story <b>↗</b></span></button>
      <button type="button" class="mission-card-thumb" data-open-mission="rules" title="Enlarge mission rules"><img src="${missionImage(state.mission,'rules',currentCity())}" alt="Mission rules card" loading="lazy"/><span>Rules <b>↗</b></span></button>
    </div>
  </section>`;
}
function missionRibbon(){
  const n=String(state.mission).padStart(2,'0');
  return `<section class="mission-ribbon" aria-label="Current mission">
    <div class="ribbon-title"><span class="ribbon-city">${cityLabel(currentCity()).toUpperCase()}</span><strong>#${n}</strong><span class="ribbon-star">${"★".repeat(CITIES.find(c=>c.id===currentCity())?.stars||1)}</span></div>
    <div class="ribbon-rule"><span class="rule-kicker">GOAL</span><strong>${state.city==='new_york'&&state.mission===3?'Complete 2 Information Sets':'Complete 4 Information Sets'}</strong>${state.shared_chips!==null?`<span class="shared-chip-counter">Shared Time Chips: ${state.shared_chips}</span>`:''}</div>
    <button class="secondary-pill" data-overlay="mission" title="View mission card">Mission Card <span>↗</span></button>
    <button class="secondary-pill" data-overlay="help" title="Basic game rules">Help <span>?</span></button>
  </section>`;
}
function playerBoard(){
  const me=state.me;
  const needsTwo=state.allowed_actions?.includes('offer');
  const canTarget=state.inspect===null && state.phase==='turn' && state.turn===me && selectedCard && (!needsTwo || secondOfferCard);
  return `<section class="seat-board" aria-label="player status"><div class="section-top"><h2>Team Status <span>TEAM STATUS</span></h2><span class="tiny-label">Select a card below, then choose a teammate here</span></div>
    <div class="table-seat-grid">${state.players.map(p=>{
      const targetable=canTarget&&p.index!==me&&!p.done&&(state.legal_targets||[]).includes(p.index);
      const active=state.turn===p.index && ['turn','feedback'].includes(state.phase);
      // View-relative compass: viewer bottom, left and right are actual physical neighbors.
      const mySeat=state.players[me].seat ?? me;
      const hisSeat=p.seat ?? p.index;
      const offset=(hisSeat-mySeat+4)%4;
      const position=['south','east','north','west'][offset];
      const bits=['seat-card','table-seat-'+position,p.is_me?'my-seat':'', active?'seat-active':'',p.done?'seat-done':'',targetable?'seat-targetable':'',selectedTarget===p.index?'seat-selected':''].join(' ');
      const cards=p.hand.map(c=>`<img class="seat-smallcard ${c.visible?'face-visible':''}" src="${imageFor(c)}" alt="${c.visible?'Face-up Card':'Face-down Card'}" title="${c.public?'Face-up Card':c.visible?'Your Hand':'Hidden Card'}" />`).join('');
      const usedChipEvents=(state.turn_events||[]).filter(e=>e.to===p.index && (e.reaction==='positive'||e.reaction==='negative'));
      const chipHistory=usedChipEvents.map(e=>`<span class="used-chip ${e.reaction==='positive'?'positive':'negative'}" title="Turn ${e.step}: ${e.reaction==='positive'?'Green — Needed':'Red — Not needed'}${e.announced_count!==undefined?` · Announced ${e.announced_count}`:''}" aria-label="Turn ${e.step}: ${e.reaction==='positive'?'Green — Needed':'Red — Not needed'}">${e.reaction==='positive'?'✓':'×'}</span>`).join('');
      const chips=p.chips===null?'Preparing':state.shared_chips!==null?'Shared':`<span class="chip-value">${p.chips}</span>`;
      return `<article class="${bits}">
        <div class="seat-top">
          <img class="seat-avatar" src="${p.char===null?assets('cards_back.png'):charImg(p.char)}" alt="${escapeHTML(p.symbol||'Choose a character')}" />
          <div class="seat-identity"><div class="seat-name">${escapeHTML(p.name)}${p.is_me?'<span class="you-dot">YOU</span>':''}${p.bot?'<span class="bot-dot">AI</span>':''}</div><div class="seat-sub">${escapeHTML(p.symbol||'—')} ${p.char===null?'Choose a character':''}</div></div>
          ${active?'<span class="turn-dot">TURN</span>':p.done?'<span class="done-dot">DONE</span>':''}
        </div>
        <div class="seat-facts"><span><span class="tiny-fact-label">TIME</span> ${chips}</span><span><span class="tiny-fact-label">CARDS</span> <b>${p.hand_size}</b> cards</span>${p.held_face_down?'<span class="held-card-indicator" title="One unknown Information Card held aside">▣ 1 SEALED</span>':''}</div>
        <div class="seat-hand" aria-label="${escapeHTML(p.name)} public cards and hidden hand">${cards||'<span class="empty-seat">Set complete · No cards left</span>'}</div>
        <div class="seat-chip-history" aria-label="${escapeHTML(p.name)} Time Chip reactions, oldest to newest"><span class="chip-history-label">USED CHIPS</span><div class="used-chip-list">${chipHistory||'<span class="chip-history-empty">None yet</span>'}</div></div>
        <div class="seat-footer">
          ${targetable?(selectedTarget===p.index?`<button class="seat-send seat-confirm-pass" data-do="${state.allowed_actions?.includes('offer')?'offer':'pass'}" title="Confirm card transfer to ${escapeHTML(p.name)}">${state.allowed_actions?.includes('offer')?'Offer 2 Cards →':'Pass Card →'}</button>`:`<button class="seat-send" data-target="${p.index}">Select Recipient →</button>`):!historyVisible?`<span class="seat-hint">${p.done?'Set completed':canTarget&&p.index!==me?'Not a legal recipient':'Check teammates’ reactions'}</span>`:`<button class="seat-history" data-journal="${p.index}">Received History ↗</button>`}
        </div>
      </article>`;
    }).join('')}<div class="table-center" aria-hidden="true"><span>S.O.R.T. 5</span><small>TABLE</small></div></div>
  </section>`;
}
function offerChoicePanel(){
 if(state.phase!=='offer_choice' || !state.offer) return '';
 const recipient=state.offer.to===state.me && state.inspect===null;
 const source=state.players[state.offer.from];
 if(!recipient)return `<section class="offer-choice-panel"><strong>Two-card offer in progress</strong><p>Waiting for ${escapeHTML(state.players[state.offer.to]?.name||'recipient')} to choose one of the offered cards.</p></section>`;
 return `<section class="offer-choice-panel"><strong>Choose One Card</strong><p>${escapeHTML(source.name)} offered 2 cards. ${state.city==='berlin' && state.mission===3?'Look at both cards and choose one.':'Choose one of the offered cards.'} The other returns to the sender.</p>
   <div class="offer-options">${[0,1].map(i=>{
     const card=state.offer.public_cards?.[i];
     return `<button type="button" class="offer-option" data-offer-choice="${i}"><img src="${imageFor(card?{id:card,visible:true}:null)}" alt="Offered card ${i+1}" /><span>Choose Card ${i+1}</span></button>`;
   }).join('')}</div></section>`;
}
function initialPassPanel(){
  if(state.phase!=='initial_pass')return '';
  const chosen=!!state.initial_pass_submitted;
  const isBot=state.players[state.me]?.bot;
  return `<div class="special-step"><strong>Simultaneous Initial Pass — New York #02</strong><p>Each player chooses one Information Card to pass right. Your choice remains secret until all four players have submitted.</p>
    <div class="special-ready">${state.initial_pass_ready} of 4 choices submitted</div>
    ${chosen?'<p>✓ Your card is locked in. Waiting for the remaining players.</p>':`<p>Choose a card from Your Hand, then confirm below.</p><button class="btn primary" type="button" data-do="initial_pass" ${selectedCard&&!isBot?'':'disabled'}>Pass Selected Card Right</button>`}
  </div>`;
}
function guessNumberPanel(){
  if(state.phase!=='guess')return '';
  const recipient=state.pending?.to===state.me && state.inspect===null;
  if(!recipient)return `<div class="special-step"><strong>Number Guess — London #04</strong><p>Waiting for ${escapeHTML(state.players[state.pending?.to]?.name||'the recipient')} to guess the number before viewing the card.</p></div>`;
  return `<div class="special-step"><strong>Guess the Number — London #04</strong><p>A card was sent to you. Choose its number <b>before looking at it</b>. A wrong guess costs one additional shared Time Chip.</p><div class="guess-options">${[1,2,3,4,5].map(n=>`<button type="button" data-guess="${n}">${n}</button>`).join('')}</div></div>`;
}
function announcementBanner(){
 if(currentCity()!=='berlin' || state.mission!==5)return '';
 const events=state.turn_events||[];
 const recent=[...events].reverse().find(e=>e.announced_count!==undefined && e.announced_at);
 if(!recent)return '';
 const key=`${state.code}:${currentCity()}:${state.mission}:${recent.step}:${recent.announced_at}`;
 if(lastAnnouncementSeen!==key){
   lastAnnouncementSeen=key;
   // Server timestamp prevents older declarations reappearing after refresh/rejoin.
   announcementVisibleUntil=Math.min(Date.now()+3000, recent.announced_at*1000+5000);
   if(announcementTimer)clearTimeout(announcementTimer);
   const delay=announcementVisibleUntil-Date.now();
   if(delay>0)announcementTimer=setTimeout(()=>{announcementTimer=null;render();},delay+50);
 }
 if(Date.now()>=announcementVisibleUntil)return '';
 const recipient=state.players[recent.to];
 return `<aside class="berlin-count-banner" role="status" aria-live="assertive"><span>BERLIN #05 · ANNOUNCEMENT</span><strong>${escapeHTML(recipient?.name||'Recipient')} declares <b>${recent.announced_count}</b></strong><small>Cards of the received color · Red Chip</small></aside>`;
}
function countAnnouncementPanel(){
 if(currentCity()!=='berlin'||state.mission!==5||state.phase!=='announce')return '';
 const mine=state.pending?.to===state.me && state.inspect===null;
 if(!mine)return `<div class="special-step"><strong>Color Count Announcement</strong><p>Waiting for the recipient to announce the number of cards.</p></div>`;
 return `<div class="special-step berlin-announce-confirm"><strong>Declare Your Card Count</strong><p>Including the card you just received, you now hold this many cards of that color:</p><strong class="berlin-declared-count">${state.announcement_count}</strong><p>Everyone will hear the number, but not the color. You must use a red chip.</p><button class="btn primary" type="button" data-do="announce">Announce ${state.announcement_count} →</button></div>`;
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
  else if(phase==='initial_pass') summary='Each player chooses one hidden card to pass right simultaneously.';
  else if(phase==='guess') summary='Recipient guesses the card number before seeing the card.';
  else if(phase==='offer_choice') summary='Waiting for the recipient to select 1 of 2 offered cards.';
  else if(phase==='announce') summary=`Waiting for ${escapeHTML(state.players[state.pending?.to]?.name||'recipient')} to announce their count.`;
  else if(phase==='feedback') summary=`Waiting for ${escapeHTML(state.players[state.pending?.to]?.name||'recipient')} to show a Time Chip.`;
  else if(actor) summary=`It is ${playerLabel(actor)}${actor.bot?' (AI)':''}'s turn.`;
  const recentMarkup=recent?(()=>{
     const from=state.players[recent.from],to=state.players[recent.to];
     const card=recent.face_up && recent.card ? {id:recent.card,visible:true}:null;
     return `<div class="transfer-display"><div class="transfer-persona"><img src="${charImg(from.char)}" alt="${escapeHTML(from.name)}"/><b>${escapeHTML(from.name)}</b><small>Sender</small></div>
       <div class="transfer-middle"><div class="transfer-card-row"><span class="flow-arrow">→</span><img src="${imageFor(card)}" alt="${card?'Face-up Card':'Face-down Card'}"><span class="flow-arrow">→</span></div><small>${recent.face_up?'Face-up Card':'Card identity hidden'}</small></div>
       <div class="transfer-persona"><img src="${charImg(to.char)}" alt="${escapeHTML(to.name)}"/><b>${escapeHTML(to.name)}</b><small>Recipient</small></div>
       <div class="transfer-response"><span class="tiny-fact-label">Recipient Reaction</span>${reactionToken(recent.reaction,true)}${recent.announced_count!==undefined?`<small>Declared: ${recent.announced_count} cards of the received color</small>`:''}${recent.guessed_number?`<small>Guessed ${recent.guessed_number} · ${recent.guess_wrong?'Wrong (+1 chip)':'Correct'}</small>`:''}</div></div>`;
  })():`<div class="stage-empty"><div class="stage-start">▲</div><div><b>Before the First Pass</b><p>The ▲ character holding the Starting Card takes the first turn.</p></div></div>`;
  return `<section class="stage-panel" aria-live="polite"><div class="section-top"><h2>Live Turn <span>LIVE TURN</span></h2><span class="turn-counter">Passes ${state.moves}${recent?` · #${recent.step}`:''}</span></div>
    <div class="stage-content"><div class="stage-context"><span class="stage-context-dot"></span><strong>${summary}</strong></div>${recentMarkup}${offerChoicePanel()}${initialPassPanel()}${guessNumberPanel()}${countAnnouncementPanel()}</div>
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
 if(!historyVisible) return `<section class="history-locked"><div><span class="history-lock-icon">⌁</span><strong>Deduction History</strong><small>Hidden for the original memory-based experience.</small></div><button type="button" class="history-unlock" data-history-toggle="show">${historyUnlocked?'Show History':'Unlock History'}</button></section>`;
 const ev=state.turn_events||[];
 const selected=journalPerson==='all'?ev:ev.filter(e=>e.to===Number(journalPerson));
 const chronological=selected.slice().reverse();
 return `<aside class="journal-panel" aria-label="Deduction History"><div class="journal-top"><div><h2>Deduction History</h2><span>DEDUCTION HISTORY · ${ev.length} events</span></div><button type="button" class="history-hide" data-history-toggle="hide">Hide ↗</button></div>
   <div class="journal-filters" role="group" aria-label="Filter received cards">
     <button data-journal="all" class="${journalPerson==='all'?'active':''}">All</button>
     ${state.players.filter(p=>p.char!==null).map(p=>`<button data-journal="${p.index}" class="${journalPerson===String(p.index)?'active':''}">${escapeHTML(p.symbol)} ${escapeHTML(p.name)}</button>`).join('')}
   </div>
   <p class="journal-explainer">${journalPerson==='all'?'All passes · Newest first':`${escapeHTML(state.players[Number(journalPerson)]?.name||'selected player')} received cards & reactions · Newest first`}</p>
   <div class="journal-scroll" id="journal-scroll" tabindex="0" aria-label="Turn history">
     ${chronological.length?chronological.map(e=>{
       const f=state.players[e.from],t=state.players[e.to];
       const card=e.face_up&&e.card?{id:e.card,visible:true}:null;
       return `<article class="journal-event"><div class="event-number">#${String(e.step).padStart(2,'0')}</div><div class="event-main"><div class="event-route"><b>${escapeHTML(f.symbol||'')}${escapeHTML(f.name)}</b><span>→</span><b>${escapeHTML(t.symbol||'')}${escapeHTML(t.name)}</b></div><div class="event-sub">${e.face_up?'Face-up pass':'Face-down pass'}${e.announced_count!==undefined?` · Declared ${e.announced_count} cards of received color`:''}${e.guessed_number?` · Guessed ${e.guessed_number} (${e.guess_wrong?'wrong':'correct'})`:''}</div></div><img class="journal-card-img" src="${imageFor(card)}" alt="${card?'Face-up Card':'Face-down Card'}">${reactionToken(e.reaction)}</article>`;
     }).join(''):`<div class="journal-empty">${journalPerson==='all'?'No passes recorded yet.':'No cards received by this player yet.'}<small>Only information made public during play is shown.</small></div>`}
   </div>
   <div class="journal-foot"><span class="legend-item"><i class="legend-chip green"></i> Needed</span><span class="legend-item"><i class="legend-chip red"></i> Not Needed</span><span class="legend-item"><i class="legend-card"></i> Face down</span></div>
 </aside>`;
}
function playerHandDock(){
 const p=state.players[state.me],readOnly=state.inspect!==null||p.bot;
 const isMyTurn=state.phase==='turn'&&state.turn===state.me&&!readOnly;
 const reveal=state.phase==='reveal'&&!p.revealed&&!readOnly;
 const initialPass=state.phase==='initial_pass'&&!state.initial_pass_submitted&&!readOnly;
 const choosing=isMyTurn||reveal||initialPass;
 const offering=isMyTurn && state.allowed_actions?.includes('offer');
 let instruction='Review your cards';
 if(state.phase==='turn')instruction=isMyTurn?(offering?'① Select 2 cards → ② Select teammate → ③ Offer there':'① Select a card → ② Select teammate in Team Status → ③ Confirm there'):'Another player is taking their turn';
 if(state.phase==='initial_pass')instruction=state.initial_pass_submitted?'Waiting for other players to choose':'Select 1 Information Card for the simultaneous pass to your right';
 if(state.phase==='guess')instruction=state.pending?.to===state.me?'Guess the number in Live Turn before viewing the card':'Waiting for the recipient’s guess';
 if(state.phase==='characters')instruction=state.rules?.includes('sets aside')||state.rules?.includes('holds card')?'Choose a character before the cards are dealt. The ▲ character will set aside one unseen card.':'Review your hand and choose a character';
 if(state.phase==='reveal')instruction=p.revealed?'Waiting for other players to reveal their cards':'Choose 1 card to reveal';
 if(state.phase==='announce')instruction=state.pending?.to===state.me?'Announce the number of matching-color cards':'Waiting for the recipient to announce';
 if(state.phase==='feedback')instruction=state.pending?.to===state.me?'Respond to the received card':'Waiting for the recipient’s reaction';
 if(state.phase==='ended')instruction='Mission Result';
 const hand=p.hand.map(c=>{
   if(!c.id)return '';
   const enabled=choosing && (state.phase!=='reveal'||c.id!=='start');
   const justReceived=c.id===p.last_received;
   return `<button class="hand-item ${selectedCard===c.id||secondOfferCard===c.id?'picked':''} ${justReceived?'just-received':''}" data-card="${escapeHTML(c.id)}" ${enabled?'':'disabled'} aria-pressed="${selectedCard===c.id||secondOfferCard===c.id}" title="${justReceived?'Most recently received card':c.public?'Face up':''}"><img src="${imageFor(c)}" alt="${escapeHTML(c.id)}"/>${c.public?'<span class="known-card">PUBLIC</span>':''}${justReceived?'<span class="received-tag">NEW</span>':''}</button>`;
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
 } else if(state.phase==='initial_pass'){
   actions=state.initial_pass_submitted?'<span class="dock-wait">Selection confirmed · Waiting for others</span>':'<span class="dock-wait">Select an Information Card, then confirm in Live Turn.</span>';
 } else if(state.phase==='guess'){
   actions='<span class="dock-wait">The receiving player must guess the number before looking.</span>';
 } else if(state.phase==='offer_choice' && state.offer?.to===state.me && !readOnly){
   actions='<span class="dock-wait">Choose one of the offered cards in the Live Turn panel.</span>';
 } else if(state.phase==='announce'){
   actions='<span class="dock-wait">Use the Announce button in Live Turn. Red Chip is mandatory.</span>';
 } else if(state.phase==='feedback'&&state.pending?.to===state.me&&!readOnly){
   actions=`<div class="feedback-actions"><button class="feedback-button green" data-feedback="true"><span>✓</span><b>Green Chip</b><small>Needed</small></button><button class="feedback-button red" data-feedback="false"><span>×</span><b>Red Chip</b><small>Not Needed</small></button></div>`;
 } else if(isMyTurn){
   actions=`<div class="selected-destination">${selectedCard?`Selected: <b>${escapeHTML(selectedCard==='start'?'Starting Card':selectedCard)}</b>`:'Select a card'}<br>${selectedTarget!==null?`Recipient: <b>${escapeHTML(state.players[selectedTarget].name)}</b><br>Confirm in Team Status above.`:'Then select a teammate in Team Status above.'}</div>`;
 } else if(state.phase==='ended'){
   const success=state.result==='success';
   const hasNext=state.mission<5 || CITIES.findIndex(c=>c.id===currentCity())<CITIES.length-1;
   const nextCity=state.mission===5 ? CITIES[CITIES.findIndex(c=>c.id===currentCity())+1] : null;
   const nextLabel=nextCity?`Next City: ${nextCity.name} #01 →`:'Next Mission →';
   actions=state.is_owner?`<button class="btn primary dock-button" data-do="${success&&hasNext?'next':'retry'}">${success&&hasNext?nextLabel:success?'Play Mission Again':'Retry Mission →'}</button>`:`<span class="dock-wait">Waiting for the host to continue.</span>`;
 } else if(state.phase==='turn' && state.ai_waiting && !readOnly && state.inspect===null){
   actions=`<span class="dock-wait">It is an AI turn. Use the <b>Advance AI Turn</b> button above Deduction History to advance one turn at a time.</span>`;
 } else if(state.phase==='feedback'){
   actions=`<span class="dock-wait">${escapeHTML(state.players[state.pending?.to]?.name||'Recipient')} is choosing a reaction.</span>`;
 } else {
   actions=`<span class="dock-wait">${state.inspect!==null?'Inspection mode · Read only':'It is not your turn.'}</span>`;
 }
 return `<section class="hand-dock" aria-label="Your hand and game controls">
   <div class="dock-head"><div><h2>Your Hand <span>${p.hand_size} cards</span></h2><p>${instruction}${p.last_received&&p.hand.some(c=>c.id===p.last_received)?` · <strong class="received-help">NEW = most recently received card</strong>`:''}</p></div><div class="dock-pills"><span class="dock-seat">${escapeHTML(p.symbol||'○')} ${escapeHTML(p.name)}</span>${p.chips!==null?`<span class="dock-chip">◷ ${p.chips}</span>`:''}</div></div>
   <div class="dock-body"><div class="dock-hand">${hand||'<div class="no-hand">Waiting for the game to start.</div>'}</div><div class="dock-controls">${actions}</div></div>
 </section>`;
}
function overlayPanel(){
 if(!overlay)return '';
 const n=String(state.mission).padStart(2,'0');
 const links=state.debug&&state.is_owner?`<section class="debug-sub"><h3>Developer Test · Player Views</h3><p>Inspection mode lets the host see private hands. Do not use it in a real game.</p><div class="debug-actions">${state.players.map(p=>`<a target="_blank" rel="noopener" href="/?room=${encodeURIComponent(state.code)}&inspect=${p.index}">${escapeHTML(p.name)} ↗</a>`).join('')}</div></section>`:'';
 let content='';
 if(overlay==='retry'){
  content=`<div class="leave-confirm"><h3>Retry this mission?</h3><p>The current deal and progress will be discarded for everyone in this room.</p><p>All players will return to the character-selection setup after the host starts the mission again.</p><div class="leave-actions"><button class="btn ghost" data-overlay="close">Cancel</button><button class="btn warn" data-do="confirm_retry">Retry Mission</button></div></div>`;
 }else if(overlay==='leave'){
  content=`<div class="leave-confirm"><h3>Leave this game?</h3><p>Your current play session will be closed on this device. You will return to the home screen.</p><p class="help-warning">Other players may remain in the room. This does not end the room for everyone.</p><div class="leave-actions"><button class="btn ghost" data-overlay="close">Stay in Game</button><button class="btn warn" data-do="confirm_leave">Leave Game</button></div></div>`;
 }else if(overlay==='mission'){
  content=`<div class="mission-view-tabs"><button data-side="rules" class="${missionSide==='rules'?'active':''}">Mission Rules</button><button data-side="story" class="${missionSide==='story'?'active':''}">Mission Story</button></div>
  <img class="mission-full" src="${missionImage(state.mission,missionSide,currentCity())}" alt="${cityLabel(currentCity())} ${n} mission ${missionSide}"/><p class="modal-rule">${missionSide==='rules'?ruleShort():'The story is shown on the card above.'}</p>`;
 }else{
  content=`<div class="help-content"><h3>Game Objective</h3><p>Work together to complete four Information Sets, one per color, each containing cards 1–5. Players must not reveal the contents of their hands through conversation.</p>
  <h3>Turn Sequence</h3><ol><li>The ▲ character holding the Starting Card takes the first turn.</li><li>Pass one card to another active player, face down unless a mission rule requires face-up passing.</li><li>The recipient spends a Time Chip, showing green if the card is needed or red if it is not.</li><li>The recipient takes the next turn.</li><li>When a player completes a color set, they reveal their cards and leave the mission.</li><li>All four sets completed: success. Running out of Time Chips before completing a set: failure.</li></ol>
  <h3>Deduction History</h3><p>Only cards that were face up during play are identified. Face-down cards remain hidden. Select a character to filter their received-card history.</p>
  <p class="help-warning">Provisional rule: receiving the Starting Card costs one red Time Chip. This exception is not explicitly addressed in the supplied rulebook.</p>${links}</div>`;
 }
 return `<div class="modal-shade" data-backdrop="true"><section class="modal-dialog" role="dialog" aria-modal="true" aria-label="${overlay==='mission'?'Mission Card':overlay==='leave'?'Leave Game':overlay==='retry'?'Retry Mission':'Game Rules'}"><header class="modal-header"><div><span class="eyebrow">S.O.R.T. 5</span><h2>${overlay==='mission'?`${cityLabel(currentCity()).toUpperCase()} #${n}`:overlay==='leave'?'Leave Game':overlay==='retry'?'Retry Mission':'Game Rules'}</h2></div><button class="modal-close" data-overlay="close" aria-label="Close">✕</button></header>${content}</section></div>`;
}
function historyWarningModal(){
 return `<div class="modal-shade history-warning-shade" role="presentation"><section class="history-warning" role="dialog" aria-modal="true" aria-label="Unlock Deduction History"><h2>Unlock Deduction History?</h2><p>SORT 5 is designed around remembering card exchanges and reading other players’ reactions. Showing previous turns will make the game easier.</p><strong>Would you like to see the history?</strong><div class="history-warning-actions"><button type="button" class="btn ghost" data-history-warning="cancel">Keep Hidden</button><button type="button" class="btn primary" data-history-warning="confirm">Show History</button></div></section></div>`;
}
function render(){
 if(!state){welcome();return;}
 const journalScroll=document.getElementById('journal-scroll');
 const scrollY=journalScroll?journalScroll.scrollTop:0;
 if(journalPerson!=='all' && (!state.players[Number(journalPerson)]))journalPerson='all';
 app.innerHTML=`<main class="main game-main phase-${state.phase}">${topBar()}${errorText?`<div class="alert" role="alert">${escapeHTML(errorText)}</div>`:''}${missionRibbon()}${announcementBanner()}
   ${state.inspect!==null?'<div class="inspect-banner">TEST MODE · Viewing another player’s screen. Controls are disabled.</div>':''}
   <div class="mobile-ai-turn-bar">${aiTurnActionPanel()}</div>
   <div class="play-grid"><div class="board-column">${playerBoard()}${currentStage()}${playerHandDock()}</div><div class="journal-column">${missionCardPanel()}<div class="desktop-ai-turn">${aiTurnActionPanel()}</div>${journalPanel()}</div></div>
   <footer class="foot">SORT 5 · SPECIAL ACTIONS DEV v2.9 · Private hands are kept separate by the server.</footer>
   ${overlayPanel()}${historyWarningOpen?historyWarningModal():''}</main>`;
 if(journalScroll && document.getElementById('journal-scroll'))document.getElementById('journal-scroll').scrollTop=scrollY;
 document.querySelectorAll('[data-card]').forEach(b=>b.addEventListener('click',()=>{
   const card=b.dataset.card;
   if(state.allowed_actions?.includes('offer') && state.phase==='turn'){
     if(selectedCard===card){selectedCard=secondOfferCard;secondOfferCard=null;}
     else if(secondOfferCard===card){secondOfferCard=null;}
     else if(!selectedCard){selectedCard=card;}
     else {secondOfferCard=card;}
   }else{selectedCard=card;secondOfferCard=null;}
   selectedTarget=null;render();
 }));
 document.querySelectorAll('[data-guess]').forEach(b=>b.addEventListener('click',()=>action('guess_number',{guess:Number(b.dataset.guess)})));
 document.querySelectorAll('[data-offer-choice]').forEach(b=>b.addEventListener('click',()=>action('choose_offer',{choice:b.dataset.offerChoice})));
 document.querySelectorAll('[data-target]').forEach(b=>b.addEventListener('click',()=>{selectedTarget=Number(b.dataset.target);render();}));
 document.querySelectorAll('[data-char]').forEach(b=>b.addEventListener('click',()=>action('character',{character:Number(b.dataset.char)})));
 document.querySelectorAll('[data-feedback]').forEach(b=>b.addEventListener('click',()=>action('feedback',{positive:b.dataset.feedback==='true'})));
 document.querySelectorAll('[data-journal]').forEach(b=>b.addEventListener('click',()=>{if(!historyUnlocked){historyWarningOpen=true;}else{historyVisible=true;}journalPerson=b.dataset.journal;render();}));
 document.querySelectorAll('[data-history-toggle]').forEach(b=>b.addEventListener('click',()=>{if(b.dataset.historyToggle==='hide'){historyVisible=false;}else if(historyUnlocked){historyVisible=true;}else{historyWarningOpen=true;}render();}));
 document.querySelectorAll('[data-history-warning]').forEach(b=>b.addEventListener('click',()=>{if(b.dataset.historyWarning==='confirm'){historyUnlocked=true;historyVisible=true;}historyWarningOpen=false;render();}));
 document.querySelectorAll('[data-overlay]').forEach(b=>b.addEventListener('click',()=>{overlay=b.dataset.overlay==='close'?null:b.dataset.overlay;render();}));
 document.querySelectorAll('[data-open-mission]').forEach(b=>b.addEventListener('click',()=>openMissionLightbox(state.mission,b.dataset.openMission,currentCity())));
 document.querySelectorAll('[data-side]').forEach(b=>b.addEventListener('click',()=>{missionSide=b.dataset.side;render();}));
 document.querySelector('[data-backdrop]')?.addEventListener('click',e=>{if(e.target===e.currentTarget){overlay=null;render();}});
 document.querySelectorAll('[data-do]').forEach(b=>b.addEventListener('click',async()=>{
   const a=b.dataset.do;
   if(a==='retry_confirm'){overlay='retry';render();}
   else if(a==='confirm_retry'){overlay=null;await action('retry');}
   else if(a==='leave'){overlay='leave';render();}
   else if(a==='confirm_leave'){
     const currentCode=credentials?.code;
     credentials=null;state=null;overlay=null;errorText='';selectedCard=null;secondOfferCard=null;selectedTarget=null;journalPerson='all';historyUnlocked=false;historyVisible=false;historyWarningOpen=false;lastSnapshotSignature='';
     sessionStorage.removeItem('sort5_credentials');
     if(currentCode)localStorage.removeItem(`sort5_debug_${currentCode}`);
     window.history.replaceState({},'',window.location.pathname);
     render();
   }
   else if(a==='advance_ai'){await action('advance_ai');}
   else if(a==='announce'){await action('announce');}
   else if(a==='initial_pass'&&selectedCard){await action('initial_pass',{card:selectedCard});}
   else if(a==='copy'){
     const invite=`${location.origin}/?room=${state.code}`;
     try{await navigator.clipboard.writeText(invite);b.textContent='Copied ✓';}catch{window.prompt('Copy invite link',invite)}
   }else if(['begin','retry','next'].includes(a)){
     if(a==='retry'||a==='next'){journalPerson='all';historyUnlocked=false;historyVisible=false;historyWarningOpen=false;}
     await action(a);
   }else if(a==='reveal'&&selectedCard){await action('reveal',{card:selectedCard});}
   else if(a==='pass'&&selectedCard&&selectedTarget!==null){await action('pass',{card:selectedCard,target:selectedTarget});}
   else if(a==='offer'&&selectedCard&&secondOfferCard&&selectedTarget!==null){await action('offer',{cards:[selectedCard,secondOfferCard],target:selectedTarget});}
 }));
}
function initialize(){
 try{const c=JSON.parse(sessionStorage.getItem('sort5_credentials'));if(c?.token&&(!qRoom||qRoom===c.code))credentials=c;}catch{}
 if(!credentials&&qRoom&&INSPECT!==null){
   const ownerToken=localStorage.getItem(`sort5_debug_${qRoom}`);
   if(ownerToken)credentials={code:qRoom,token:ownerToken,debugOwner:true};
 }
 if(credentials)loadState();else render();
 document.addEventListener('keydown', e=>{if(e.key==='Escape'){if(historyWarningOpen){historyWarningOpen=false;render();return;}const lightbox=id('mission-lightbox');if(lightbox){lightbox.remove();return;}if(overlay){overlay=null;render();}}});
 setInterval(()=>{if(credentials&&document.visibilityState==='visible')loadState();},1500);
}
initialize();
