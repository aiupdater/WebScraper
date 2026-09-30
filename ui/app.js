'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const number = value => Number(value || 0).toLocaleString('cs-CZ');
  const state = {ready:false, running:false, starting:false, dbBusy:false, stopping:false,
    groupsLoaded:false, settings:{}, records:[], emails:new Set(), skipped:new Set(),
    counts:{profiles:0, emails:0, skipped:0, errors:0}, started:null, activeStage:0,
    manual:false, tab:'results', total:0, logs:[], lastError:'', detail:null, resume:false,
    hasStoppedData:false, isCompleted:false, categories:[], selected:new Set(), categoryBusy:false};
  let api, polling = false, initializing = false, renderTimer, toastTimer, folderTimer, folderInfoRequest = 0;

  function notice(title, text) {
    $('notice-title').textContent = title;
    $('notice-text').textContent = text;
    if (!$('notice-dialog').open) $('notice-dialog').showModal();
  }
  function toast(text) {
    clearTimeout(toastTimer);
    $('toast').textContent = text;
    $('toast').hidden = false;
    toastTimer = setTimeout(() => $('toast').hidden = true, 2600);
  }
  async function call(name, ...args) {
    if (!api) return {ok:false, message:'Rozhraní zatím není připojené k Pythonu.'};
    try { return await api[name](...args); }
    catch (_) { return {ok:false, message:'Operaci se nepodařilo dokončit. Ověřte, že aplikace stále běží.'}; }
  }
  function runStatus(text, tone='blue') {
    $('run-status').textContent = text;
    $('run-status').className = 'badge badge-' + tone;
  }
  function updateVisibility() {
    const direct = $('portal').value === '11880';
    const portalHelp = $('portal-help');
    if (portalHelp) portalHelp.textContent = direct ? 'E-maily se získávají přímo z profilů firem.' : 'E-maily se hledají na firemních webech.';
    for (const [stage, text] of [[2, direct ? 'Načtení profilů firem' : 'Odkazů na firemní web'], [4, direct ? 'Zpracování e-mailů z profilů' : 'Prohledáno stránek']]) {
      document.querySelector(`[data-stage="${stage}"] h3`).textContent = text;
      document.querySelector(`[data-stage="${stage}"] progress`).setAttribute('aria-label', text);
    }
    const mysql = $('destination').value === 'mysql';
    $('group-field').hidden = !mysql;
    if ($('database-panel')) $('database-panel').hidden = !(mysql || $('skip-existing').checked);
    if ($('connect')) $('connect').hidden = !(mysql || $('skip-existing').checked);
    $('browser-field').hidden = $('wlw-mode').value !== 'browser';
    $('group').disabled = !mysql || !state.groupsLoaded || state.running || state.dbBusy;
  }
  function controls() {
    const busy = state.running || state.stopping || state.dbBusy || state.starting || state.categoryBusy;
    for (const id of ['source-fields','destination-fields','folder-fields']) $(id).disabled = busy;

    const hasPausedData = !state.running && (state.resume || state.hasStoppedData) && !state.isCompleted;

    if (state.running) {
      $('start').hidden = true;
      $('stop').hidden = false;
      $('stop').disabled = state.stopping;
      if ($('prepare-new')) $('prepare-new').hidden = true;
      if ($('resume-run')) $('resume-run').hidden = true;
      if ($('finish-run')) $('finish-run').hidden = true;
      if ($('discard-run')) $('discard-run').hidden = true;
    } else if (state.isCompleted) {
      $('start').hidden = true;
      $('stop').hidden = true;
      if ($('resume-run')) $('resume-run').hidden = true;
      if ($('finish-run')) $('finish-run').hidden = true;
      if ($('discard-run')) $('discard-run').hidden = true;
      if ($('prepare-new')) {
        $('prepare-new').hidden = false;
        $('prepare-new').disabled = busy;
      }
    } else if (hasPausedData) {
      if ($('prepare-new')) $('prepare-new').hidden = true;
      $('start').hidden = true;
      $('stop').hidden = true;
      if ($('resume-run')) {
        $('resume-run').hidden = false;
        $('resume-run').disabled = busy;
      }
      if ($('finish-run')) {
        $('finish-run').hidden = false;
        $('finish-run').disabled = busy;
      }
      if ($('discard-run')) {
        $('discard-run').hidden = false;
        $('discard-run').disabled = busy;
      }
    } else {
      if ($('prepare-new')) $('prepare-new').hidden = true;
      $('start').hidden = false;
      $('start').disabled = busy || !state.ready || !state.selected.size || ($('destination').value === 'mysql' && !state.groupsLoaded);
      $('stop').hidden = true;
      if ($('resume-run')) $('resume-run').hidden = true;
      if ($('finish-run')) $('finish-run').hidden = true;
      if ($('discard-run')) $('discard-run').hidden = true;
    }
    if ($('discard-saved')) $('discard-saved').hidden = true;
    updateVisibility();
  }
  function updateStats() {
    Object.entries(state.counts).forEach(([key,value]) => $('stat-' + key).textContent = number(value));
  }
  function config() {
    return {portal:$('portal').value, categories:state.categories.filter(value=>state.selected.has(value)), max_pages:$('pages').value, start_page:$('start-page').value,
      workers:$('workers').value, delay:$('delay').value, output_mode:$('destination').value,
      skip_existing:$('skip-existing').checked, save_best_email:$('save-best-email').checked, group_id:$('group').value,
      wlw_mode:$('wlw-mode').value, browser_channel:$('browser').value, folder:$('folder').value};
  }
  function categorySummary() {
    const selected = state.categories.filter(value=>state.selected.has(value));
    $('category-summary').textContent = selected.length ? selected.join(', ') : 'Vyberte kategorie';
    $('category-help').textContent = selected.length ? `Vybráno: ${selected.length} z ${state.categories.length} · sběr postupně.` : 'Pro spuštění sběru vyberte alespoň jednu kategorii.';
    controls();
  }
  function renderCategories() {
    $('category').replaceChildren();
    state.categories.forEach(value=>{
      const row=document.createElement('div'), label=document.createElement('label');
      row.className='category-row';
      const checkbox=document.createElement('input'); checkbox.type='checkbox'; checkbox.checked=state.selected.has(value);
      checkbox.addEventListener('change',()=>{if(checkbox.checked)state.selected.add(value);else state.selected.delete(value);categorySummary();});
      const name=document.createElement('span'); name.textContent=value; label.append(checkbox,name);
      const remove=document.createElement('button'); remove.type='button'; remove.className='btn btn-quiet'; remove.textContent='×';
      remove.setAttribute('aria-label','Smazat kategorii '+value);
      remove.addEventListener('click',()=>saveCategories(state.categories.filter(item=>item!==value)));
      row.append(label,remove); $('category').append(row);
    });
    categorySummary();
  }
  async function saveCategories(values, added) {
    if(state.running || state.starting || state.dbBusy || state.categoryBusy) return;
    state.categoryBusy=true; controls();
    const result=await call('save_categories',values);
    if(result.ok) {
      state.categories=result.categories;
      state.selected=new Set([...state.selected].filter(value=>state.categories.includes(value)));
      if(added) {state.selected.add(added); $('new-category').value='';}
      renderCategories();
    } else notice('Kategorie se nepodařilo uložit',result.message);
    state.categoryBusy=false; controls();
  }
  function addCategory() {
    const value=$('new-category').value.trim();
    if(!value) { $('new-category').focus(); return; }
    saveCategories([...state.categories,value],value);
  }
  function resetRun(isResume = false) {
    if (!isResume) {
      state.records = []; state.emails.clear(); state.skipped.clear(); state.total = 0;
      state.counts = {profiles:0,emails:0,skipped:0,errors:0}; state.lastError = '';
      state.activeStage = 0;
      state.logs = [];
      $('log-panel').textContent = '';
      document.querySelectorAll('.step').forEach(step => {
        step.classList.remove('active','done'); step.querySelector('progress').value = 0;
        step.querySelector('p').textContent = 'Čeká';
      });
    }
    state.isCompleted = false;
    state.manual = false; state.stopping = false;
    state.started = Date.now(); state.running = true;
    state.hasStoppedData = false;
    $('search').value = ''; $('result-filter').value = 'all'; $('verification').hidden = true;
    $('current-request').textContent = isResume ? 'Pokračuji ve sběru…' : 'Připravuji sběr…';
    $('activity-dot').className = 'status-dot active';
    $('footer-message').textContent = 'Výsledky se ukládají průběžně. Běh lze kdykoliv zastavit.';
    runStatus('Probíhá sběr'); updateStats(); changeTab('results'); render();
    appendLog((isResume ? 'Pokračování' : 'Nový sběr') + ' · ' + $('portal').selectedOptions[0].textContent + ' · ' + config().categories.join(', '));
  }
  async function prepareNewRun() {
    if (state.running || state.starting || state.dbBusy) return;
    state.starting = true; controls();
    const result = await call('new_folder');
    state.starting = false;
    if (!result.ok || !result.folder) {
      controls();
      notice('Nový sběr se nepodařilo připravit', result.message || 'Nepodařilo se vytvořit novou složku běhu.');
      return;
    }
    $('folder').value = result.folder;
    state.isCompleted = false;
    state.resume = false;
    state.hasStoppedData = false;
    state.records = [];
    state.emails.clear();
    state.skipped.clear();
    state.total = 0;
    state.counts = { profiles: 0, emails: 0, skipped: 0, errors: 0 };
    state.lastError = '';
    state.activeStage = 0;
    state.started = null;
    state.stopping = false;
    state.manual = false;
    state.logs = [];
    $('log-panel').textContent = '';

    document.querySelectorAll('.step').forEach(step => {
      step.classList.remove('active', 'done');
      const progress = step.querySelector('progress');
      if (progress) progress.value = 0;
      const text = step.querySelector('p');
      if (text) text.textContent = 'Čeká';
      step.title = '';
    });

    $('search').value = '';
    $('result-filter').value = 'all';
    $('verification').hidden = true;
    $('elapsed').textContent = '00:00';
    $('activity-dot').className = 'status-dot';
    runStatus('Připraveno', 'green');
    $('current-request').textContent = 'Připraveno na nový sběr.';
    $('current-request').title = '';
    $('footer-message').textContent = 'Připraveno. Zkontrolujte nastavení a klikněte na Spustit sběr.';

    updateStats();
    changeTab('results');
    render();

    toast('Vše vynulováno. Můžete nastavit a spustit nový sběr.');
    controls();
  }
  async function start() {
    if (state.running || state.starting || state.dbBusy || state.categoryBusy || !state.selected.size) return;
    const isResume = Boolean(state.resume || state.hasStoppedData);
    state.isCompleted = false;
    state.starting = true; controls();
    const result = await call('start_run', config());
    if (result.ok) { resetRun(isResume); $('folder').value = result.folder; folderInfo(); }
    else notice('Zkontrolujte nastavení', result.message);
    state.starting = false; controls();
  }
  async function stop() {
    if (state.stopping || !state.running) return;
    state.stopping = true; controls();
    runStatus('Zastavuji sběr', 'amber');
    $('footer-message').textContent = 'Zastavuji sběr a ukládám průběžný stav…';
    const result = await call('stop_run');
    if (!result.ok) { state.stopping = false; controls(); notice('Zastavení běhu', result.message); }
  }
  async function finishRun() {
    if (state.running || state.stopping || state.starting) return;
    state.stopping = true; controls();
    runStatus('Zpracovávám data', 'amber');
    $('footer-message').textContent = 'Zpracovávám dosud načtená data…';
    const result = await call('finish_run', config());
    if (!result.ok) { state.stopping = false; controls(); notice('Zpracování dat', result.message); return; }
    state.running = true; state.stopping = false; state.resume = false; state.hasStoppedData = false;
    state.started = Date.now(); $('activity-dot').className = 'status-dot active'; controls();
  }
  async function folderInfo() {
    const folder = $('folder').value;
    const request = ++folderInfoRequest;
    const result = await call('folder_info', folder);
    if (result.ok && request === folderInfoRequest && $('folder').value === folder) {
      if (['wlw','11880'].includes(result.portal) && !state.running) $('portal').value = result.portal;
      state.resume = Boolean(result.resume);
      if (result.resume) state.hasStoppedData = true;
      if (result.completed && !state.running) {
        state.isCompleted = true;
      } else if (!result.completed && !state.running && !result.resume) {
        state.isCompleted = false;
      }
      controls();
    }
  }
  async function discardSavedRun() {
    if (state.running || state.starting) return;
    if (!confirm('Opravdu zrušit tento běh a zahodit veškerá načtená data?')) return;
    state.starting = true; controls();
    const result = await call('discard_saved_run', $('folder').value);
    state.starting = false;
    if (!result.ok) { controls(); notice('Běh se nepodařilo zrušit', result.message); return; }
    state.resume = false; state.hasStoppedData = false; state.isCompleted = true;
    state.records = []; state.emails.clear(); state.skipped.clear(); state.total = 0;
    state.counts = {profiles:0,emails:0,skipped:0,errors:0};
    state.logs = []; $('log-panel').textContent = '';
    updateStats(); render();
    runStatus('Ukončeno','gray');
    $('current-request').textContent = 'Data běhu byla zahozena. Připravte nový sběr.';
    $('footer-message').textContent = 'Běh byl ukončen a data zahozena. Klikněte na „Připravit nový sběr“.';
    controls();
  }
  async function connect() {
    if (state.running || state.dbBusy) return;
    if (!state.settings.has_password) { openSettings(); return; }
    state.dbBusy = true; controls();
    if ($('db-status')) $('db-status').textContent = 'Připojuji a načítám skupiny…';
    if ($('db-dot')) $('db-dot').className = 'status-dot active';
    if ($('mysql-toggle')) $('mysql-toggle').title = 'Nastavení MySQL · Připojuji…';
    const result = await call('connect_database');
    if (!result.ok) {
      state.dbBusy = false; controls();
      if ($('db-dot')) $('db-dot').className = 'status-dot failed';
      if ($('db-status')) $('db-status').textContent = 'Připojení se nezdařilo';
      if ($('mysql-toggle')) $('mysql-toggle').title = 'Nastavení MySQL · Připojení se nezdařilo';
      notice('Připojení k EmailApp',result.message);
    }
  }
  async function openSettings() {
    for (const key of ['host','port','database','user']) $('db-'+key).value = state.settings[key] ?? '';
    $('db-tls').checked = state.settings.tls !== false; $('db-ca').value = state.settings.ca_file || '';
    $('db-password').value = '';
    $('db-password').placeholder = state.settings.has_password ? 'Ponechte prázdné pro stávající heslo' : 'Zadejte heslo';
    $('password-hint').textContent = 'Heslo se ukládá do místního nastavení připojení.';
    $('settings-error').hidden = true; $('ca-field').hidden = !$('db-tls').checked;
    updateSaveBestEmail();
    $('settings-dialog').showModal();
    const result = await call('settings_password');
    if(result.ok && $('settings-dialog').open && !$('db-password').value) $('db-password').value = result.password;
  }
  async function saveSettings(event) {
    event.preventDefault(); $('save-settings').disabled = true; $('settings-error').hidden = true;
    const values = {host:$('db-host').value, port:$('db-port').value, database:$('db-database').value,
      user:$('db-user').value, password:$('db-password').value, tls:$('db-tls').checked, ca_file:$('db-ca').value};
    const result = await call('save_settings',values);
    values.password = ''; $('db-password').value = ''; $('save-settings').disabled = false;
    if (!result.ok) { $('settings-error').textContent = result.message; $('settings-error').hidden = false; return; }
    state.settings = result.settings; state.groupsLoaded = false;
    $('group').replaceChildren(new Option('⚪ Bez skupiny (výchozí)','')); $('settings-dialog').close();
    updateGroupBadge();
    await connect();
  }
  function statusOf(record) {
    const d = record.data;
    if (d.delivery === 'PENDING') return ['Čeká na uložení','amber'];
    if (d.delivery === 'INSERTED') return ['Uloženo v EmailApp','green'];
    if (d.status === 'OK') return [record.stage === 2 ? 'Web nalezen' : 'E-mail nalezen','green'];
    return ({SKIPPED_EXISTING:['Již v databázi','gray'],ERROR:['Chyba','red'],PARTIAL:['Nedokončeno','amber'],
      REVIEW:['K ověření','amber'],NO_EMAIL:['Bez e-mailu','gray'],NO_WEBSITE:['Bez webu','gray']})[d.status] || [d.status || 'Čeká','gray'];
  }
  function matches(record) {
    const d = record.data, filter = $('result-filter').value;
    const emails = d.emails || (d.email ? [d.email] : []);
    if (filter === 'emails' && !emails.length) return false;
    if (filter === 'skipped' && d.status !== 'SKIPPED_EXISTING') return false;
    if (filter === 'review' && d.status !== 'REVIEW') return false;
    if (filter === 'errors' && !['ERROR','PARTIAL'].includes(d.status) && d.delivery !== 'PENDING') return false;
    return [record.url, ...emails, d.website, d.skipped_email, ...(d.skipped_existing||[]), ...(d.origins||[]).map(o=>o.category), statusOf(record)[0]]
      .join(' ').toLocaleLowerCase('cs').includes($('search').value.trim().toLocaleLowerCase('cs'));
  }
  function addText(parent, tag, text, className) {
    const el = document.createElement(tag); el.textContent = text ?? '';
    if (className) el.className = className;
    parent.append(el); return el;
  }
  function scheduleRender() { if (!renderTimer) renderTimer = setTimeout(render,100); }
  function render() {
    clearTimeout(renderTimer); renderTimer = null;
    const fragment = document.createDocumentFragment(), rows = state.records.filter(matches).slice().reverse();
    rows.forEach((record,index) => {
      const d = record.data, row = document.createElement('tr'); row.className = index%2 ? 'row-alt-dark' : 'row-alt-light';
      let host = record.url;
      try { host = new URL(record.url).hostname.replace(/^www\./,''); } catch (_) {}
      const siteCell = addText(row,'td',''); addText(siteCell,'span',host,'cell-value');
      addText(siteCell,'small',record.url.includes('11880.com/branchenbuch/') ? 'Profil 11880.com' : record.stage === 2 ? 'Profil WLW' : 'Firemní web','cell-meta'); siteCell.title = record.url;
      const emails = d.emails && d.emails.length ? d.emails.join(', ') : d.email;
      const value = emails || d.skipped_email || d.website || (d.skipped_existing||[]).join(', ') || '—';
      const valueCell = addText(row,'td',''); addText(valueCell,'span',value,'cell-value'); valueCell.title = value;
      const categories = [...new Set((d.origins||[]).map(o=>o.category).filter(Boolean))].join(', ') || '—';
      const categoryCell = addText(row,'td',''); addText(categoryCell,'span',categories,'cell-value'); categoryCell.title = categories;
      const statusCell = addText(row,'td',''), [title,tone] = statusOf(record);
      addText(statusCell,'span',title,'badge badge-'+tone);
      const action = addText(row,'td',''), detail = addText(action,'button','›','detail-icon');
      detail.type = 'button'; detail.setAttribute('aria-label','Detail: '+host);
      row.addEventListener('click',() => showDetail(record));
      detail.addEventListener('keydown',event => { if (event.key === 'Enter') { event.preventDefault(); showDetail(record); } });
      fragment.append(row);
    });
    const scroll = $('table-scroll').scrollTop;
    $('results-body').replaceChildren(fragment); $('table-scroll').scrollTop = scroll;
    $('empty-state').hidden = rows.length > 0;
    $('empty-title').textContent = state.records.length ? 'Žádné odpovídající výsledky' : 'Vaše další kontakty začínají zde';
    $('empty-text').textContent = state.records.length ? 'Zkuste změnit hledaný text nebo filtr.' :
      state.running ? 'Probíhá sběr. První výsledky se objeví za chvíli.' : 'Vyberte obor firem a spusťte sběr. Nalezené e-maily uvidíte průběžně zde.';
    $('tab-count').textContent = number(state.total);
    if (state.tab === 'results') $('result-count').textContent = state.total ?
      `${number(rows.length)} z ${number(state.records.length)} výsledků` + (state.total>500 ? ' · posledních 500' : '') : 'Zatím žádné výsledky';
  }
  function showDetail(record) {
    state.detail = record;
    $('detail-title').textContent = statusOf(record)[0]; $('detail-content').replaceChildren();
    const d = record.data;
    const emails = d.emails && d.emails.length ? d.emails.join(', ') : (d.email || d.skipped_email);
    const origins = [...new Set((d.origins||[]).map(o=>o.category + (o.page ? ` · stránka ${o.page}` : '')))].join('; ') || 'Neuvedena';
    [['Profil / web',record.url],['Kategorie',origins],['Nalezený web',d.website],['Nalezené e-maily',emails],
      ['Zdroj e-mailu',d.source],['Přeskočené adresy',(d.skipped_existing||[]).join(', ')],
      ['Podrobnosti',d.detail],['Další nalezené adresy',(d.candidates||[]).join(', ')]]
      .filter(([,value])=>value).forEach(([title,value])=> {addText($('detail-content'),'dt',title);addText($('detail-content'),'dd',value);});
    $('copy-detail').textContent = emails ? 'Kopírovat e-maily' : 'Kopírovat adresu webu';
    $('detail-dialog').showModal();
  }
  async function copyDetail() {
    if (!state.detail) return;
    const d = state.detail.data;
    const emails = d.emails && d.emails.length ? d.emails.join(', ') : (d.email || d.skipped_email);
    const value = emails || d.website || state.detail.url;
    try { await navigator.clipboard.writeText(value); toast('Zkopírováno do schránky.'); }
    catch (_) { notice('Kopírování', 'Schránka není dostupná. Označte text v detailu a použijte Ctrl+C.'); }
  }
  function changeTab(tab) {
    state.tab = tab; const results = tab === 'results';
    $('results-panel').hidden = !results; $('filters').hidden = !results; $('log-panel').hidden = results;
    $('table-hint').hidden = !results;
    ['results','log'].forEach(name=> { const selected = name === tab; const button = $(name+'-tab');
      button.classList.toggle('active',selected); button.setAttribute('aria-selected',String(selected)); button.tabIndex = selected ? 0 : -1; });
    if (results) render();
    else {
      $('result-count').textContent = 'Podrobný průběh a diagnostika běhu (nejnovější záznamy nahoře)';
      $('log-panel').scrollTop = 0;
    }
  }
  function appendLog(text) {
    const atTop = $('log-panel').scrollTop < 60;
    state.logs.unshift(new Date().toLocaleTimeString('cs-CZ') + '  ' + text);
    if (state.logs.length > 1500) state.logs.length = 1500;
    $('log-panel').textContent = state.logs.join('\n');
    if (atTop) $('log-panel').scrollTop = 0;
  }
  const BOOTSTRAP_COLORS = {
    primary: { dot: '🔵', hex: '#0d6efd' },
    blue: { dot: '🔵', hex: '#0d6efd' },
    danger: { dot: '🔴', hex: '#dc3545' },
    red: { dot: '🔴', hex: '#dc3545' },
    success: { dot: '🟢', hex: '#198754' },
    green: { dot: '🟢', hex: '#198754' },
    warning: { dot: '🟡', hex: '#ffc107' },
    yellow: { dot: '🟡', hex: '#ffc107' },
    info: { dot: '🔵', hex: '#0dcaf0' },
    cyan: { dot: '🔵', hex: '#0dcaf0' },
    secondary: { dot: '⚪', hex: '#6c757d' },
    gray: { dot: '⚪', hex: '#6c757d' },
    grey: { dot: '⚪', hex: '#6c757d' },
    dark: { dot: '⚫', hex: '#212529' },
    black: { dot: '⚫', hex: '#212529' },
    light: { dot: '⚪', hex: '#f8f9fa' },
    white: { dot: '⚪', hex: '#ffffff' },
    orange: { dot: '🟠', hex: '#fd7e14' },
    purple: { dot: '🟣', hex: '#6f42c1' },
    indigo: { dot: '🟣', hex: '#6610f2' }
  };
  function groupColor(name) {
    if (!name) return { dot: '⚪', hex: '#6c757d' };
    const key = String(name).toLowerCase().trim();
    return BOOTSTRAP_COLORS[key] || { dot: '⚪', hex: key.startsWith('#') ? key : '#6c757d' };
  }
  function updateGroupBadge() {
    const badge = $('group-badge');
    if (!badge || !$('group')) return;
    const opt = $('group').selectedOptions?.[0];
    const hex = opt?.dataset?.hex;
    if (hex && $('group').value && $('group').value !== 'missing') {
      badge.style.display = 'inline-block';
      badge.style.background = hex;
      badge.style.boxShadow = `0 0 0 2px ${hex}30`;
    } else {
      badge.style.display = 'none';
    }
  }
  function handleEvent(event) {
    if (event.type === 'groups') {
      state.dbBusy = false; state.groupsLoaded = true;
      const previous = $('group').value;
      $('group').replaceChildren(new Option('⚪ Bez skupiny (výchozí)',''));
      event.groups.forEach(g => {
        const id = g[0];
        const name = g[1];
        const color = g[2] || '';
        const { dot, hex } = groupColor(color);
        const opt = new Option(`${dot}  ${name}`, String(id));
        opt.dataset.color = color;
        opt.dataset.hex = hex;
        $('group').append(opt);
      });
      if (previous && !event.groups.some(g => String(g[0]) === previous)) {
        $('group').append(new Option('Vyberte skupinu znovu','missing')); $('group').value = 'missing';
      } else $('group').value = previous;
      updateGroupBadge();
      if ($('db-status')) $('db-status').textContent = `Připojeno · ${event.groups.length} skupin`;
      if ($('db-dot')) $('db-dot').className = 'status-dot connected';
      if ($('mysql-toggle')) $('mysql-toggle').title = `Nastavení MySQL · Připojeno (${event.groups.length} skupin)`;
      if ($('connect')?.querySelector('span')) $('connect').querySelector('span').textContent = 'Obnovit skupiny';
      controls();
    } else if (event.type === 'groups_error') {
      state.dbBusy = false; state.groupsLoaded = false; controls();
      if ($('db-status')) $('db-status').textContent = 'Připojení se nezdařilo';
      if ($('db-dot')) $('db-dot').className = 'status-dot failed';
      if ($('mysql-toggle')) $('mysql-toggle').title = 'Nastavení MySQL · Připojení se nezdařilo';
      appendLog(event.message); notice('Připojení k EmailApp',event.message);
    } else if (event.type === 'database') {
      if ($('db-status')) $('db-status').textContent = `Uloženo: ${number(event.counts.INSERTED)} · čeká: ${number(event.counts.PENDING)}`;
    } else if (event.type === 'request') {
      $('current-request').textContent = 'Právě načítám: ' + event.url; $('current-request').title = event.url;
    } else if (event.type === 'manual') {
      state.manual = event.active && !state.stopping; $('verification').hidden = !state.manual;
      $('verify').disabled = !state.manual;
      $('verify-message').textContent = 'Dokončete CAPTCHA a potom pokračujte ve sběru.';
      if (state.manual) {runStatus('Čeká na ověření','amber'); appendLog(event.message||'Čekám na ruční ověření.');}
      else if (!state.stopping) runStatus('Probíhá sběr');
    } else if (event.type === 'stage') {
      if (event.stage === 1 && Number.isFinite(event.profiles)) {
        state.counts.profiles = event.profiles;
        updateStats();
      }
      state.activeStage = event.stage;
      const step = document.querySelector(`[data-stage="${event.stage}"]`);
      if (!step) return;
      const ratio = event.total ? Math.min(1,event.done/event.total) : 0;
      const done = event.status.startsWith('Hotovo') ||
                   event.status.startsWith('Import hotov') ||
                   event.status.startsWith('Přeskočeno') ||
                   (event.total > 0 && event.done >= event.total);
      document.querySelectorAll('.step').forEach(el=>el.classList.remove('active'));
      step.classList.toggle('done',done); step.classList.toggle('active',!done); step.querySelector('progress').value = ratio;
      if (event.stage === 4) {
        step.querySelector('p').textContent = event.total ?
          `${number(event.done)} / ${number(event.total)} webů · ${done ? 'Hotovo (' + number(state.counts.emails) + ' e-mailů)' : number(state.counts.emails) + ' e-mailů'}` : event.status;
      } else if (event.stage === 3 && done) {
        step.querySelector('p').textContent = `${number(event.done)} / ${number(event.total)} webů · Hotovo`;
      } else if (event.stage === 2 && done) {
        step.querySelector('p').textContent = `${number(event.done)} / ${number(event.total)} profilů · Hotovo`;
      } else if (event.stage === 1 && done) {
        step.querySelector('p').textContent = `${number(event.done)} / ${number(event.total)} stránek · Hotovo`;
      } else {
        step.querySelector('p').textContent = event.total ? `${number(event.done)} / ${number(event.total)}${done?' · Hotovo':''}` : event.status;
      }
      step.title = event.status;
    } else if (event.type === 'result') {
      const d = event.data;
      if (event.stage === 4) {
        (d.skipped_existing||[]).forEach(email=>state.skipped.add(email));
        if (d.skipped_email) state.skipped.add(d.skipped_email);
        state.counts.skipped = state.skipped.size;
        const newEmails = d.emails || (d.email ? [d.email] : []);
        newEmails.forEach(email => state.emails.add(email));
        state.counts.emails = state.emails.size;
        const step4 = document.querySelector('[data-stage="4"]');
        if (step4) {
          step4.title = `Nalezeno ${state.counts.emails} e-mailových kontaktů`;
        }
      }
      if (['ERROR','PARTIAL'].includes(d.status)) state.counts.errors++;
      const existingIndex = event.updated ? state.records.findIndex(item => item.type === 'result' && item.stage === event.stage && item.url === event.url) : -1;
      if (existingIndex >= 0) state.records[existingIndex] = event;
      else { state.records.push(event); state.total++; if (state.records.length>500) state.records.shift(); }
      updateStats(); scheduleRender();
    } else if (event.type === 'log') {
      appendLog((event.level||'INFO')+'  '+event.message);
      if (event.level === 'ERROR') state.lastError = event.message;
    } else if (event.type === 'finish') {
      // The result is final even if DesktopAPI has not emitted its trailing
      // idle event yet. Never leave the stop action visible for a finished run.
      state.running = false; state.stopping = true; state.started = null;
      const [title,tone] = ({DONE:['Dokončeno','green'],PARTIAL:['Dokončeno s varováním','amber'],STOPPED:['Zastaveno','amber'],FAILED:['Běh selhal','red'],BLOCKED:['Přístup zastaven','amber']})[event.status] || ['Dokončeno','gray'];
      runStatus(title,tone);
      if (['STOPPED','FAILED','BLOCKED'].includes(event.status)) {
        state.hasStoppedData = true;
        state.resume = true;
        state.isCompleted = false;
      } else {
        state.hasStoppedData = false;
        state.resume = false;
        state.isCompleted = true;
      }
      state.counts = {profiles:event.profiles,emails:event.emails,skipped:event.skipped_existing||0,errors:event.errors_this_run}; updateStats();
      $('verification').hidden = true; state.manual = false; $('activity-dot').className = 'status-dot';
      $('footer-message').textContent = `${title} · K ověření: ${event.review} · Výsledky jsou ve složce běhu.`;
      $('current-request').textContent = ['FAILED','BLOCKED'].includes(event.status) ? state.lastError || 'Podrobnosti najdete v protokolu.' :
        event.status === 'STOPPED' ? 'Sběr je zastavený. Můžete pokračovat, použít aktuální data nebo běh ukončit.' :
        'Výsledky jsou uložené. Kliknutím na „Připravit nový sběr“ můžete spustit další sběr.';
      if (event.mysql && Object.keys(event.mysql).length && $('db-status')) $('db-status').textContent = `Uloženo: ${number(event.mysql.INSERTED)} · čeká: ${number(event.mysql.PENDING)}`;
      if (['FAILED','BLOCKED','STOPPED'].includes(event.status)) document.querySelectorAll('.step:not(.done) p').forEach(el=>el.textContent='Nedokončeno');
      appendLog(title+' · '+event.folder); render();
      controls();
    } else if (event.type === 'fatal') {
      state.running = false; state.stopping = true; state.started = null;
      runStatus('Nelze spustit','red'); $('footer-message').textContent = event.message;
      appendLog(event.message); notice('Běh nelze spustit',event.message);
    } else if (event.type === 'discarded') {
      state.hasStoppedData = false;
      state.resume = false;
      state.isCompleted = true;
      state.records = []; state.emails.clear(); state.skipped.clear(); state.total = 0;
      state.counts = {profiles:0,emails:0,skipped:0,errors:0};
      state.logs = []; $('log-panel').textContent = '';
      updateStats(); render(); runStatus('Běh zrušen','gray');
      $('footer-message').textContent = 'Běh byl zrušen a data zahozena.';
      $('current-request').textContent = 'Data běhu byla zahozena. Připravte nový sběr.';
      controls();
    } else if (event.type === 'idle') {
      state.running = false; state.stopping = false; state.started = null;
      if (state.isCompleted) {
        state.hasStoppedData = false;
        state.resume = false;
      }
      controls();
      if (!state.isCompleted) {
        folderInfo();
      }
    } else if (event.type === 'closing') {
      state.stopping = true; controls(); runStatus('Ukládám a zavírám','amber');
      $('footer-message').textContent = 'Ukládám výsledky před zavřením okna…';
    }
  }
  async function poll() {
    if (polling || !state.ready || state.starting) return;
    polling = true;
    try {
      const events = await api.poll_events();
      events.forEach(event => {
        try { handleEvent(event); }
        catch (error) { appendLog('Chyba zobrazení události: ' + (error?.message || error)); }
      });
    }
    catch (_) { $('footer-message').textContent = 'Spojení s Pythonem bylo přerušeno.'; }
    finally { polling = false; }
  }
  async function init() {
    if (state.ready || initializing || typeof window.pywebview?.api?.bootstrap !== 'function') return;
    initializing = true;
    api = window.pywebview.api;
    const data = await call('bootstrap');
    if (!data.ok) { initializing = false; notice('Spuštění rozhraní',data.message); return; }
    state.ready = true; state.settings = data.settings;
    if (data.db_connected) {
      if ($('db-dot')) $('db-dot').className = 'status-dot connected';
      if ($('mysql-toggle')) $('mysql-toggle').title = 'Nastavení MySQL · Připojeno';
    } else {
      if ($('db-dot')) $('db-dot').className = 'status-dot failed';
      if ($('mysql-toggle')) $('mysql-toggle').title = 'Nastavení MySQL · Nepřipojeno';
    }
    initializing = false;
    state.categories=data.categories; state.selected=new Set(data.categories); renderCategories();
    $('folder').value = data.folder;
    $('footer-message').textContent = data.categories_error || data.settings_error || 'Připraveno. Vyberte kategorie a spusťte sběr.';
    if(data.categories_error) notice('Načtení kategorií',data.categories_error);
    controls(); folderInfo();
    setInterval(poll,180);
    if (!data.settings_error) await connect();
    setInterval(()=> {
      if (!state.started) return;
      const seconds=Math.floor((Date.now()-state.started)/1000);
      $('elapsed').textContent = `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
    },1000);
  }
  $('start').addEventListener('click',start); $('stop').addEventListener('click',stop);
  if ($('prepare-new')) $('prepare-new').addEventListener('click',prepareNewRun);
  if ($('resume-run')) $('resume-run').addEventListener('click',start);
  if ($('finish-run')) $('finish-run').addEventListener('click',finishRun);
  if ($('discard-run')) $('discard-run').addEventListener('click',discardSavedRun);
  if ($('discard-saved')) $('discard-saved').addEventListener('click',discardSavedRun);
  function updateSaveBestEmail() {
    if (!$('save-best-email') || !$('save-best-email-label')) return;
    const isBest = $('save-best-email').checked;
    $('save-best-email-label').textContent = isBest ? 'Vybrat nejlepší kontakt' : 'Uložit všechny kontakty';
  }
  if ($('save-best-email')) {
    const saved = localStorage.getItem('wlw.save_best_email');
    if (saved !== null) $('save-best-email').checked = saved === 'true';
    $('save-best-email').addEventListener('change', () => {
      localStorage.setItem('wlw.save_best_email', $('save-best-email').checked);
      updateSaveBestEmail();
      controls();
    });
  }
  ['portal','destination','skip-existing','save-best-email','wlw-mode'].forEach(id=>{if($(id))$(id).addEventListener('change',controls);});
  if ($('group')) $('group').addEventListener('change', () => { updateGroupBadge(); controls(); });
  $('connect').addEventListener('click',connect);
  if ($('mysql-toggle')) $('mysql-toggle').addEventListener('click',openSettings);
  if ($('mysql-settings')) $('mysql-settings').addEventListener('click',openSettings);
  $('settings-form').addEventListener('submit',saveSettings);
  $('db-tls').addEventListener('change',()=> $('ca-field').hidden=!$('db-tls').checked);
  $('settings-dialog').addEventListener('close',()=> $('db-password').value='');
  $('preferences-toggle').addEventListener('click',()=> $('preferences-dialog').showModal());
  document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>$(button.dataset.close).close()));
  $('verify').addEventListener('click',async()=> {
    $('verify').disabled = true; const result=await call('confirm_verification');
    if (!result.ok) { notice('Ruční ověření',result.message); $('verify').disabled=false; }
    else $('verify-message').textContent='Kontroluji dokončení ověření…';
  });
  for (const [id,method] of [['choose-folder','choose_folder'],['new-folder','new_folder']]) $(id).addEventListener('click',async()=>{
    const result=await call(method); if (!result.ok) notice('Složka běhu',result.message);
    else if(result.folder) { $('folder').value=result.folder; folderInfo(); }
  });
  $('folder').addEventListener('input',()=> {clearTimeout(folderTimer); folderTimer=setTimeout(folderInfo,300);});
  $('open-folder').addEventListener('click',async()=> {const result=await call('open_folder',$('folder').value);if(!result.ok)notice('Složka výsledků',result.message);});
  $('search').addEventListener('input',scheduleRender); $('result-filter').addEventListener('change',render);
  $('results-tab').addEventListener('click',()=>changeTab('results')); $('log-tab').addEventListener('click',()=>changeTab('log'));
  document.querySelectorAll('[role="tab"]').forEach(tab=>tab.addEventListener('keydown',event=>{
    if (['ArrowRight','ArrowLeft','Home','End'].includes(event.key)) {event.preventDefault(); const name=event.key==='Home'?'results':event.key==='End'?'log':state.tab==='results'?'log':'results'; changeTab(name);$(name+'-tab').focus();}
  }));
  $('copy-detail').addEventListener('click',copyDetail);
  document.addEventListener('keydown',event=> {
    if ((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='f') {event.preventDefault(); changeTab('results'); $('search').focus();}
    if (event.key==='F5'||((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='r')) event.preventDefault();
  });
  $('add-category').addEventListener('click',addCategory);
  $('new-category').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();addCategory();}});
  $('select-all-categories').addEventListener('click',()=>{state.selected=new Set(state.categories);renderCategories();});
  updateSaveBestEmail();
  updateVisibility();
  if (typeof window.pywebview?.api?.bootstrap === 'function') {
    init();
  } else {
    window.addEventListener('pywebviewready', init, { once: true });
    let attempts = 0;
    const checkTimer = setInterval(() => {
      attempts++;
      if (typeof window.pywebview?.api?.bootstrap === 'function') {
        clearInterval(checkTimer);
        init();
      } else if (attempts > 60) {
        clearInterval(checkTimer);
      }
    }, 50);
  }
  setTimeout(() => {
    if (!state.ready) $('footer-message').textContent = 'Rozhraní čeká na Python. Aplikaci spouštějte pomocí _SPUSTIT.bat, nikoli otevřením ui/index.html.';
  }, 6000);
})();
