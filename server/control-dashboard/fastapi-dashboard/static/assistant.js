/* Le chat n'accède jamais directement aux fournisseurs, au broker ou à Docker. */
(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const labels = {get_robot_state:'Lecture des capteurs', move_robot:'Déplacement', turn_robot:'Rotation approximative', set_robot_speed:'Réglage de la vitesse', set_autonomy:'Comportement autonome', stop_robot:'Arrêt du robot'};
  const pendingActions = new Map();
  let ready = false, config = null, installation = null, busy = false, managementBusy = false, poll = null, session;
  try { session = sessionStorage.getItem('elio-chat-session'); } catch {}
  if (!session) {
    const bytes = crypto.getRandomValues(new Uint8Array(24));
    session = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
    try { sessionStorage.setItem('elio-chat-session', session); } catch {}
  }
  async function api(path, method = 'GET', data) {
    const response = await fetch('/assistant' + path, {method, headers:{'Content-Type':'application/json','X-Elio-Assistant':'1'}, ...(data === undefined ? {} : {body:JSON.stringify(data)})});
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'La demande n’a pas été acceptée.');
    return value;
  }
  function status(text, error = false) {
    el('assistant-config-status').textContent = text;
    el('assistant-config-status').classList.toggle('error', error);
  }
  function resizeInput() {
    const input = el('assistant-input');
    if (!input || el('assistant-panel').hidden) return;
    input.style.height = 'auto';
    input.style.height = `${input.scrollHeight}px`;
  }
  function scroll() { const box = el('assistant-messages'); box.scrollTop = box.scrollHeight; }
  function message(role, text) {
    el('assistant-welcome').hidden = true;
    const item = document.createElement('div'); item.className = 'assistant-message ' + role;
    const author = document.createElement('span'); author.className = 'message-author'; author.textContent = role === 'user' ? 'Vous' : 'ElioBot';
    const content = document.createElement('div'); content.textContent = text;
    item.append(author, content); el('assistant-messages').append(item); scroll();
  }
  function action(event) {
    el('assistant-welcome').hidden = true;
    const pending = event.status !== 'running' && pendingActions.get(event.name);
    const detail = pending || document.createElement('details'); detail.className = 'assistant-action' + (event.status === 'error' ? ' error' : '');
    const summary = document.createElement('summary');
    summary.textContent = `${event.status === 'running' ? '◌' : event.status === 'error' ? '!' : '✓'} ${labels[event.name] || event.name}${event.status === 'running' ? '…' : ''}`;
    const content = document.createElement('pre'); content.textContent = JSON.stringify(event.result || event.arguments || {}, null, 2);
    detail.replaceChildren(summary, content);
    if (!pending) el('assistant-messages').append(detail);
    if (event.status === 'running') pendingActions.set(event.name, detail); else pendingActions.delete(event.name);
    scroll();
  }
  function setBusy(value) {
    busy = value;
    el('assistant-send').disabled = value;
    el('assistant-input').disabled = value;
    el('assistant-cancel').hidden = !value;
    el('assistant-clear').disabled = value;
    el('assistant-save').disabled = value;
    el('assistant-test').disabled = value;
    el('assistant-fallback-switch').disabled = value;
    el('assistant-fallback-settings').disabled = value;
  }
  function fallback(error) {
    el('assistant-fallback').hidden = !(error?.suggested_provider === 'ollama' && config.provider === 'gemini');
    el('assistant-fallback-text').textContent = 'Gemini a atteint une limite. Vous pouvez patienter ou passer à Ollama. Les actions précédentes ne seront pas relancées.';
  }
  function engine() {
    el('assistant-engine').textContent = config.provider === 'gemini' ? `Gemini · ${config.gemini_model}` : `Ollama · ${config.ollama_model}${config.ollama_enabled ? '' : ' · déconnecté'}`;
  }
  async function loadHistory() {
    const data = await api('/history/' + session);
    pendingActions.clear();
    el('assistant-messages').querySelectorAll('.assistant-message,.assistant-action').forEach(item => item.remove());
    el('assistant-welcome').hidden = data.messages.length > 0;
    for (const item of data.messages) {
      for (const tool of item.actions || []) action({name:tool.tool, result:tool.result, status:tool.result.error ? 'error' : 'done'});
      message(item.role, item.text);
    }
    fallback(data.messages.at(-1)?.error);
  }
  async function send(text) {
    if (busy || !text.trim()) return;
    fallback(null); message('user', text.trim()); el('assistant-input').value = ''; resizeInput(); setBusy(true);
    el('assistant-status').textContent = 'Connexion au modèle…';
    try {
      const response = await fetch('/assistant/chat', {method:'POST', headers:{'Content-Type':'application/json','X-Elio-Assistant':'1'}, body:JSON.stringify({session, message:text.trim()})});
      if (!response.ok) { const value = await response.json(); throw new Error(value.detail || 'Demande refusée.'); }
      if (response.headers.get('content-type').includes('application/json')) {
        const value = await response.json(); message('assistant', value.text); return;
      }
      const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '', doneReceived = false;
      function event(value) {
        if (value.type === 'status' || value.type === 'error') el('assistant-status').textContent = value.text;
        if (value.type === 'action') action(value);
        if (value.type === 'message') { message('assistant', value.text); fallback(value.error); }
        if (value.type === 'done') doneReceived = true;
      }
      while (true) {
        const {value, done} = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), {stream:!done});
        const lines = buffer.split('\n'); buffer = lines.pop();
        for (const line of lines) if (line.trim()) event(JSON.parse(line));
        if (done) { if (buffer.trim()) event(JSON.parse(buffer)); break; }
      }
      if (!doneReceived) throw new Error('Connexion interrompue. Vérifier l’état du robot avant de recommencer.');
    } catch (error) { message('assistant', error.message); }
    finally {
      for (const name of [...pendingActions.keys()]) action({name, status:'error', result:{message:'Demande interrompue ; consulter l’état du robot.'}});
      setBusy(false); el('assistant-status').textContent = 'Prêt à discuter.'; el('assistant-input').focus();
    }
  }
  function formProvider() { return document.querySelector('input[name="assistant-provider"]:checked').value; }
  function showProvider() {
    const ollama = formProvider() === 'ollama';
    el('assistant-gemini-fields').hidden = ollama;
    el('assistant-ollama-fields').hidden = !ollama;
    el('assistant-ollama-management').hidden = !ollama;
    el('assistant-gemini-model').required = !ollama;
    el('assistant-ollama-model').required = ollama;
    el('assistant-model-list').replaceChildren();
    showKind();
  }
  function showKind() {
    const managed = el('assistant-ollama-kind').value === 'managed';
    el('assistant-url-field').hidden = managed;
    el('assistant-managed-controls').hidden = !managed;
    el('assistant-native-note').hidden = managed;
    el('assistant-uninstall').hidden = !managed;
    if (!managed && el('assistant-ollama-url').value === 'http://ollama:11434') el('assistant-ollama-url').value = 'http://host.docker.internal:11434';
  }
  function platformGuide() {
    const system = el('assistant-host-system').value;
    const guides = {
      Darwin:['Installer l’application Ollama sur le Mac pour utiliser le GPU Apple Silicon. Le conteneur du dashboard peut la contacter via host.docker.internal. Configurer l’écoute réseau d’Ollama pour autoriser cette connexion. Pour désinstaller une application installée séparément, suivre la section de désinstallation du guide officiel ; les modèles se gèrent séparément.', 'https://docs.ollama.com/macos'],
      Windows:['Installer Ollama avec l’installateur Windows. L’application tourne en arrière-plan. Depuis le dashboard Docker, utiliser host.docker.internal et configurer l’écoute réseau ainsi que le pare-feu. Pour désinstaller : Paramètres → Applications → Ollama. Les modèles conservés peuvent être retirés séparément.', 'https://docs.ollama.com/windows'],
      Linux:['Sur Linux ou Raspberry Pi avec un système 64 bits, le conteneur géré par ElioBot permet l’installation et la suppression depuis cet écran. Commencer par le CPU ; NVIDIA nécessite les pilotes et NVIDIA Container Toolkit. Une installation native existante peut aussi être connectée.', 'https://docs.ollama.com/linux']
    };
    el('assistant-platform-guide').textContent = guides[system][0]; el('assistant-platform-link').href = guides[system][1];
  }
  function populate() {
    document.querySelector(`input[name="assistant-provider"][value="${config.provider}"]`).checked = true;
    el('assistant-gemini-model').value = config.gemini_model; el('assistant-ollama-model').value = config.ollama_model;
    el('assistant-ollama-url').value = config.ollama_url; el('assistant-ollama-kind').value = config.ollama_kind;
    el('assistant-key').value = '';
    el('assistant-key-status').textContent = config.gemini_key_configured ? `Clé détectée (${config.gemini_key_source}). Laisser vide pour la conserver.` : 'Aucune clé détectée.';
    showProvider(); engine();
  }
  async function save() {
    const values = {provider:formProvider(), gemini_model:el('assistant-gemini-model').value.trim(), ollama_model:el('assistant-ollama-model').value.trim(), ollama_kind:el('assistant-ollama-kind').value, ollama_url:el('assistant-ollama-url').value.trim(), ollama_enabled:true};
    if (el('assistant-key').value.trim()) values.gemini_key = el('assistant-key').value.trim();
    config = await api('/config', 'POST', values); populate(); status('Réglages enregistrés.');
    if (config.provider === 'ollama') fallback(null);
  }
  async function openSettings(provider) {
    try {
      config = await api('/config'); populate(); status('');
      if (provider) { document.querySelector(`input[name="assistant-provider"][value="${provider}"]`).checked = true; showProvider(); }
      el('assistant-settings').showModal(); await installationState();
    } catch (error) { status(error.message, true); }
  }
  async function switchToOllama() {
    if (busy || managementBusy) return;
    setBusy(true); el('assistant-fallback-text').textContent = 'Vérification d’Ollama et du modèle installé…';
    try {
      const result = await api('/switch-to-ollama', 'POST', {});
      config = result.config; populate(); fallback(null);
      message('assistant', result.message);
    } catch (error) { el('assistant-fallback-text').textContent = error.message; }
    finally { setBusy(false); }
  }
  async function test() {
    await save(); status('Vérification de la connexion…');
    const result = await api('/models');
    el('assistant-model-list').replaceChildren(...result.models.map(model => { const option = document.createElement('option'); option.value = model.name; option.label = model.size ? `${(model.size / 1e9).toFixed(1)} Go` : model.label || model.name; return option; }));
    status(`${result.message} ${result.models.length} modèle(s) disponible(s).`);
  }
  async function installationState() {
    installation = await api('/installation');
    const host = installation.host || {};
    const systemNames = {Darwin:'macOS', Linux:host.raspberry_pi ? 'Raspberry Pi / Linux' : 'Linux', Windows:'Windows', unknown:'Hôte non identifié'};
    const memory = installation.docker_memory_bytes ? ` · ${(installation.docker_memory_bytes / 2**30).toFixed(1)} Go alloués à Docker` : '';
    const recommendation = host.ollama_recommendation === 'native' ? ' Application native recommandée sur ce système.' : '';
    el('assistant-host-info').textContent = `${systemNames[host.system] || host.system || 'Hôte non identifié'}${host.architecture ? ' · ' + host.architecture : ''}${memory}.${recommendation} ${installation.message || ''}`;
    if (!config.configured && host.ollama_recommendation === 'native') { el('assistant-ollama-kind').value = 'native'; showKind(); }
    if (['Darwin','Linux','Windows'].includes(host.system)) el('assistant-host-system').value = host.system;
    platformGuide();
    const names = {running:'Démarré', exited:'Arrêté', created:'Prêt à démarrer', not_installed:'Non installé'};
    el('assistant-install-status').textContent = installation.available ? names[installation.status] || installation.status : 'Gestion indisponible';
    el('assistant-storage').textContent = installation.data_bytes == null ? 'Espace occupé par les modèles gérés : non mesuré.' : `Modèles gérés : ${(installation.data_bytes / 1e9).toFixed(2)} Go sur disque.`;
    document.querySelectorAll('#assistant-managed-controls button').forEach(button => button.disabled = !installation.available || managementBusy);
    el('assistant-uninstall').disabled = !installation.available || managementBusy;
    const job = installation.model_job || {};
    el('assistant-job').hidden = !job.status || job.status === 'idle';
    el('assistant-job-text').textContent = job.message || '';
    const progress = el('assistant-job-progress');
    if (job.total && job.completed != null) { progress.max = job.total; progress.value = job.completed; } else progress.removeAttribute('value');
    return job.status === 'running';
  }
  function confirmAction(title, copy, erase = false) {
    const dialog = el('assistant-confirm');
    el('assistant-confirm-title').textContent = title; el('assistant-confirm-copy').textContent = copy;
    el('assistant-erase-label').hidden = !erase; el('assistant-erase-data').checked = false; dialog.returnValue = '';
    return new Promise(resolve => {
      dialog.addEventListener('close', () => resolve({confirmed:dialog.returnValue === 'confirm', erase:el('assistant-erase-data').checked}), {once:true});
      dialog.showModal();
    });
  }
  async function manage(actionName) {
    if (managementBusy) return;
    let confirmation = {confirmed:true, erase:false};
    const external = el('assistant-ollama-kind').value !== 'managed';
    if (actionName === 'uninstall') confirmation = await confirmAction('Désinstaller Ollama ?', `${el('assistant-storage').textContent} Le conteneur créé par ElioBot sera arrêté et supprimé. Les modèles seront conservés sauf si vous cochez l’option ci-dessous. Le dashboard restera disponible.`, true);
    if (actionName === 'delete') confirmation = await confirmAction('Supprimer ce modèle ?', `Le modèle ${el('assistant-ollama-model').value} sera supprimé de l’instance configurée${external ? ', même si d’autres applications l’utilisent' : ''}. Il faudra le télécharger à nouveau pour l’utiliser.`);
    if (actionName === 'pull' && external) confirmation = await confirmAction('Télécharger sur cette instance ?', 'Le téléchargement utilisera le disque de la machine Ollama configurée, qui peut être partagée avec d’autres applications.');
    if (!confirmation.confirmed) return;
    managementBusy = true;
    document.querySelectorAll('[data-ollama-action]').forEach(button => button.disabled = true);
    el('assistant-save').disabled = true; el('assistant-test').disabled = true;
    try {
      if (busy) await api('/cancel', 'POST', {});
      // Conserver les réglages sauvegardés pendant une désinstallation/déconnexion.
      if (['start','pull','delete'].includes(actionName)) await save();
      status(actionName === 'start' ? 'Installation / démarrage en cours. Le premier téléchargement peut prendre quelques minutes…' : 'Opération en cours…');
      const result = await api('/ollama/' + actionName, 'POST', {model:el('assistant-ollama-model').value.trim(), gpu:el('assistant-gpu').value, confirm:confirmation.confirmed, erase_data:confirmation.erase, confirm_external:external});
      status(result.message || 'Opération lancée.'); config = await api('/config'); engine();
      await installationState();
      if (result.accepted) {
        clearTimeout(poll);
        async function follow() { try { if (await installationState()) poll = setTimeout(follow, 1500); } catch (error) { status(error.message, true); } }
        poll = setTimeout(follow, 1000);
      }
    } catch (error) { status(error.message, true); }
    finally { managementBusy = false; document.querySelectorAll('[data-ollama-action]').forEach(button => button.disabled = false); el('assistant-save').disabled = busy; el('assistant-test').disabled = busy; }
  }
  async function init() {
    if (ready) return;
    const response = await fetch('/static/assistant.html');
    if (!response.ok) throw new Error('Impossible de charger le chat. Recharger le dashboard.');
    const template = document.createElement('template'); template.innerHTML = await response.text(); document.body.append(template.content);
    ready = true;
    el('assistant-close').addEventListener('click', () => { el('assistant-panel').hidden = true; el('assistant-launch').hidden = false; el('assistant-launch').setAttribute('aria-expanded','false'); el('assistant-launch').focus(); });
    el('assistant-input').addEventListener('input', resizeInput);
    window.addEventListener('resize', resizeInput);
    el('assistant-chat-form').addEventListener('submit', event => { event.preventDefault(); send(el('assistant-input').value); });
    el('assistant-input').addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); send(el('assistant-input').value); } });
    document.querySelectorAll('.assistant-suggestions button').forEach(button => button.addEventListener('click', () => send(button.textContent)));
    el('assistant-cancel').addEventListener('click', () => api('/cancel','POST',{}).catch(error => message('assistant',error.message)));
    el('assistant-stop').addEventListener('click', async () => { try { const response = await fetch('/command/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}); if (!response.ok) throw new Error(); el('assistant-status').textContent = 'Commande d’arrêt envoyée.'; } catch { message('assistant','Impossible de confirmer l’envoi de l’arrêt. Vérifier la connexion au robot.'); } });
    el('assistant-clear').addEventListener('click', async () => { try { await api('/history/' + session, 'DELETE'); await loadHistory(); } catch (error) { message('assistant', error.message); } });
    el('assistant-settings-open').addEventListener('click', () => openSettings());
    el('assistant-fallback-switch').addEventListener('click', switchToOllama);
    el('assistant-fallback-settings').addEventListener('click', () => openSettings('ollama'));
    el('assistant-settings-close').addEventListener('click', () => el('assistant-settings').close());
    document.querySelectorAll('input[name="assistant-provider"]').forEach(input => input.addEventListener('change',showProvider));
    el('assistant-ollama-kind').addEventListener('change',showKind);
    el('assistant-host-system').addEventListener('change',platformGuide);
    el('assistant-config-form').addEventListener('submit', async event => { event.preventDefault(); try { await save(); } catch(error) { status(error.message,true); } });
    el('assistant-test').addEventListener('click', async () => { try { await test(); } catch(error) { status(error.message,true); } });
    document.querySelectorAll('[data-ollama-action]').forEach(button => button.addEventListener('click', () => manage(button.dataset.ollamaAction)));
  }
  el('assistant-launch').addEventListener('click', async () => {
    try {
      await init(); config = await api('/config'); populate(); await loadHistory();
      el('assistant-panel').hidden = false; el('assistant-launch').hidden = true; el('assistant-launch').setAttribute('aria-expanded','true'); resizeInput(); el('assistant-input').focus();
    } catch(error) { if (typeof notify === 'function') notify(error.message); }
  });
})();
