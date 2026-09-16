// Parcours du chat réel : quota, choix explicite d'Ollama et absence de rejeu.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');

function assistant(switchResponse = {ok:true}) {
  const nodes = new Map(), requests = [];
  const config = {provider:'gemini', gemini_model:'test', ollama_model:'qwen3:4b', ollama_enabled:true, ollama_kind:'managed', ollama_url:'http://ollama:11434'};
  function element() {
    return {hidden:false, disabled:false, value:'', textContent:'', children:[], listeners:{},
      classList:{toggle(){}}, append(...items){this.children.push(...items);}, replaceChildren(...items){this.children=items;},
      querySelectorAll(){return [];}, addEventListener(name,fn){this.listeners[name]=fn;},
      setAttribute(){}, removeAttribute(){}, focus(){}, showModal(){this.open=true;}, close(){this.open=false;}};
  }
  const get = id => {if (!nodes.has(id)) nodes.set(id,element()); return nodes.get(id);};
  get('assistant-fallback').hidden = true;
  const document = {getElementById:get, createElement:element, body:element(), querySelectorAll:()=>[],
    querySelector:selector=>get(selector)};
  const failure = {code:'quota_exceeded', provider:'gemini', suggested_provider:'ollama'};
  const events = [{type:'error', text:'Quota atteint.', ...failure}, {type:'message', role:'assistant', text:'Quota atteint.', error:failure}, {type:'done'}];
  const context = vm.createContext({document, crypto:webcrypto, sessionStorage:{getItem(){},setItem(){}}, TextDecoder, Uint8Array, setTimeout, clearTimeout,
    fetch:async (url,options={}) => {
      requests.push({url, options});
      if (url === '/static/assistant.html') return {ok:true,text:async()=>'<aside></aside>'};
      if (url === '/assistant/chat') {
        let sent=false;
        return {ok:true,headers:{get:()=> 'application/x-ndjson'}, body:{getReader:()=>({read:async()=>{
          if (sent) return {done:true}; sent=true;
          return {value:Buffer.from(events.map(e=>JSON.stringify(e)).join('\n')+'\n'),done:false};
        }})}};
      }
      if (url === '/assistant/switch-to-ollama') {
        if (!switchResponse.ok) return {ok:false,json:async()=>({detail:'Ollama est indisponible.'})};
        config.provider='ollama';
        return {ok:true,json:async()=>({config:{...config},message:'Ollama est sélectionné. Envoyez une nouvelle demande.'})};
      }
      if (url === '/assistant/installation') return {ok:true,json:async()=>({host:{system:'Linux'},available:false})};
      if (url.startsWith('/assistant/history')) return {ok:true,json:async()=>({messages:[]})};
      return {ok:true,json:async()=>({...config})};
    }});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../server/control-dashboard/fastapi-dashboard/static/assistant.js'),'utf8'),context);
  const flush = async () => { for(let i=0;i<4;i++) await new Promise(resolve=>setImmediate(resolve)); };
  return {get,requests,async open(){await get('assistant-launch').listeners.click();},async send(){
    get('assistant-input').value='Tourne de 70 degrés à droite';
    get('assistant-chat-form').listeners.submit({preventDefault(){}}); await flush();
  }};
}

test('Quota Gemini : le chat propose Ollama sans changer de moteur ni rejouer la demande', async()=>{
  const app=assistant(); await app.open(); await app.send();
  assert.equal(app.get('assistant-fallback').hidden,false);
  assert.equal(app.get('assistant-fallback-switch').disabled,false);
  assert.equal(app.requests.filter(r=>r.url==='/assistant/switch-to-ollama').length,0);
  assert.match(app.get('assistant-engine').textContent,/Gemini/);
  await app.get('assistant-fallback-switch').listeners.click();
  assert.equal(app.get('assistant-fallback').hidden,true);
  assert.match(app.get('assistant-engine').textContent,/Ollama/);
  assert.equal(app.requests.filter(r=>r.url==='/assistant/chat').length,1);
});

test('Ollama indisponible : le chat conserve Gemini et permet de configurer Ollama', async()=>{
  const app=assistant({ok:false}); await app.open(); await app.send();
  await app.get('assistant-fallback-switch').listeners.click();
  assert.equal(app.get('assistant-fallback').hidden,false);
  assert.match(app.get('assistant-fallback-text').textContent,/indisponible/);
  assert.match(app.get('assistant-engine').textContent,/Gemini/);
  assert.equal(app.get('assistant-fallback-switch').disabled,false);
  assert.equal(app.requests.filter(r=>r.url==='/assistant/chat').length,1);
});
