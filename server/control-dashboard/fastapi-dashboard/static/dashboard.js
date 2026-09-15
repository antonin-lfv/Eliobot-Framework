'use strict';
const $ = id => document.getElementById(id);
const modes = {idle:'Veille', manual:'Manuel', exploration:'Exploration', fly:'Connectome de mouche'};
const actionLabels = {start:'Départ', moved_forward:'Avancé', turned_left:'Rotation gauche', turned_right:'Rotation droite', uturn:'Demi-tour'};
let state = {connected:false, mode:'idle', steps:[], control:{active:'idle', paused:null, revision:0}, fly:{status:'unloaded',steps:0}};
let compatible = false, compatibilityError = '';
let selectedNeuronId = null;
let probeFrame = null, probeTimer = null, probeBusy = false;
let wsConnected = false, heldDir = null, holdTimer = null, moveChain = Promise.resolve(), moveBusy = false;
let epoch = 0, takeoverRevision = null, muted = false, toastTimer, speedTimer;
let lastNeuralStep = -1, activityHistory = [], eyePatterns = {};
const incompatibilityMessage = 'L’interface et le serveur ne sont pas à la même version. Reconstruire et redémarrer le dashboard, puis recharger cette page.';
const controls = [...document.querySelectorAll('[data-direction]')];

function notify(message) {
  $('toast').textContent = message; $('toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, 5000);
}
async function api(path, body = {}) {
  if (!compatible && !(path === '/command/mode' && body.mode === 'idle')) throw new Error(compatibilityError || 'En attente de la connexion au serveur.');
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  let result;
  try { result = await response.json(); } catch { throw new Error(`Réponse du serveur illisible (HTTP ${response.status}). Recharger la page après la mise à jour du serveur.`); }
  if (response.status === 404) {
    compatible = false; compatibilityError = incompatibilityMessage; renderConnection();
    throw new Error(incompatibilityMessage);
  }
  if (!response.ok) { const error = new Error(typeof result.detail === 'string' ? result.detail : 'La commande n’a pas été acceptée.'); error.detail = result.detail; throw error; }
  return result;
}
function acceptState(message) {
  const incoming = message.state;
  if (!incoming || typeof incoming !== 'object') {
    compatible = false; compatibilityError = incompatibilityMessage; renderConnection(); return false;
  }
  if (message.type === 'snapshot') {
    compatible = incoming.protocol === 3 && incoming.control && Number.isInteger(incoming.control.revision);
    compatibilityError = compatible ? '' : incompatibilityMessage;
    state = {...state, ...incoming, control:{active:'idle',paused:null,revision:0,...(incoming.control || {})},fly:incoming.fly || {status:'unloaded',steps:0},steps:incoming.steps || []};
  } else {
    const {control,fly,...rest} = incoming;
    Object.assign(state,rest);
    if (control) state.control = {...state.control,...control};
    if (fly) state.fly = {...state.fly,...fly};
    if (message.steps_append) state.steps = [...state.steps,...message.steps_append].slice(-1000);
  }
  return true;
}
function online() {
  return compatible && wsConnected && state.connected && state.last_seen && Date.now()-Date.parse(state.last_seen)<3000;
}
function clearHold() {
  heldDir = null; epoch++; clearInterval(holdTimer); holdTimer = null;
  controls.forEach(button => button.classList.remove('held'));
}
function releaseControl() {
  const held = heldDir !== null;
  clearHold();
  if (held) queueMove('stop');
  return moveChain;
}
function queueMove(direction) {
  if (direction !== 'stop' && moveBusy) return moveChain;
  const generation = epoch;
  moveBusy = true;
  moveChain = moveChain.then(async () => {
    if (direction !== 'stop' && (generation !== epoch || heldDir !== direction)) return;
    try {
      const result = await api('/command/move', {direction,revision:state.control.revision});
      if (direction !== 'stop' && result.revision >= state.control.revision) {
        state.control = {...state.control,active:'manual',revision:result.revision};
      }
    }
    catch(error) {
      if (error.detail?.confirmation_required) {
        clearHold();
        takeoverRevision = error.detail.revision;
        const name = error.detail.active === 'fly' ? 'la mouche' : 'l’exploration';
        $('takeover-title').textContent = `Mettre ${name} en pause ?`;
        if (!$('takeover-dialog').open) $('takeover-dialog').showModal();
      } else { clearHold(); notify(error.message); }
    }
  }).finally(() => { moveBusy = false; });
  return moveChain;
}
function startControl(direction) {
  if (!online() || $('takeover-dialog').open || heldDir === direction) return;
  releaseControl(); heldDir = direction;
  controls.forEach(button => button.classList.toggle('held', button.dataset.direction === direction));
  queueMove(direction);
  holdTimer = setInterval(() => { if (heldDir) queueMove(heldDir); }, 250);
}
async function autonomy(mode) {
  await releaseControl();
  try { await api('/command/autonomy', {mode, action:state.control.active === mode ? 'pause':'start'}); }
  catch(error) { notify(error.message); }
}
async function stopAll() {
  releaseControl();
  try { await api(compatible ? '/command/stop' : '/command/mode', compatible ? {} : {mode:'idle'}); } catch(error) { notify(error.message); }
}
function connect() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss':'ws'}://${location.host}/ws`);
  ws.onmessage = event => {
    try {
      const message = JSON.parse(event.data);
      if (!['snapshot','delta'].includes(message.type)) {
        compatible = false; compatibilityError = incompatibilityMessage; renderConnection(); return;
      }
      if (!acceptState(message)) return;
      wsConnected = true;
      render(message.type === 'snapshot' || 'steps' in message.state || !!message.steps_append);
    } catch(error) { console.error(error); notify('La télémétrie reçue est invalide.'); }
  };
  ws.onclose = () => { wsConnected = false; compatible = false; releaseControl(); renderConnection(); setTimeout(connect, 2000); };
  ws.onerror = () => ws.close();
}
function renderConnection() {
  const live = online();
  $('compatibility-notice').hidden = !compatibilityError;
  $('compatibility-notice').textContent = compatibilityError;
  $('connection').classList.toggle('online', !!live);
  $('connection-label').textContent = live ? 'Robot connecté' : (wsConnected && state.connected ? 'Robot absent' : 'Hors connexion');
  controls.forEach(button => button.disabled = !live);
  $('speed').disabled = !live;
  $('exploration-action').disabled = !live;
  $('mute').disabled = !live;
  $('buzzer').disabled = !live;
  renderSensors(); renderEyes();
  const age = state.last_seen ? Math.max(0, Math.round((Date.now()-Date.parse(state.last_seen))/1000)) : null;
  $('last-signal').textContent = age === null ? 'AUCUN SIGNAL' : `SIGNAL IL Y A ${age} S`;
  $('battery-header').textContent = Number.isFinite(state.battery_v) ? `${state.battery_v.toFixed(2)} V` : '— V';
  if (!live && heldDir) releaseControl();
  const flyStatus = state.fly?.status;
  $('fly-action').disabled = !compatible || probeBusy || flyStatus === 'loading' || flyStatus === 'resetting' || (flyStatus === 'ready' && !live);
}
function render(mapChanged = true) {
  if (state.control.active === 'fly' && probeFrame) clearProbe();
  renderConnection();
  const control = state.control || {active:state.mode};
  $('active-mode').textContent = modes[control.active] || 'Veille';
  $('session-detail').textContent = control.paused ? `${modes[control.paused]} en pause` : (online() ? 'Session active' : 'En attente du robot');
  $('control-notice').hidden = !control.reason;
  $('control-notice').textContent = control.reason || '';
  $('manual-live').classList.toggle('on', control.active === 'manual');
  $('manual-hint').textContent = ['exploration','fly'].includes(control.active) ? 'Une confirmation sera demandée pour reprendre la main.' : 'Clavier : flèches · relâcher pour arrêter';
  if (heldDir && ['exploration','fly'].includes(control.active)) releaseControl();
  for (const mode of ['exploration','fly']) {
    const running = control.active === mode, paused = control.paused === mode;
    $(`${mode}-card`).classList.toggle('running', running);
    $(`${mode}-status`).classList.toggle('active', running);
    $(`${mode}-status`).textContent = running ? 'EN COURS' : paused ? 'EN PAUSE' : 'À L’ARRÊT';
    $(`${mode}-label`).textContent = running ? 'Mettre en pause' : paused ? 'Reprendre' : mode === 'fly' ? 'Lancer la mouche' : 'Lancer l’exploration';
  }
  const fly = state.fly || {};
  const availability = {unloaded:'NON CHARGÉ',loading:'CHARGEMENT…',error:'INDISPONIBLE',resetting:'REMISE À ZÉRO…'};
  if (fly.status !== 'ready') {
    $('fly-status').textContent = availability[fly.status] || 'NON CHARGÉ';
    $('fly-label').textContent = fly.status === 'loading' ? 'Chargement…' : fly.status === 'error' ? 'Réessayer le chargement' : 'Charger le cerveau';
  }
  $('fly-error').hidden = !fly.error;
  $('fly-error').textContent = fly.error ? `Connectome indisponible. ${fly.error}` : '';
  $('reset-brain').disabled = !compatible || probeBusy || fly.status !== 'ready' || control.active === 'fly';
  $('position-warning').textContent = state.status?.position_valid === false
    ? 'Position incertaine après un mouvement manuel, neuronal ou interrompu. Replacer le robot au départ puis réinitialiser pour retrouver ce repère.'
    : 'Position déduite des commandes, sans mesure de distance réelle.';
  if (mapChanged) { renderMap(); renderLog(); }
  renderNeural();
}
function renderMap() {
  const steps = (state.steps || []).filter(step => Number.isFinite(step.x) && Number.isFinite(step.y));
  const moves = steps.filter(s => s.action === 'start' || s.action === 'moved_forward');
  const last = steps.at(-1);
  $('position').textContent = last ? `${last.x} / ${last.y}` : '— / —';
  $('step-count').textContent = String(steps.filter(s => s.action === 'moved_forward').length);
  $('visited').textContent = String(state.visited_count || 0);
  $('map-caption').hidden = !!last;
  const xs = steps.map(s => s.x), ys = steps.map(s => s.y);
  const minX = Math.min(-3,...xs)-1, maxX = Math.max(3,...xs)+1, minY = Math.min(-2,...ys)-1, maxY = Math.max(2,...ys)+1;
  const scale = Math.min(620/(maxX-minX),230/(maxY-minY));
  const project = (x,y) => [360+(x-(maxX+minX)/2)*scale,165-(y-(maxY+minY)/2)*scale];
  $('map-path').setAttribute('d', moves.map((s,i) => `${i?'L':'M'}${project(s.x,s.y).join(' ')}`).join(' '));
  const pos = last ? project(last.x,last.y) : [360,165];
  $('map-robot').setAttribute('transform',`translate(${pos.join(' ')})`);
  $('map-heading').setAttribute('transform',`rotate(${Number.isFinite(last?.heading) ? last.heading*90 : 0})`);
  const obstacles = $('map-obstacles'); obstacles.replaceChildren();
  const dx=[0,1,0,-1],dy=[1,0,-1,0],seen=new Set();
  for(const s of steps) {
    for(const [field,offset] of [['front',0],['right',1],['left',3]]) {
      if(!s[field]) continue;
      const heading=((s.heading||0)+offset)%4,x=s.x+dx[heading],y=s.y+dy[heading],key=`${x},${y}`;
      if(seen.has(key)) continue; seen.add(key);
      const [px,py]=project(x,y), point=document.createElementNS('http://www.w3.org/2000/svg','path');
      point.setAttribute('d',`M${px-3} ${py-3}l6 6m0 -6l-6 6`); point.setAttribute('stroke','#b77560'); point.setAttribute('stroke-width','1.5');obstacles.appendChild(point);
    }
  }
}
function renderLog() {
  const steps=state.steps || []; $('log-count').textContent=`${steps.length} étapes`;
  $('log-body').replaceChildren();
  for(const step of steps.slice(-12).reverse()) {
    const row=document.createElement('tr');
    for(const value of [step.ts||'—',`${step.x}, ${step.y}`,actionLabels[step.action]||'Étape',...['front','left','right'].map(k=>step[k]?'Obstacle':'Libre')]) {
      const cell=document.createElement('td');cell.textContent=value;row.appendChild(cell);
    }
    $('log-body').appendChild(row);
  }
}
function renderSensors() {
  const live=online();
  for(const name of ['left','front','right','back']) {
    const blocked=!!state.obstacles?.[name];
    $(`sensor-${name}`).classList.toggle('blocked',live && blocked);
    $(`beam-${name}`).classList.toggle('detected',live && blocked);
    $(`sensor-${name}-value`).textContent=live ? (blocked?'OBSTACLE':'LIBRE') : '—';
    const raw=state.obstacles?.raw?.[name], threshold=state.obstacles?.thresholds?.[name];
    $(`raw-${name}`).textContent=live && Number.isFinite(raw) && Number.isFinite(threshold) ? `${raw} / ${threshold}` : '— / —';
  }
  $('sensor-diagnostic-note').textContent=!live?'En attente des mesures du robot.':state.obstacles?.raw?'Seuils réglables dans la configuration du robot. Les valeurs ne sont pas des distances.':'Mettre à jour le programme du robot pour recevoir les valeurs brutes.';
  for(let i=0;i<5;i++) {
    const raw=Number.isFinite(state.lines?.[i])?state.lines[i]:0;
    $(`line-${i}`).classList.toggle('dark',live && raw<(state.status?.line_threshold ?? 30000));
    $(`line-fill-${i}`).style.height=`${Math.max(0,Math.min(100,raw/65535*100))}%`;
    $(`line-value-${i}`).textContent=live ? raw : '—';
  }
}
function renderNeural() {
  const f=probeFrame || state.fly || {}, number=(v,d=2)=>Number.isFinite(v)?v.toFixed(d):'—';
  renderNeurons(f);
  $('vision-left').textContent=number(f.vision_L,1);$('vision-right').textContent=number(f.vision_R,1);
  $('motor-output').textContent=`${number(f.motor_L)} / ${number(f.motor_R)}`;
  $('wheel-output').textContent=`${number(f.left,0)} / ${number(f.right,0)} %`;
  $('neural-steps').textContent=`${f.steps||0} PAS`; $('compute-time').textContent=`${number(f.compute_ms,1)} MS / PAS`;
  $('fly-guard').textContent=f.guard?'Obstacle frontal : avance bloquée, rotation conservée.':'Commandes limitées à ±45 %';
  if((f.steps||0)<lastNeuralStep) activityHistory=[];
  if(Number.isFinite(f.activity) && f.steps!==lastNeuralStep) activityHistory.push(f.activity);
  activityHistory=activityHistory.slice(-100);lastNeuralStep=f.steps||0;
  const max=Math.max(.01,...activityHistory);
  $('activity-path').setAttribute('d',activityHistory.map((v,i)=>`${i?'L':'M'}${i*260/99} ${50-v/max*44}`).join(' '));
}
function clearProbe() {
  clearInterval(probeTimer); probeTimer = null; probeFrame = null;
  activityHistory = []; lastNeuralStep = -1;
}
function neuronColor(value) {
  const magnitude = Math.min(1,Math.abs(value || 0));
  if(magnitude < .001) return '#d6dfd9';
  return value < 0 ? `hsl(262 48% ${78-magnitude*39}%)` : `hsl(143 60% ${78-magnitude*48}%)`;
}
function renderNeurons(f) {
  const testing = !!probeFrame;
  $('activity-source').textContent = testing ? 'Test simulé · aucune commande au robot' : 'Activité liée au robot';
  $('activity-help').textContent = probeBusy ? 'Calcul de la propagation dans le réseau complet…' : testing ? '32 pas depuis le repos. La stimulation et les réponses affichées sont simulées ; les roues ne sont pas commandées.' : state.fly?.status !== 'ready' ? 'Charger le cerveau pour observer ses neurones.' : state.control.active === 'fly' ? 'Les capteurs réels stimulent le réseau et ses réponses commandent ElioBot.' : 'Le réseau est prêt. Tester une stimulation sans mouvement, ou lancer la mouche avec le robot connecté.';
  document.querySelectorAll('[data-probe]').forEach(button=>button.disabled = !compatible || probeBusy || state.fly?.status !== 'ready' || state.control.active === 'fly');
  $('show-live').hidden = !testing;
  $('active-neurons').textContent = Number.isFinite(f.active_count) ? f.active_count.toLocaleString('fr-FR') : '—';
  for (const [side,name] of [['L','left'],['R','right']]) {
    const cells=f.sensory?.[side] || [], container=$(`neurons-${name}`);
    if(container.children.length !== cells.length) container.replaceChildren();
    $(`count-${name}`).textContent = cells.length ? `· ${cells.length}` : '';
    cells.forEach((cell,index)=>{
      let dot=container.children[index];
      if(!dot) {dot=document.createElement('button');dot.type='button';dot.className='neuron-dot';dot.addEventListener('click',()=>{selectedNeuronId=cell.id;renderNeural();});container.appendChild(dot);}
      const label=`${cell.type} ${side} · ${cell.id} · activité ${cell.value.toFixed(4)}`;
      dot.title=label;dot.setAttribute('aria-label',label);dot.setAttribute('aria-pressed',String(selectedNeuronId===cell.id));dot.style.background=neuronColor(cell.value);
    });
  }
  const selected=[...(f.sensory?.L||[]),...(f.sensory?.R||[])].find(cell=>cell.id===selectedNeuronId);
  $('selected-neuron').textContent=selected ? `${selected.type} · ${selected.side==='L'?'gauche':'droite'} · ID ${selected.id} · activité ${selected.value.toFixed(4)}` : 'Choisir un neurone pour suivre son activité.';
  const ranking=$('top-neurons');ranking.replaceChildren();
  for(const cell of f.top_neurons || []) {
    const row=document.createElement('div');row.className='rank-row';
    const name=document.createElement('span');name.className='rank-name';name.textContent=`${cell.type} · ${cell.side}`;
    const id=document.createElement('small');id.textContent=cell.id;name.appendChild(id);
    const track=document.createElement('span');track.className='rank-track';const fill=document.createElement('i');fill.style.width=`${Math.min(100,Math.abs(cell.value)*100)}%`;fill.style.background=neuronColor(cell.value);track.appendChild(fill);
    const value=document.createElement('strong');value.textContent=cell.value.toFixed(3);row.append(name,track,value);ranking.appendChild(row);
  }
  if(!(f.top_neurons || []).length) {const empty=document.createElement('p');empty.className='footnote';empty.textContent=state.fly?.status==='ready'?'Le réseau est au repos. Présenter une stimulation pour voir sa réponse.':'Les neurones apparaîtront après le chargement.';ranking.appendChild(empty);}
  const motors=$('motor-neurons');motors.replaceChildren();
  for(const cell of f.motor_neurons || []) {
    const block=document.createElement('div');block.className='motor-cell';
    const label=document.createElement('span');label.textContent=`${cell.type} · ${cell.side==='L'?'gauche':'droite'}`;
    const value=document.createElement('strong');value.textContent=cell.value.toFixed(3);value.style.color=cell.value<0?'#6743af':'#17643b';
    const id=document.createElement('small');id.textContent=cell.id;block.append(label,value,id);motors.appendChild(block);
  }
}
async function runProbe(stimulus) {
  if(probeBusy) return;
  clearProbe();probeBusy=true;renderNeural();renderConnection();
  try {
    const result=await api('/command/fly/probe',{stimulus});
    if(state.control.active==='fly')return;
    const frames=result.frames || [];let index=0;
    if(frames.length) {
      probeFrame=frames[0];renderNeural();
      probeTimer=setInterval(()=>{index++;if(index>=frames.length){clearInterval(probeTimer);probeTimer=null;return;}probeFrame=frames[index];renderNeural();},100);
    }
  } catch(error){notify(error.message);}
  finally{probeBusy=false;renderNeural();renderConnection();}
}
function renderEyes() {
  const pattern=eyePatterns[state.eyes?.pattern]||[], rgb=state.eyes?.color || [80,120,90];
  const channels=rgb.map(v=>Math.max(0,Math.min(255,Number(v)||0)));
  // Conserver la teinte, éclaircir l’aperçu pour lire aussi les LED peu lumineuses.
  const peak=Math.max(...channels), gain=peak>0?Math.max(1,220/peak):1;
  const color=`rgb(${channels.map(v=>Math.round(v*gain)).join(',')})`;
  ['left','right'].forEach((side,j)=>[...$(`eye-${side}`).children].forEach((pixel,i)=>{pixel.style.background=online() && pattern[j*64+i]?color:'#25352d';}));
}
function initialize() {
  if (document.body?.dataset.page === 'fly') {
    $('page-title').textContent = 'Laboratoire mouche.';
    $('page-subtitle').textContent = 'Observer le réseau anatomique, de la stimulation à la réponse motrice.';
  }
  document.querySelectorAll('[data-probe]').forEach(button=>button.addEventListener('click',()=>runProbe(button.dataset.probe)));
  $('show-live').addEventListener('click',()=>{clearProbe();renderNeural();});
  for(const [name,label] of [['left','Gauche'],['front','Avant'],['right','Droite'],['back','Arrière']]) {
    const sensor=document.createElement('div');sensor.id=`sensor-${name}`;sensor.className=`sensor sensor-${name}`;
    const title=document.createElement('span');title.textContent=label;const value=document.createElement('strong');value.id=`sensor-${name}-value`;value.textContent='—';sensor.append(title,value);$('obstacle-grid').appendChild(sensor);
    const row=document.createElement('div');row.className='sensor-diagnostic-row';const labelNode=document.createElement('span');labelNode.textContent=label;const raw=document.createElement('strong');raw.id=`raw-${name}`;raw.textContent='— / —';row.append(labelNode,raw);$('sensor-diagnostics').appendChild(row);
  }
  for(let i=0;i<5;i++) {
    const item=document.createElement('div');item.id=`line-${i}`;item.className='line-reading';const track=document.createElement('div');track.className='line-track';const fill=document.createElement('i');fill.id=`line-fill-${i}`;track.appendChild(fill);const value=document.createElement('span');value.id=`line-value-${i}`;value.textContent='—';item.append(track,value);$('line-readings').appendChild(item);
  }
  for(const side of ['left','right']) for(let i=0;i<64;i++) $(`eye-${side}`).appendChild(document.createElement('i'));
  fetch('/static/eye-patterns.json').then(r=>r.json()).then(data=>{eyePatterns=data;renderEyes();}).catch(()=>{});
  controls.forEach(button=>{
    button.addEventListener('pointerdown',event=>{event.preventDefault();button.setPointerCapture(event.pointerId);startControl(button.dataset.direction);});
    for(const event of ['pointerup','pointercancel','lostpointercapture']) button.addEventListener(event,()=>{if(heldDir===button.dataset.direction)releaseControl();});
  });
  window.addEventListener('blur',releaseControl);window.addEventListener('pagehide',releaseControl);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)releaseControl();});
  const keys={ArrowUp:'forward',ArrowDown:'backward',ArrowLeft:'left',ArrowRight:'right'};
  window.addEventListener('keydown',event=>{if(event.key==='Escape'){stopAll();return;}if(keys[event.key] && !['INPUT','BUTTON','SELECT','TEXTAREA'].includes(event.target.tagName) && !$('takeover-dialog').open){event.preventDefault();if(!event.repeat)startControl(keys[event.key]);}});
  window.addEventListener('keyup',event=>{if(keys[event.key]===heldDir)releaseControl();});
  $('takeover-confirm').addEventListener('click',async()=>{
    $('takeover-confirm').disabled=true;
    try {await api('/command/takeover',{revision:takeoverRevision});$('takeover-dialog').close();notify('Autonomie en pause. Maintenez une direction pour déplacer le robot.');}
    catch(error){$('takeover-dialog').close();notify(error.message);}
    finally{$('takeover-confirm').disabled=false;}
  });
  $('stop-all').addEventListener('click',stopAll);
  $('exploration-action').addEventListener('click',()=>autonomy('exploration'));
  $('fly-action').addEventListener('click',async()=>{
    if(state.fly?.status==='ready')return autonomy('fly');
    $('fly-action').disabled=true;
    try{await api('/command/fly/load');notify('Chargement du connectome complet…');}catch(error){notify(error.message);}finally{renderConnection();}
  });
  $('reset-brain').addEventListener('click',async()=>{try{await api('/command/fly/reset');clearProbe();}catch(error){notify(error.message);}});
  $('reset-map').addEventListener('click',async()=>{await releaseControl();try{await api('/command/reset_map');}catch(error){notify(error.message);}});
  $('speed').addEventListener('input',event=>{
    const speed=Number(event.target.value);$('speed-value').textContent=`${speed} %`;clearTimeout(speedTimer);
    speedTimer=setTimeout(()=>api('/command/speed',{speed}).catch(error=>notify(error.message)),150);
  });
  $('mute').addEventListener('click',async()=>{try{await api('/command/mute',{muted:!muted});muted=!muted;$('mute-label').textContent=muted?'Réactiver le son':'Couper le son';$('mute').setAttribute('aria-pressed',String(muted));$('sound-waves').style.display=muted?'none':'';$('sound-cross').style.display=muted?'':'none';}catch(error){notify(error.message);}});
  $('buzzer').addEventListener('click',()=>api('/command/buzzer').catch(error=>notify(error.message)));
  $('server-host').textContent=location.host;
  render();setInterval(renderConnection,1000);connect();
}
initialize();
