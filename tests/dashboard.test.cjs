// Contrats du JavaScript réel, avec DOM et réseau simulés.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function dashboard(responder = () => ({ok:true, data:{ok:true,revision:1}})) {
  const nodes=new Map(), requests=[], sockets=[],timers=new Map();let timerId=0,mapRenders=0;
  function element() {
    const flags=new Set();
    return {children:[],style:{},dataset:{},disabled:false,hidden:false,open:false,textContent:'',listeners:{},
      classList:{add(k){flags.add(k);},remove(k){flags.delete(k);},toggle(k,v){if(v)flags.add(k);else flags.delete(k);},contains:k=>flags.has(k)},
      appendChild(c){this.children.push(c);},append(...c){this.children.push(...c);},replaceChildren(...c){this.children=[...c];},
      setAttribute(k,v){this[k]=v;if(this===nodes.get('map-path'))mapRenders++;},
      setPointerCapture(){},addEventListener(k,fn){this.listeners[k]=fn;},showModal(){this.open=true;},close(){this.open=false;}
    };
  }
  const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);};
  const document={hidden:false,getElementById:get,createElement:element,createElementNS:element,querySelectorAll:()=>[],listeners:{},addEventListener(k,fn){this.listeners[k]=fn;}};
  const window={listeners:{},addEventListener(k,fn){this.listeners[k]=fn;}};
  const context=vm.createContext({document,window,console,location:{protocol:'http:',host:'localhost:8768'},
    WebSocket:class{constructor(){sockets.push(this);}close(){}},
    fetch:async(url,options)=>{
      if(!options)return {json:async()=>({})};
      const request={url,body:JSON.parse(options.body)};requests.push(request);
      const response=await responder(request);
      return {ok:response.ok,status:response.status,json:async()=>response.data};
    },
    setInterval:fn=>{timers.set(++timerId,fn);return timerId;},clearInterval:id=>timers.delete(id),
    setTimeout:()=>{},clearTimeout(){},
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../server/control-dashboard/fastapi-dashboard/static/dashboard.js'),'utf8'),context);
  return {context,requests,sockets,window,document,get,renders:()=>mapRenders,
    receive:message=>sockets[0].onmessage({data:JSON.stringify(message)}),
    run:code=>vm.runInContext(code,context),flush:()=>vm.runInContext('moveChain',context)};
}
function snapshot(active='exploration') {
  return {type:'snapshot',state:{protocol:3,connected:true,last_seen:new Date().toISOString(),mode:active,
    control:{active,paused:null,revision:0},battery_v:3.8,obstacles:{},steps:[],lines:[0,0,0,0,0],
    status:{line_threshold:57000,position_valid:true},fly:{status:'unloaded',steps:0}}};
}

test('Ouvrir le dashboard n’envoie aucune commande et aucun sélecteur n’existe',()=>{
  const app=dashboard();app.receive(snapshot());assert.equal(app.requests.length,0);
  const html=fs.readFileSync(path.join(__dirname,'../server/control-dashboard/fastapi-dashboard/static/index.html'),'utf8');
  assert.doesNotMatch(html,/<select\b/i);
});

test('Demande manuelle : confirmation, annulation sans changement, reprise sans mouvement implicite',async()=>{
  const app=dashboard(request=>request.url==='/command/move'?{ok:false,data:{detail:{confirmation_required:true,active:'exploration',revision:4}}}:{ok:true,data:{ok:true}});
  app.receive(snapshot());app.run('startControl("forward")');await app.flush();
  assert.equal(app.get('takeover-dialog').open,true);
  assert.equal(app.requests.length,1);
  app.get('takeover-dialog').close();
  assert.equal(app.requests.length,1); // annulation : aucune reprise.
  app.run('startControl("forward")');await app.flush();
  await app.get('takeover-confirm').listeners.click();
  assert.equal(app.requests.at(-1).url,'/command/takeover');
  assert.equal(app.requests.at(-1).body.revision,4);
  assert.equal(app.requests.filter(r=>r.url==='/command/move').length,2);
  assert.equal(app.get('takeover-dialog').open,false);
});

test('Perte de focus arrête le maintien et une réponse manuelle met à jour la révision',async()=>{
  const app=dashboard();app.receive(snapshot('manual'));
  app.run('startControl("forward")');await app.flush();
  app.window.listeners.blur();await app.flush();
  assert.deepEqual(app.requests.map(r=>r.body.direction),['forward','stop']);
  assert.equal(app.requests[1].body.revision,1);
});

test('Les deltas ne redessinent pas une carte inchangée',()=>{
  const app=dashboard();app.receive(snapshot());const initial=app.renders();
  app.receive({type:'delta',state:{battery_v:3.7}});assert.equal(app.renders(),initial);
  app.receive({type:'delta',state:{},steps_append:[{event_id:1,x:0,y:1,heading:0,action:'moved_forward'}]});
  assert.equal(app.renders(),initial+1);assert.equal(app.get('position').textContent,'0 / 1');
  app.receive({type:'delta',state:{steps:[]}});assert.equal(app.get('position').textContent,'— / —');
});

test('Une interruption de position et une erreur de modèle sont visibles',()=>{
  const app=dashboard();app.receive(snapshot());
  app.receive({type:'delta',state:{status:{position_valid:false},fly:{status:'error',error:'Cache absent',steps:0}}});
  assert.match(app.get('position-warning').textContent,/Position incertaine/);
  assert.equal(app.get('fly-error').hidden,false);assert.match(app.get('fly-error').textContent,/Cache absent/);
});

test('L’arrêt général n’attend pas une requête de déplacement suspendue',async()=>{
  let finish;
  const app=dashboard(request=>request.url==='/command/move'?new Promise(resolve=>finish=resolve):{ok:true,data:{ok:true}});
  app.receive(snapshot('manual'));app.run('startControl("forward")');await Promise.resolve();await Promise.resolve();
  await app.run('stopAll()');
  assert.ok(app.requests.some(r=>r.url==='/command/stop'));
  finish({ok:true,data:{ok:true,revision:0}});
});


test('Un ancien serveur sans control est détecté sans TypeError ni mouvement',async()=>{
  const app=dashboard();const old=snapshot();delete old.state.control;delete old.state.protocol;
  app.receive(old);app.run('startControl("forward")');await app.flush();
  assert.equal(app.requests.length,0);
  assert.equal(app.get('compatibility-notice').hidden,false);
  assert.match(app.get('compatibility-notice').textContent,/même version/);
  assert.equal(app.get('fly-action').disabled,true);
  await app.run('stopAll()');
  assert.equal(app.requests[0].url,'/command/mode');assert.equal(app.requests[0].body.mode,'idle');
});

test('Une route absente affiche un diagnostic de version explicite',async()=>{
  const app=dashboard(()=>({ok:false,status:404,data:{detail:'Not Found'}}));app.receive(snapshot());
  await app.get('fly-action').listeners.click();
  assert.match(app.get('toast').textContent,/interface et le serveur/);
  assert.equal(app.get('compatibility-notice').hidden,false);
  assert.equal(app.get('fly-action').disabled,true);
});

test('Le contrôle exploration appartient à la carte et le laboratoire a sa navigation',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../server/control-dashboard/fastapi-dashboard/static/index.html'),'utf8');
  assert.match(html,/<div class="map-actions"><button[^>]+id="exploration-action"/);
  assert.equal((html.match(/id="exploration-action"/g)||[]).length,1);
  assert.match(html,/href="\/fly"/);
});

test('Un neurone sélectionné conserve son identité pendant les mises à jour',()=>{
  const app=dashboard();app.receive(snapshot());
  const frame=value=>({type:'delta',state:{fly:{status:'ready',steps:1,sensory:{L:[{id:'24605',type:'LPLC2',side:'L',value}],R:[]}}}});
  app.receive(frame(.2));const dot=app.get('neurons-left').children[0];dot.listeners.click();
  assert.match(app.get('selected-neuron').textContent,/24605.*0.2000/);
  app.receive(frame(.8));assert.equal(app.get('neurons-left').children[0],dot);
  assert.match(app.get('selected-neuron').textContent,/24605.*0.8000/);
});
