
'use strict';
const tg = window.Telegram && window.Telegram.WebApp;
// 3.1: страница на постоянном адресе («Телефон без компьютера») — сборка tools/mini-site подставляет { fn: адрес функции tg-login }.
// null — страницу отдаёт программа через туннель, как раньше.
const REMOTE = null; // rz-remote
const SNAP_V = 1;   // формат снимка, который эта страница понимает (bot.js rzrPut → "v")
// чужой родитель (Telegram Web) на обращение к window.parent.rzDev бросает SecurityError — весь скрипт падал
const DEV = (() => { try { return /[?&]dev\b/.test(location.search) && window.parent !== window && window.parent.rzDev; } catch { return null; } })();
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const icon = (n, cls) => `<svg class="ic${cls ? ' ' + cls : ''}" aria-hidden="true"><use href="#i-${n}"/></svg>`;
const nf = new Intl.NumberFormat('ru-RU');
const plural = (n, a, b, c) => { n = Math.abs(n) % 100; const d = n % 10; return n > 10 && n < 20 ? c : d > 1 && d < 5 ? b : d === 1 ? a : c; };
const CH = { ig: ['Instagram', 'ig'], tg: ['Telegram', 'tg'], viber: ['Viber', 'viber'], wa: ['WhatsApp', 'wa'], fb: ['Facebook', 'fb'] };
const STAGE_COLORS = { work: '#FFFFFF', new: '#8E8FA0', queued: '#3EE6A8', contacted: '#F2C94C', due: '#FF9F43', replied: '#38A0F0', interested: '#7EDC9E', client: '#B68CFF', declined: '#FF6B6B' };
const TITLES = { today: 'Сегодня', new: 'Парсер', base: 'База', msgs: 'Сообщения' };
const haptic = k => { try { k === 'ok' ? tg.HapticFeedback.notificationOccurred('success') : k === 'err' ? tg.HapticFeedback.notificationOccurred('error') : k === 'sel' ? tg.HapticFeedback.selectionChanged() : tg.HapticFeedback.impactOccurred('light'); } catch {} };

// ---- настройки страницы: облако Telegram (адрес туннеля меняется при каждом запуске программы — localStorage с ним пропадает) ----
const PREF_KEYS = ['tab', 'nf', 'sort', 'bf', 'fold', 'gfx'];
const P = { tab: 'today', nf: {}, sort: 'score', bf: 'work', fold: {}, gfx: null };
const cloud = () => { try { return tg && tg.CloudStorage && tg.isVersionAtLeast && tg.isVersionAtLeast('6.9') ? tg.CloudStorage : null; } catch { return null; } };
function prefsLoad(){
  return new Promise(done => {
    for (const k of PREF_KEYS) { try { const v = localStorage.getItem('rzm.' + k); if (v != null) P[k] = JSON.parse(v); } catch {} }
    const cs = cloud(); if (!cs) return done();
    const t = setTimeout(done, 700);
    try { cs.getItems(PREF_KEYS.map(k => 'rzm_' + k), (err, vals) => { clearTimeout(t); if (!err && vals) for (const k of PREF_KEYS) { try { const v = vals['rzm_' + k]; if (v) P[k] = JSON.parse(v); } catch {} } done(); }); } catch { clearTimeout(t); done(); }
  });
}
function keep(k, v){
  P[k] = v; const s = JSON.stringify(v);
  try { localStorage.setItem('rzm.' + k, s); } catch {}
  const cs = cloud(); if (cs && s.length < 4000) try { cs.setItem('rzm_' + k, s); } catch {}
}

// ---- живой фон окна: bg.js с ПК, настройки графики приходят с каждым ответом программы ----
let gfxLoaded = false;
function gfxBoot(){
  if (gfxLoaded) return; gfxLoaded = true;
  if (!DEV && P.gfx) try { localStorage.setItem('rz.settings', JSON.stringify({ gfx: P.gfx })); } catch {}
  const s = document.createElement('script'); s.src = '/static/bg.js'; s.onerror = () => { $('bg').hidden = true; };
  s.onload = () => { try { RZGfx.page(S.tab === 'base' ? 'base' : S.tab === 'msgs' ? 'msg' : 'lead'); } catch {} };
  document.body.appendChild(s);
}
function gfxApply(g){
  if (!g || DEV) return;
  const s = JSON.stringify(g); if (s === JSON.stringify(P.gfx)) return;
  keep('gfx', g);
  try { localStorage.setItem('rz.settings', JSON.stringify({ gfx: g })); } catch {}
  try { window.RZGfx && RZGfx.set(g); } catch {}
}

// ---- связь с программой ----
let apiBusy = 0;
function syncState(k){
  const b = $('sync'); if (!b) return;
  b.classList.toggle('busy', apiBusy > 0); b.classList.toggle('off', k === 'off');
  if (k === 'ok' && REMOTE) {
    const n = Object.keys(R.pend).length, on = pcOn();
    $('syncT').textContent = (on ? 'ПК на связи' : 'снимок ' + (snapAge() || '—')) + (n ? ' · ждёт ПК ' + n : '');
    b.classList.toggle('off', !on && !!n);
    b.setAttribute('aria-label', (on ? 'Компьютер на связи' : 'Компьютер не на связи, снимок от ' + (snapAge() || 'неизвестно')) + (n ? `, ${n} ${plural(n, 'действие ждёт', 'действия ждут', 'действий ждут')} компьютер` : '') + '. Обновить');
    return;
  }
  if (k === 'ok') { S.syncAt = new Date(); $('syncT').textContent = S.syncAt.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }); b.setAttribute('aria-label', 'На связи с компьютером, обновлено в ' + $('syncT').textContent + '. Обновить'); }
  if (k === 'off') { $('syncT').textContent = 'нет связи'; b.setAttribute('aria-label', 'Нет связи с компьютером. Повторить'); }
}
// Каждое действие (op 'act') несёт opId: повтор той же операции (кнопка «Записать»/«Повторить» после обрыва) идёт с тем же opId,
// и программа не выполняет её второй раз, если первая всё-таки дошла (ответ потерялся по дороге)
function newOpId(){ try { if (window.crypto && crypto.randomUUID) return crypto.randomUUID(); } catch {} return Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12) + Math.random().toString(36).slice(2, 12); }
async function api(op, args){
  if (op === 'act' || op === 'run') { args = Object.assign({}, args); if (!args.opId) args.opId = newOpId(); }
  apiBusy++; syncState();
  try {
    let d, tries = 0;
    for (; ; tries++) {
      try { d = await apiRaw(op, args); break; }
      catch (e) {
        // действие ушло, а итога нет (долго выполняется, программа ответила «не успела»): это не «нет связи» —
        // дозапрашиваем итог тем же opId, программа второй раз не выполнит (bot.js rzOpOnce)
        if ((op === 'act' || op === 'run') && e && e.slow && tries < 3) { if (!tries) toast('Выполняется на компьютере… жду результат', null, 60000); continue; }
        throw e;
      }
    }
    if (tries) hideToast();   // «выполняется…» больше не нужно — итог покажет after()
    apiBusy--; syncState('ok'); return d;
  }
  // e.reopen — до программы не дошли (обрыв, таймаут, 502/404, 401); раньше таймаут и 401 показывались как «на связи»
  catch (e) { apiBusy--; syncState(e && e.reopen || /связи|не отвечает|не ответила/.test((e && e.message) || '') ? 'off' : 'ok'); throw e; }
}
// ошибка, после которой помогает «закрыть и открыть заново» (новый адрес туннеля / свежая подпись Telegram)
function reopenErr(msg){ const e = new Error(msg); e.reopen = true; return e; }
// 3.18: подписка учётки закончилась (сервер m31 → 403 reason 'unpaid') — повтор не поможет: только «Закрыть», продлевают на компьютере
const UNPAID_TEXT = 'Подписка закончилась — продлите её в программе на компьютере (Профиль → Подписка).';
function deadErr(){ const e = new Error(UNPAID_TEXT); e.dead = true; return e; }
// Сроки ожидания по типу операции — чуть дольше, чем ждёт программа (app-main.js miniAsk: 150 с / 30 с):
// её ответ «не успела» приходит раньше нашего обрыва, и действие дозапрашивается, а не теряется
const LONG_ACT = /^(scan|reg|gen|who|quick)$/;
const waitMs = (op, args) => op === 'act' && LONG_ACT.test((args || {}).act || '') ? 160000 : 35000;
// свёрнуто или закрывается — запрос должен дойти и после выгрузки страницы (keepalive, до 64 КБ)
const leaving = () => document.visibilityState === 'hidden';
async function httpApi(url, op, args){
  let r;
  const ms = waitMs(op, args), ctl = new AbortController(), tm = setTimeout(() => ctl.abort(), ms);
  const body = JSON.stringify({ initData: tg ? tg.initData : '', op, args: args || {} });
  try { r = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body, signal: ctl.signal, keepalive: leaving() && body.length < 60000 }); }
  catch {
    const e = reopenErr(ctl.signal.aborted ? `Программа не ответила за ${ms > 60000 ? '2,5 минуты' : '35 секунд'}. Компьютер мог уснуть или программа занята.` : 'Нет связи с программой: компьютер выключен или уснул, программа закрыта — или она перезапускалась и адрес приложения сменился.');
    e.slow = ctl.signal.aborted; e.net = !ctl.signal.aborted; throw e;
  }
  finally { clearTimeout(tm); }
  if (r.status === 502 || r.status === 530 || r.status === 504 || r.status === 404) { const e = reopenErr('Программа на компьютере не отвечает — или она перезапускалась и адрес приложения сменился.'); e.net = true; throw e; }
  if (r.status === 403 || r.status === 401) { const j = await r.clone().json().catch(() => ({})); if (j && j.reason === 'unpaid') throw deadErr(); }
  if (r.status === 401) {   // причину говорит сервер: «больше суток» было неправдой, если бот переподключили или привязали другой телефон
    const j = await r.json().catch(() => ({}));
    throw reopenErr(j.reason === 'nobot' ? 'Бот в программе отключён или привязан к другому телефону — подключите его заново: Настройки → «Telegram-бот».' : 'Telegram не подтвердил вход: приложение открыто больше суток или бот переподключён.');
  }
  const d = await r.json().catch(() => ({ error: 'Программа ответила непонятно (' + r.status + ').' }));
  if (!r.ok || d.error) {
    if (/Неизвестная операция/.test(d.error || '')) throw new Error('Программе на компьютере нужна свежая версия: перезапустите LeadHunter.');
    const e = new Error(d.error || 'Ошибка ' + r.status); if (d.slow) e.slow = true; throw e;
  }
  return d;
}
async function apiRaw(op, args){
  let d;
  if (DEV) d = await DEV(op, args || {});
  else if (REMOTE) d = await remoteApi(op, args || {});
  else d = await httpApi('api', op, args);
  if (d && d._c) counts(d._c);
  if (d && d._g) gfxApply(d._g);
  if (d && d._note) S.note = d._note;
  return d;
}

// ---- 3.1: «Телефон без компьютера» — страница на постоянном адресе (REMOTE) ----
// Данные — снимок, который программа выкладывает на сервер LeadHunter (тот же ответ, что она дала бы через туннель),
// действия — в очередь на сервере: компьютер заберёт и выполнит их с тем же opId (дважды не запишется).
// Туннель программы ещё жив (адрес в снимке, компьютер на связи) — ходим к нему напрямую, как раньше.
// Снимок держим в localStorage: без сети и с выключенным компьютером видно последнее; очередь — со счётчиком «ждёт ПК».
const R = { snap: null, srvAt: '', pcSeen: 0, tunnel: '', tunnelBad: 0, wait: 0, syncAt: 0, syncP: null, pend: {}, waiters: {}, err: '' };
const PC_FRESH = 45000;
const pcOn = () => !!R.pcSeen && Date.now() - R.pcSeen < PC_FRESH;
const hm = t => new Date(t).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
const snapAge = () => R.snap && R.snap.at ? hm(R.snap.at) : '';
async function m31(body, ms){
  const ctl = new AbortController(), tm = setTimeout(() => ctl.abort(), ms || 20000);
  const b = JSON.stringify(Object.assign({ op: 'm31', initData: tg ? tg.initData : '' }, body));
  let r;
  try { r = await fetch(REMOTE.fn, { method: 'POST', headers: { 'content-type': 'application/json' }, body: b, signal: ctl.signal, keepalive: leaving() && b.length < 60000 }); }
  catch { const e = new Error(ctl.signal.aborted ? 'Сервер LeadHunter не ответил.' : 'Нет интернета — показываю сохранённое.'); e.net = true; throw e; }
  finally { clearTimeout(tm); }
  if (r.status === 401) throw reopenErr('Telegram не подтвердил вход: закройте приложение и откройте заново кнопкой LeadHunter в боте.');
  const j = await r.json().catch(() => null);
  if (!j) { const e = new Error('Сервер ответил непонятно (' + r.status + ').'); e.net = r.status >= 500; throw e; }
  if (j.reason === 'unpaid') throw deadErr();
  if (j.reason === 'off') throw new Error('«Телефон без компьютера» выключен в программе — включите: Настройки → «Telegram-бот».');
  if (!j.ok) throw new Error(j.error || 'Ошибка сервера.');
  return j;
}
function snapKeep(){ try { const v = JSON.stringify({ srvAt: R.srvAt, snap: R.snap }); if (v.length < 3e6) localStorage.setItem('rzm.snap', v); } catch {} }
function pendKeep(){ try { localStorage.setItem('rzm.pend', JSON.stringify(R.pend)); } catch {} }
// один запрос «get»: снимок (если сменился), когда компьютер был на связи, итоги своих операций. true — снимок новый
async function remoteGet(extra){
  const ops = Object.keys(R.pend).concat(extra || []).slice(0, 50);
  const j = await m31({ do: 'get', since: R.snap ? R.srvAt : '', ops });
  R.syncAt = Date.now(); R.err = '';
  R.pcSeen = j.pcAge != null ? Date.now() - j.pcAge * 1000 : 0; R.tunnel = /^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(j.tunnel || '') ? j.tunnel : ''; R.wait = j.wait || 0;
  let fresh = false;
  if (j.snap && !j.same) { R.snap = j.snap; R.srvAt = j.at; fresh = true; snapKeep(); }
  pendApply(j.ops || []);
  syncState('ok');
  return { j, fresh };
}
function remoteSync(force){
  if (R.syncP) return R.syncP;
  if (!force && R.snap && Date.now() - R.syncAt < 10000) return Promise.resolve(false);
  R.syncP = remoteGet().then(x => x.fresh, e => { R.err = e.message || String(e); throw e; }).finally(() => { R.syncP = null; });
  return R.syncP;
}
// итоги операций очереди: свои ожидания (waiters) получают ответ, действия «ждёт ПК» — тост с итогом
function pendApply(states){
  let changed = false;
  for (const st of states) {
    if (!st || (st.state !== 'done' && st.state !== 'fail')) continue;
    const w = R.waiters[st.op_id]; if (w) { delete R.waiters[st.op_id]; w(st); }
    const p = R.pend[st.op_id]; if (!p) continue;
    delete R.pend[st.op_id]; changed = true;
    const res = st.res || {};
    if (w) continue;   // ответ дождался тот, кто спрашивал
    if (res.error) { toast('С компьютера: ' + res.error, null, 9000); continue; }
    if (p.op === 'act' && res.res) { const r = res.res; if (r.msg && !r.quiet) toast('С компьютера: ' + r.msg, null, 6000); }
    if (p.op === 'run' && res.res && res.res.msg) { toast('С компьютера: ' + res.res.msg, null, 9000); if (res.res.ok) runWatch(); }
  }
  if (changed) { pendKeep(); if (!Object.keys(R.pend).length) show(true); }
}
function pendAdd(opId, op, args){ R.pend[opId] = { op, act: args.act || '', id: args.id || '', at: Date.now() }; pendKeep(); }
async function remotePush(op, args){
  const a = Object.assign({}, args); const opId = a.opId || newOpId(); delete a.opId;
  const j = await m31({ do: 'push', opId, op, args: a });
  R.wait = j.wait || R.wait;
  return opId;
}
// спросить компьютер через очередь и дождаться (пока он на связи); null — не дождались за ms
async function remoteAsk(op, args, ms){
  const opId = await remotePush(op, args);
  if (op === 'act' || op === 'run') pendAdd(opId, op, args);
  const got = new Promise(ok => { R.waiters[opId] = ok; });
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const st = await Promise.race([got, new Promise(k => setTimeout(() => k(null), 1500))]);
    if (st) { const res = st.res || {}; if (res.error) throw new Error(res.error); return res; }
    try { await remoteGet([opId]); } catch {}
  }
  delete R.waiters[opId];
  return null;
}
// ответ из снимка; partial — не то, что просили (фильтр, «ещё»), а ближайшее, что есть
function snapRead(op, a){
  const sn = R.snap; if (!sn || !sn.views) return null;
  const v = sn.views, extra = { _c: sn.counts, _g: sn.gfx };
  const part = (d, more) => ({ d: Object.assign({}, d, extra, more || {}), partial: true });
  if (op === 'today') return { d: Object.assign({}, v.today, extra) };
  if (op === 'new') {
    if (+a.off > 0) return part(v.new, { items: [], more: false, off: +a.off });
    const plain = !a.city && !a.kind && !a.mob && (a.sort || 'score') === 'score' && (+a.limit || 30) <= 30;
    return plain ? { d: Object.assign({}, v.new, extra) } : part(v.new);
  }
  if (op === 'base') return (a.f || 'work') === 'work' && !a.lim ? { d: Object.assign({}, v.base, extra) } : part(v.base);
  if (op === 'msgs') return !a.lim ? { d: Object.assign({}, v.msgs, extra) } : part(v.msgs);
  if (op === 'lead') { const l = sn.leads && sn.leads[a.id]; return l ? { d: Object.assign({ lead: l }, extra) } : null; }
  if (op === 'runInfo') {
    const r = Object.assign({}, sn.run || {});
    if (a.city && a.cat) r.pair = { city: a.city, cat: a.cat, ok: true, req: r.pages || 1, cost: ((r.pages || 1) / 1000 * (r.price || 0)).toFixed(2).replace('.', ','), recent: null };
    return a.city ? part(r) : { d: Object.assign({}, r, extra) };   // списки городов и категорий снимка хватает; «уже искали» знает только ПК
  }
  if (op === 'runState') return part({ running: false, log: '', pct: 0 });
  if (op === 'search') {   // поиск по снимку: название, город, номер, ник, имя владельца
    const q = String(a.q || '').toLowerCase().trim(), dg = q.replace(/\D/g, ''), seen = new Set(), items = [];
    const hit = it => [it.name, it.city, it.category].some(x => String(x || '').toLowerCase().includes(q)) || (it.ig && String(it.ig.nick || '').toLowerCase().includes(q.replace(/^@/, '')))
      || (dg.length >= 5 && (it.phones || []).some(p => String(p.d || '').includes(dg)));
    const all = [].concat(...['today', 'base', 'msgs'].map(k => [].concat(...((v[k] || {}).groups || []).map(g => g.items || []))), (v.new || {}).items || [], Object.values(sn.leads || {}));
    for (const it of all) if (it && it.id && !it.stop && !seen.has(it.id) && hit(it)) { seen.add(it.id); items.push(it); if (items.length >= 15) break; }
    return part({ items, me: v.today ? v.today.me : true, stops: (v.today || {}).stops });
  }
  return null;
}
// действие без компьютера: телефон показывает, что набрано (черновик, заметка), остальное — «ждёт компьютер»
function queuedReply(op, a){
  if (op === 'run') return { res: { ok: true, queued: true, msg: 'Поиск выполнится на компьютере, когда он будет на связи.' } };
  const sn = R.snap || {}, card = (sn.leads || {})[a.id], open = S.lead && S.lead.id === a.id ? S.lead.data : null;
  const lead = card || open ? Object.assign({}, card || open) : null;
  if (lead && a.act === 'draft') lead.draftText = String(a.arg == null ? '' : a.arg);
  if (lead && a.act === 'noteSet') lead.note = String(a.arg == null ? '' : a.arg);
  if (card && lead) sn.leads[a.id] = lead;
  const quiet = a.act === 'draft' || a.act === 'noteSet';
  return { res: { ok: true, queued: true, quiet, msg: 'Ждёт компьютер — выполнится, когда он заберёт очередь.' }, lead };
}
async function tunnelApi(op, args){ return httpApi(R.tunnel + '/api', op, args); }
async function remoteApi(op, a){
  // 1) туннель программы жив — напрямую (быстро и свежо); не отвечает — минуту не пробуем, дальше через сервер
  if (!R.snap && !R.syncAt) await remoteSync().catch(() => {});
  if (R.tunnel && pcOn() && Date.now() - R.tunnelBad > 60000) {
    try { return await tunnelApi(op, a); } catch (e) { if (!e.net) throw e; R.tunnelBad = Date.now(); }
  }
  // 2) снимок: есть сохранённый — показываем сразу, свежий подтянется и перерисует тихо
  if (R.snap) remoteSync().then(fresh => { if (fresh && op !== 'act' && op !== 'run') show(true); }, e => { syncState('off'); if (e && e.dead && !R.deadSaid) { R.deadSaid = true; fail(e); } });
  else await remoteSync().catch(e => { if (!R.snap) throw e; });
  if (R.snap && R.snap.v > SNAP_V) { const e = new Error('Страница Mini App устарела для этой версии программы — владельцу нужно выложить её заново.'); throw e; }
  if (op === 'act' || op === 'run') {
    if (pcOn()) { const res = await remoteAsk(op, a, waitMs(op, a)); if (res) return res; return queuedReply(op, a); }
    const opId = await remotePush(op, a); pendAdd(opId, op, a);
    return queuedReply(op, a);
  }
  const sr = snapRead(op, a);
  if (sr && !sr.partial) return sr.d;
  if (pcOn()) { const res = await remoteAsk(op, a, 30000).catch(e => { if (!sr) throw e; return null; }); if (res) return res; }
  if (sr) return Object.assign(sr.d, { _note: (pcOn() ? 'Компьютер не успел ответить' : 'Компьютер не на связи') + ' — показан снимок' + (snapAge() ? ' от ' + snapAge() : '') + (op === 'search' ? ' (поиск только по нему).' : ', без фильтров и «ещё».') });
  throw new Error(op === 'lead' ? 'Этой карточки нет в снимке — откроется, когда компьютер будет на связи.' : 'Компьютер не на связи, а в снимке этого нет.');
}
function counts(c){
  const b = (id, n, t) => { const el = $(id); el.hidden = !n; el.textContent = n > 99 ? '99+' : n; el.title = t || ''; };
  b('bToday', c.today, 'ответили и пора дожать'); b('bNew', 0); b('bBase', c.base, 'пора дожать и ответили'); b('bMsgs', c.msg, 'ответить и готово к отправке');
  S.fresh = c.fresh;
}

// ---- тост с действиями (как в окне); пока приложение свёрнуто (ушли в Instagram) — ждёт возвращения ----
let toastT = 0, toastLeft = 0;
function toast(t, acts, ms){
  $('toastT').textContent = t;
  const a = $('toastA'); a.innerHTML = '';
  (acts || []).forEach(x => { const b = document.createElement('button'); b.className = 'toast-act'; b.type = 'button'; b.textContent = x.label; b.onclick = () => { hideToast(); x.fn(); }; a.appendChild(b); });
  $('toast').classList.toggle('over', !!S.lead || $('pick').classList.contains('open'));
  $('toast').classList.add('show');
  toastLeft = ms || (acts && acts.length ? 6500 : 3200);
  armToast();
}
function armToast(){ clearTimeout(toastT); if (!document.hidden && toastLeft) toastT = setTimeout(hideToast, toastLeft); }
function hideToast(){ clearTimeout(toastT); toastLeft = 0; $('toast').classList.remove('show'); }
// ошибка действия: «Повторить» — та же операция с тем же opId (дошла — второй раз не запишется)
function failRetry(e, fn){ if (e && e.dead) return fail(e); haptic('err'); toast(String((e && e.message) || e), [{ label: 'Повторить', fn }].concat(e && e.reopen && tg ? [{ label: 'Закрыть', fn: () => { try { tg.close(); } catch {} } }] : []), 12000); }
function fail(e){ haptic('err'); toast(String((e && e.message) || e), e && (e.reopen || e.dead) && tg ? [{ label: 'Закрыть', fn: () => { try { tg.close(); } catch {} } }] : null, e && e.reopen ? 9000 : 0); }

// буфер — синхронно, в самом нажатии: после запроса к программе телефон уже не разрешит писать в буфер
function copyNow(text){
  let ok = false, t = null;
  try {
    t = document.createElement('textarea');
    t.value = text; t.setAttribute('readonly', ''); t.setAttribute('data-tmp', ''); t.style.cssText = 'position:fixed;top:0;left:0;opacity:0;font-size:16px';
    document.body.appendChild(t); t.focus({ preventScroll: true }); t.select(); t.setSelectionRange(0, text.length);
    ok = document.execCommand('copy');
  } catch {}
  finally { if (t) { try { t.blur(); } catch {} t.remove(); } }   // blur до remove: иначе focusout может не прийти и body.typing останется
  if (!ok && navigator.clipboard) { try { navigator.clipboard.writeText(text).catch(() => toast('Текст не скопировался — откройте карточку и нажмите «Скопировать».')); ok = true; } catch {} }
  return ok;
}
function copy(text, what){ if (!text) return; const ok = copyNow(text); haptic(ok ? 'ok' : 'err'); toast(ok ? (what || 'Скопировано') : 'Не получилось скопировать — выделите текст пальцем.'); }
function openUrl(url){
  // только известные схемы: адрес карты может прийти из импортированной таблицы, а javascript: здесь увидел бы initData
  if (!url || !/^(https?:|tg:|viber:|whatsapp:|tel:|mailto:|sms:)/i.test(url)) return;
  try {
    if (tg && /^https:\/\/t\.me\//.test(url)) return tg.openTelegramLink(url);
    if (tg && /^https?:\/\//.test(url)) return tg.openLink(url);
  } catch {}
  if (/^https?:/.test(url)) window.open(url, '_blank', 'noopener'); else location.href = url;
}

// ---- состояние ----
// parserNext — свежий список парсера, станет S.parser.items только при перерисовке; baseLim / msgLim — «Показать ещё» в Базе и «Сообщениях»
const S = { tab: 'today', q: '', lead: null, nav: { ids: [], label: '' }, items: {}, view: null, parser: { items: [], off: 0 }, parserNext: null, baseLim: 0, msgLim: 0, twinOk: {}, claimOk: {}, me: true, fresh: 0, busy: 0, moreBusy: 0 };
const remember = arr => { arr.forEach(it => { if (it && it.id) S.items[it.id] = it; }); return arr; };

// ---- плашки ----
function kindBadge(it, long){ return `<span class="lead ${it.kind}"><span class="dot ${it.kind}"></span>${esc(long ? it.kindLong || it.kindLabel : it.kindLabel)}</span>` + (it.closed ? `<span class="lead closedb">${long ? 'Закрыто навсегда' : 'закрыто'}</span>` : ''); }
function ratingHtml(it){ return it.rating == null ? '<span class="muted">без рейтинга</span>' : `${icon('star', 'star')}<b>${Number(it.rating).toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</b><span class="muted2">${nf.format(it.reviews || 0)}</span>`; }
const repliedBadge = it => it.replied ? `<span class="replied">${icon(it.via === 'ig' ? 'ig' : it.via === 'tg' ? 'tg' : 'message', 'sm')}ответили</span>` : '';
const twinBadge = it => it.twins ? `<span class="twin" title="Тот же владелец у других заведений">${icon('phone', 'sm')}×${it.twins + 1}</span>` : '';
// 3.10: бронь заведений (claim из bot.js): плашка в списке и в панели
const claimTxt = c => c.client ? 'клиент другого пользователя LeadHunter' : 'в работе у другого пользователя LeadHunter · свободно с ' + c.until;
const claimPlate = (it, big) => !it.claim ? '' : big
  ? `<div class="claim-plate big" role="note"><b>Уже трогали</b><span>${esc(claimTxt(it.claim))}${/\.$/.test(it.claim.until) ? '' : '.'} Писать повторно не стоит: владелец, скорее всего, уже получил такое же предложение.</span></div>`
  : `<p class="claim-plate" role="note"><b>Уже трогали</b><span>${it.claim.client ? 'клиент другого' : 'до ' + esc(it.claim.until)}</span></p>`;
const sBadge = it => it.badge ? `<span class="sbadge${it.badge.warn ? ' warn' : ''}">${esc(it.badge.t)}</span>` : '';
const fuChip = (it, id) => it.fu ? `<button type="button" class="fu ${it.fu.cls}" data-fu="${esc(id || it.id)}">${icon('clock', 'sm')}${esc(it.fu.txt)}</button>` : '';
// Кнопки каналов (contactCell): нажатие — текст в буфер, чат открывается, касание записывается
function chanBtns(it){
  let h = '';
  const has = ch => it.links.some(x => x.ch === ch);
  if (has('ig')) h += `<button type="button" class="cbtn ch-ig${it.igUnsure ? ' unsure' : ''}" data-ch="ig" data-id="${esc(it.id)}" aria-label="Написать в Instagram">${icon('ig')}</button>`;
  else if (it.igState === 'pending') h += `<span class="cbtn ghost" aria-label="Ищу Instagram…"><span class="spin"></span></span>`;
  for (const ch of ['tg', 'viber', 'wa', 'fb']) if (has(ch)) h += `<button type="button" class="cbtn ch-${ch}" data-ch="${ch}" data-id="${esc(it.id)}" aria-label="Написать в ${CH[ch][0]}">${icon(CH[ch][1])}</button>`;
  return h || '<span class="landline">мессенджеров нет</span>';
}
const sdot = st => `<span class="sdot s-${esc(st)}"></span>`;
function pcard(it){
  return `<article class="card s-${esc(it.stage)}${it.claim ? ' claimed' : ''}" data-lead="${esc(it.id)}" aria-label="${esc(it.name)} — открыть">
    <div class="card-top">${kindBadge(it)}${repliedBadge(it)}${twinBadge(it)}${sBadge(it)}<span class="card-rating">${ratingHtml(it)}</span></div>
    ${claimPlate(it)}
    <h3 class="card-name">${esc(it.name)}</h3>
    <p class="card-city">${icon('pin', 'sm')}<span>${esc(it.city || 'город не указан')}</span>${it.category ? `<span class="dotsep"></span><span>${esc(it.category)}</span>` : ''}</p>
    ${it.fu ? `<p class="card-next">${fuChip(it)}</p>` : ''}
    <div class="card-foot"><div class="cwrap">${chanBtns(it)}</div><button type="button" class="stat" data-stage="${esc(it.id)}">${sdot(it.stage)}${esc(it.stageLabel)}</button></div>
  </article>`;
}
function brow(it){
  if (it.stop) return `<article class="brow stopr" style="--c:${it.col}"><div class="bhead"><b>${esc(it.name)}</b></div><div class="bmeta"><span>${esc(it.city || 'город не указан')}</span>${it.touch ? `<time>${esc(it.touch)}</time>` : ''}</div>${it.note ? `<p class="hnote">${esc(it.note)}</p>` : ''}<div class="bfoot"><span class="bstage ro" style="--c:${it.col}"><i></i><span>${esc(it.stageLabel)}</span></span><span class="sp"></span><span class="landline">вернуть — в программе</span></div></article>`;
  const meta = [it.city || 'город не указан', it.category].filter(Boolean).join(' · ');
  return `<article class="brow${it.claim ? ' claimed' : ''}" data-lead="${esc(it.id)}" style="--c:${it.col}" aria-label="${esc(it.name)} — открыть">${claimPlate(it)}
    <div class="bhead"><b>${esc(it.name)}</b>${repliedBadge(it)}${twinBadge(it)}${it.rating != null ? `<span class="card-rating">${ratingHtml(it)}</span>` : ''}</div>
    <div class="bmeta"><span>${esc(meta)}</span>${it.touch ? `<time>${esc(it.touch)}</time>` : ''}</div>
    ${it.sub ? `<p class="bquote">${esc(it.sub)}</p>` : ''}
    ${it.fu ? `<p class="card-next">${fuChip(it)}</p>` : ''}
    ${it.note ? `<p class="hnote">${esc(it.note)}</p>` : ''}
    <div class="bfoot"><button type="button" class="bstage" data-stage="${esc(it.id)}" style="--c:${it.col}"><i></i><span>${esc(it.stageLabel)}</span></button><span class="sp"></span><div class="cwrap">${chanBtns(it)}</div></div>
  </article>`;
}
const mrBtn = it => `<button type="button" class="hbtn${it.marked ? ' on' : ''}" data-mr="${esc(it.id)}" aria-pressed="${!!it.marked}" aria-label="${it.marked ? 'Снять метку «ответили»' : 'Отметить: ответили'}">${icon('message')}</button>`;
const genBtn = it => `<button type="button" class="cbtn gen${it.draftText && (it.draftText || '').trim() ? ' has' : ''}" data-gen="${esc(it.id)}" aria-label="${it.genDone ? 'Первое сообщение отправлено — дожимов нет' : it.draftText && (it.draftText || '').trim() ? 'Перегенерировать черновик' : 'Сгенерировать черновик'}"${it.genDone ? ' disabled' : ''}>${icon('spark')}</button>`;
function groupHead(g, n, foldable){
  const f = foldable && !S.q && isFolded(g.key);
  return `<button type="button" class="bgroup" data-grp="${esc(g.key)}" aria-expanded="${!f}" style="--c:${g.col}"${foldable ? '' : ' disabled'}><i></i><b>${esc(g.title)}</b><span class="n">${nf.format(n)}</span>${g.hint ? `<small>${esc(g.hint)}</small>` : ''}<span class="ln"></span>${foldable ? '<span class="chev"></span>' : ''}</button>`;
}
const isFolded = k => (P.fold || {})[S.tab + '|' + k] ?? (k === 'sent');
const skel = n => '<div class="list">' + Array.from({ length: n }, () => '<div class="skel"></div>').join('') + '</div>';
function setTitle(t, s){ $('title').innerHTML = esc(t) + `<small>${s ? esc(s) : '&nbsp;'}</small>`; }
const listIds = () => [...$('view').querySelectorAll('[data-lead]')].map(el => el.dataset.lead).filter((v, i, a) => a.indexOf(v) === i);

// ---- страницы ----
async function viewToday(){
  const d = await api('today');
  S.me = d.me; S.queue = d.ids || []; if (d.stops) S.stops = d.stops;
  setTitle('Сегодня', d.day);
  const pct = Math.min(100, Math.round(d.sent.today / d.sent.goal * 100));
  let h = '';
  if (!d.me) h += `<div class="warnbox">Впишите имя и регион в программе: Настройки → «Обо мне» — без них текст сообщений не собирается.</div>`;
  h += `<div class="kstrip"><div class="kpi"><b class="num">${nf.format(d.sent.today)}<small>/ ${nf.format(d.sent.goal)}</small></b><span>отправлено</span></div>
    <button type="button" class="kpi" data-tab="msgs"><b class="num">${nf.format(d.sent.week)}</b><span>за неделю</span></button>
    <button type="button" class="kpi" data-tab="new"><b class="num">${nf.format(d.newCount)}</b><span>новых</span></button></div>
    <div class="goal"><div class="mgoal${d.sent.today >= d.sent.goal ? ' done' : ''}"><i style="width:${Math.max(pct, d.sent.today ? 3 : 0)}%"></i></div><span>${d.sent.today >= d.sent.goal ? 'цель дня взята' : `до цели ${nf.format(d.sent.goal - d.sent.today)}`}</span></div>`;
  const g = Object.fromEntries(d.groups.map(x => [x.key, x]));
  const gn = x => x.items.length + (x.more || 0);   // в группе — первые 60, остальные в «ещё»
  const chip = (k, lab) => g[k].items.length ? `<button type="button" class="tchip" data-blf="${k}" style="--c:${g[k].col}"><b>${nf.format(gn(g[k]))}</b>${lab}</button>` : '';
  const chips = chip('w:replied', 'ответили') + chip('w:due', 'пора дожать') + chip('w:queued', 'к отправке');
  if (chips) h += `<div class="today">${chips}</div>`;
  h += S.queue.length ? `<button type="button" class="btn primary wide" data-queue>${icon('right')}Пройти по очереди · ${nf.format(S.queue.length)}</button>` : `<div class="clear"><span class="clear-ic">${icon('check')}</span><b>Всё под контролем</b><p>Никто не ждёт ответа, дожимать и отправлять некому.</p>${d.newCount ? `<button type="button" class="btn primary" data-tab="new">${icon('search')}Выбрать из новых · ${nf.format(d.newCount)}</button>` : ''}</div>`;
  // «ещё»: разделы очереди — в Базе тем же фильтром, черновики — в «Сообщениях» (как «Показать всех» у групп Базы)
  const moreBtn = x => !x.more ? '' : x.key === 'ready' ? `<div class="more"><button type="button" class="btn wide" data-tab="msgs">${icon('message')}Все черновики — в «Сообщениях» · ${nf.format(gn(x))}</button></div>`
    : `<div class="more"><button type="button" class="btn wide" data-blf="${esc(x.key)}">${icon('base')}Показать всех в «${esc(x.title)}» · ${nf.format(gn(x))}</button></div>`;
  for (const x of d.groups) if (x.items.length) { remember(x.items); h += groupHead(x, gn(x), true) + (isFolded(x.key) ? '' : `<div class="glist">${x.items.map(brow).join('')}</div>${moreBtn(x)}`); }
  const f = d.funnel || {};
  if (f.sent) {
    const row = (lab, n, col) => `<div class="fnrow" style="--w:${Math.round(n / f.sent * 100)}%;--c:${col}"><span>${lab}</span><span><b>${nf.format(n)}</b>${lab !== 'Написал' ? `<small>${Math.round(n / f.sent * 100)}%</small>` : ''}</span><i></i></div>`;
    h += `<h2>Итоги · 7 дней</h2><div class="fn">${row('Написал', f.sent, '#C6C7D2')}${row('Ответили', f.replied, '#38A0F0')}${row('Заинтересованы', f.interested, '#F2C94C')}${row('Клиенты', f.client, '#6FD39A')}${row('Отказы', f.declined, '#FF6B6B')}</div>`;
  }
  return h;
}
const KINDS = [['', 'Все типы'], ['hot', 'Без сайта'], ['warm', 'Шаблон'], ['social', 'Соцсеть']];
const SORTS = [['score', 'Сначала перспективные'], ['reviews', 'Больше отзывов'], ['rating', 'Выше рейтинг'], ['firstSeen', 'Сначала новые'], ['name', 'По названию']];
const PARSER_MAX = 1000;   // столько программа отдаёт за раз (bot.js RZ_NEW_MAX)
async function viewNew(more, quiet){
  const off = more ? S.parser.items.length : 0;
  // тихое обновление после «Показать ещё» перечитывает столько, сколько уже показано (до PARSER_MAX) — раньше список урезался до 30;
  // догрузили больше потолка — тихо не перерисовываем вовсе (урезало бы до потолка), обновит смена фильтра или вкладки
  if (!more && quiet && S.parser.items.length > PARSER_MAX) return null;
  const limit = !more && quiet ? Math.min(PARSER_MAX, Math.max(30, S.parser.items.length)) : 30;
  const d = await api('new', Object.assign({}, P.nf, { sort: P.sort, off, limit }));
  S.me = d.me !== false; if (d.stops) S.stops = d.stops;
  const list = remember(d.items);
  setTitle('Парсер', d.count === d.total ? `${nf.format(d.total)} новых · не в Базе` : `${nf.format(d.count)} из ${nf.format(d.total)} под фильтр`);
  if (more) { S.parser.items = S.parser.items.concat(list); return null; }
  S.parserNext = list;   // в S.parser.items — только если show() и правда перерисует (пока печатают, он пропускает)
  const f = d.filter;
  let h = `<div class="filters" role="group" aria-label="Фильтры">
    <label class="fchip" aria-pressed="${!!f.city}">${icon('pin', 'sm')}<select id="fCity" aria-label="Город"><option value="">Все города</option>${d.cities.map(c => `<option${c === f.city ? ' selected' : ''}>${esc(c)}</option>`).join('')}</select></label>
    ${KINDS.map(([k, lab]) => `<button type="button" class="fchip" data-kind="${k}" aria-pressed="${(f.kind || '') === k}">${k ? `<span class="dot ${k}"></span>` : ''}${lab}</button>`).join('')}
    <button type="button" class="fchip" data-mob aria-pressed="${!!f.mob}">${icon('phone', 'sm')}Мобильный</button>
    <label class="fchip" aria-pressed="false">${icon('filter', 'sm')}<select id="fSort" aria-label="Сортировка">${SORTS.map(([k, lab]) => `<option value="${k}"${k === d.sort ? ' selected' : ''}>${lab}</option>`).join('')}</select></label></div>`;
  h += `<p class="stats">Показано <b class="num" id="pShown">${nf.format(list.length)}</b> из ${nf.format(d.count)} · <span style="color:#FFB39E">${nf.format(d.hot)} без сайта</span> · <span style="color:#F5DA8A">${nf.format(d.warm)} с шаблоном</span></p>`;
  h += `<div class="btns" style="margin:0 0 var(--sp-el)"><button type="button" class="btn" data-run>${icon('search')}Найти новые: город и категория</button></div>`;
  h += d.items.length ? `<div class="list" id="pList">${d.items.map(pcard).join('')}</div>${d.more ? `<div class="more"><button type="button" class="btn wide" data-more data-left="${d.count - list.length}">${icon('plus')}Показать ещё ${Math.min(30, d.count - list.length)} из ${nf.format(d.count - list.length)}</button></div>` : ''}` : `<div class="empty"><b>Никого под фильтр</b>${d.total ? `Из ${nf.format(d.total)} новых ни один не подошёл.<br><button type="button" class="btn" data-reset>${icon('x')}Сбросить фильтры</button>` : 'Новых нет — нажмите «Найти новые» выше или запустите поиск в программе.'}</div>`;
  return h;
}
async function viewBase(more, quiet, lim){
  const n = lim && lim.k === 'base' ? lim.n : S.baseLim;   // «Показать ещё» просит больше; S.baseLim станет n, только если перерисовали
  const d = await api('base', n ? { f: P.bf, lim: n } : { f: P.bf });
  S.me = d.me !== false; if (d.stops) S.stops = d.stops;
  const cur = d.tiles.find(t => t.id === d.f) || {};
  setTitle('База', `${nf.format(d.all)} ${plural(d.all, 'заведение', 'заведения', 'заведений')} · ${cur.lab || ''}`);
  const tile = (t, i, a) => `<button type="button" class="bltile${t.id === d.f ? ' on' : ''}${t.attn ? ' attn' : ''}${t.n ? '' : ' zero'}${t.stop && !(a[i - 1] || {}).stop ? ' sep' : ''}" data-blf="${esc(t.id)}" aria-pressed="${t.id === d.f}" style="--c:${t.col}"><b>${nf.format(t.n)}</b><span>${esc(t.lab)}</span></button>`;
  let h = `<div class="bltiles" id="tiles">${d.tiles.map(tile).join('')}</div>`;
  const total = d.groups.reduce((a, g) => a + g.items.length, 0);
  if (!total) return h + `<div class="empty"><b>В разделе «${esc(cur.lab || '')}» никого</b>${d.all ? `<button type="button" class="btn" data-blf="work">${icon('base')}Показать всех в работе · ${nf.format((d.tiles.find(t => t.id === 'work') || {}).n || 0)}</button>` : `Возьмите заведения из «Парсера» — кнопка «В Базу».<br><button type="button" class="btn primary" data-tab="new">${icon('search')}Открыть Парсер</button>`}</div>`;
  for (const g of d.groups) {
    remember(g.items.filter(x => !x.stop));
    if (g.title) h += groupHead(g, g.items.length + (g.more || 0), true) + (isFolded(g.key) ? '' : `<div class="glist">${g.items.map(brow).join('')}</div>${g.more ? `<div class="more"><button type="button" class="btn wide" data-blf="${esc(g.f)}">${icon('base')}Показать всех в «${esc(g.title)}» · ${nf.format(g.items.length + g.more)}</button></div>` : ''}`);
    else h += `<div class="glist">${g.items.map(brow).join('')}</div>${listMore(g, 'data-bmore', 400)}`;   // раздел без групп: раньше молча обрезался до 400
  }
  return h;
}
// «Показать ещё» длинного списка (Раздел Базы без групп, группы «Сообщений»): попросить у программы больше; cap — дальше только на компьютере
const listMore = (g, attr, step) => !g.more ? '' : g.cap ? `<p class="hint" style="text-align:center">Ещё ${nf.format(g.more)} — в программе на компьютере.</p>`
  : `<div class="more"><button type="button" class="btn wide" ${attr} data-shown="${g.items.length}">${icon('plus')}Показать ещё ${nf.format(Math.min(step, g.more))} из ${nf.format(g.more)}</button></div>`;
async function viewMsgs(more, quiet, lim){
  const n = lim && lim.k === 'msgs' ? lim.n : S.msgLim;
  const d = await api('msgs', n ? { lim: n } : {});
  S.me = d.me; S.llm = d.llm;
  const pct = Math.min(100, Math.round(d.sent.today / d.sent.goal * 100));
  const gn = k => { const g = d.groups.find(x => x.key === k) || {}; return (g.items || []).length + (g.more || 0); };
  setTitle('Сообщения', [gn('reply') && `${gn('reply')} ждут ответа`, gn('ready') && `${gn('ready')} готово к отправке`, gn('need') && `${gn('need')} без текста`].filter(Boolean).join(' · ') || 'срочного нет');
  let h = `<div class="mtop"><span>Сегодня</span><span class="mgoal${d.sent.today >= d.sent.goal ? ' done' : ''}" role="img" aria-label="${d.sent.today} из ${d.sent.goal}"><i style="width:${pct}%"></i></span><span><b>${nf.format(d.sent.today)}</b> из ${nf.format(d.sent.goal)}</span><span>· за 7 дней ${nf.format(d.sent.week)}</span></div>`;
  if (!d.me) h += `<div class="warnbox">Впишите имя и регион в программе: Настройки → «Обо мне».</div>`;
  if (!d.groups.length) return h + `<div class="empty"><b>Писать пока некому</b>Нет ответов, готовых текстов и заведений «К отправке».<br><button type="button" class="btn primary" data-tab="new">${icon('search')}Взять в работу из Парсера</button></div>`;
  for (const g of d.groups) { remember(g.items); h += groupHead(g, g.items.length + (g.more || 0), true) + (isFolded(g.key) ? '' : `<div class="glist wide">${g.items.map(it => mcard(it, g)).join('')}</div>${listMore(g, 'data-mmore', 60)}`); }
  return h;
}
function mcard(it, g){
  const head = `<div class="mhead"><button type="button" class="mname" data-lead="${esc(it.id)}">${esc(it.name)}</button>${twinBadge(it)}${g.key === 'reply' ? '' : repliedBadge(it)}<span class="mmeta">${esc(it.meta)}</span></div>`;
  if (g.key === 'sent') return `<article class="mcard sent" style="--c:${g.col}">${head}<p class="msent">${it.sentVia ? `<b>${esc(it.sentVia)}:</b> ` : ''}${esc(it.sentText)}</p></article>`;
  return `<article class="mcard" style="--c:${g.col}" data-card="${esc(it.id)}">${head}
    ${it.inc ? `<blockquote class="mquote"><b>${esc(it.inc.via)}:</b> ${esc(it.inc.text)}</blockquote>` : ''}
    ${it.mrText != null ? `<div class="mquote">Ответили — отмечено вручную${it.mrText ? ': ' + esc(it.mrText) : ''}</div>` : ''}
    <textarea class="input mdraft" name="draft" data-draft="${esc(it.id)}" rows="4" spellcheck="true" aria-label="Текст для «${esc(it.name)}»" placeholder="${esc(it.placeholder || 'Текста нет. Напишите ответ, выберите готовый ниже или нажмите ✦…')}">${esc(it.draftText)}</textarea>
    ${it.tplOnly ? '<p class="mnote">Своего текста нет — уйдёт стандартный шаблон (серый текст выше).</p>' : ''}
    ${it.old ? `<p class="mnote">Этот текст уже отправлен ${esc(it.old)}. Измените его или выберите ответ ниже — получится новое сообщение.</p>` : ''}
    <span class="dstat" data-dstat="${esc(it.id)}"></span>
    <p class="dwarn" data-dwarn="${esc(it.id)}"${it.warnDraft && it.warnDraft.length ? '' : ' hidden'}>${it.warnDraft && it.warnDraft.length ? 'Проверьте: ' + esc(it.warnDraft.join('; ')) : ''}</p>
    <div class="mquick line" role="group" aria-label="Текст">${it.genDone ? '' : `<button type="button" class="ai" data-gen="${esc(it.id)}">${icon('spark', 'sm')}${it.draftText && (it.draftText || '').trim() ? 'Переписать ИИ' : 'Написать ИИ'}</button>`}${it.quick ? [['yes', 'После «так»'], ['price', 'Цена'], ['qr', 'Есть QR'], ['boss', 'Руководство']].map(([k, lab]) => `<button type="button" data-quick="${k}" data-id="${esc(it.id)}">${lab}</button>`).join('') : ''}</div>
    <div class="mfoot"><div class="cwrap">${chanBtns(it)}</div><span class="sp"></span>${g.key === 'reply' || !it.canMr ? '' : `<button type="button" class="pill${it.marked ? ' on' : ''}" data-mr="${esc(it.id)}" aria-pressed="${!!it.marked}">${icon('message', 'sm')}${it.marked ? 'Снять' : 'Ответили'}</button>`}</div>
  </article>`;
}
async function viewSearch(){
  const q = S.q; setTitle('Поиск', '«' + q + '»');
  const d = await api('search', { q });
  if (q !== S.q) return null;
  S.me = d.me !== false; if (d.stops) S.stops = d.stops;
  remember(d.items);
  return d.items.length ? `<div class="list">${d.items.map(brow).join('')}</div>` : `<div class="empty"><b>По «${esc(q)}» ничего</b>Ищу по названию, городу, нику Instagram, имени владельца и номеру.<br><button type="button" class="btn" data-clearq>${icon('x')}Очистить поиск</button></div>`;
}
const VIEWS = { today: viewToday, new: viewNew, base: viewBase, msgs: viewMsgs };
let showSeq = 0;
// force — перерисовать и при фокусе в поле (нажали «Показать ещё»: ждут список, а не печатают);
// lim — { k: 'base' | 'msgs', n } для «Показать ещё»: в S.baseLim / S.msgLim попадает, только если список и правда перерисован.
// true — экран перерисован
async function show(quiet, force, lim){
  const seq = ++showSeq, view = $('view'), y = window.scrollY;
  const f = S.q.length >= 2 ? viewSearch : VIEWS[S.tab] || viewToday;
  if (!quiet) { setTitle(S.q.length >= 2 ? 'Поиск' : TITLES[S.tab], ''); view.innerHTML = skel(4); }
  S.parserNext = null; S.note = '';
  try {
    let h = await f(false, quiet, lim);
    if (h != null && S.note) h = `<div class="warnbox">${esc(S.note)}</div>` + h;
    if (seq !== showSeq || h == null) return false;
    S.quietErr = false;
    if (quiet && !force && view.contains(document.activeElement) && document.activeElement.matches('textarea,input,select')) return false;   // пока печатают — не перерисовываем
    view.innerHTML = h;
    if (f === viewNew && S.parserNext) S.parser.items = S.parserNext;   // список парсера — тот, что на экране
    S.parserNext = null;
    if (lim && f === VIEWS[lim.k]) { if (lim.k === 'base') S.baseLim = lim.n; else S.msgLim = lim.n; }
    view.classList.toggle('view-in', !quiet); if (!quiet) setTimeout(() => view.classList.remove('view-in'), 400);
    bindView();
    if (quiet) window.scrollTo(0, y);
    return true;
  } catch (e) {
    if (seq !== showSeq) return false;
    // тихое обновление (таймер, возврат в приложение) не стирает список экраном ошибки — только подсказка, один раз;
    // нажатие («Показать ещё») — ошибку показываем каждый раз
    if (quiet && view.children.length) { if (force) fail(e); else if (!S.quietErr) { S.quietErr = true; if (e && e.dead) fail(e); else toast('Нет связи с программой — список не обновился. ' + (e.message || '')); } return false; }
    if (e && e.dead) { view.innerHTML = `<div class="empty"><b>Подписка закончилась</b>Продлите её в боте @LeaddHunterrBot: Меню → Тарифы подписки.${tg ? `<br><button type="button" class="btn" data-reopen>${icon('x')}Закрыть</button>` : ''}</div>`; return false; }
    view.innerHTML = `<div class="empty"><b>Не получилось загрузить</b>${esc(e.message || e)}${e.reopen ? '<br>Закройте приложение и откройте заново кнопкой LeadHunter в боте — адрес и подпись обновятся.' : ''}<br><button type="button" class="btn primary" data-retry>${icon('right')}Повторить</button>${e.reopen && tg ? `<br><button type="button" class="btn" data-reopen>${icon('x')}Закрыть приложение</button>` : ''}</div>`;
    return false;
  }
}
function bindView(){
  const c = $('fCity'); if (c) c.onchange = e => { keep('nf', Object.assign({}, P.nf, { city: e.target.value })); haptic('sel'); show(); };
  const s = $('fSort'); if (s) s.onchange = e => { keep('sort', e.target.value); haptic('sel'); show(); };
  const t = $('tiles'); if (t) { const on = t.querySelector('.on'); if (on) { const dx = on.getBoundingClientRect().left - t.getBoundingClientRect().left; if (dx < 12 || dx + on.offsetWidth > t.clientWidth - 12) t.scrollLeft += dx - 12; } }
}
function setTab(tab){
  const nt = TITLES[tab] ? tab : 'today';
  if (nt !== S.tab) S.msgLim = 0;   // «Показать ещё» «Сообщений» — до ухода с вкладки (Базы — до смены раздела, data-blf)
  S.tab = nt; keep('tab', S.tab);
  S.q = ''; $('q').value = '';
  document.querySelectorAll('.rail-btn').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === S.tab)));
  try { window.RZGfx && RZGfx.page(S.tab === 'base' ? 'base' : S.tab === 'msgs' ? 'msg' : 'lead'); } catch {}
  window.scrollTo(0, 0);
  show();
}

// ---- написать: как contact() окна ----
async function contact(src, ch, owner, forced, btn){
  const links = owner ? src.ownerLinks || [] : src.links || [];
  const k0 = links.find(x => x.ch === ch), k = k0 && Object.assign({}, k0);
  if (!k) { toast(`${CH[ch][0]}: ссылки нет — нет мобильного номера или профиля.`); return; }
  if (!S.me || src.me === false) { toast('Сначала впишите имя, регион и цену в программе: Настройки → «Обо мне».'); return; }
  if (!owner && !forced && src.claim && !S.claimOk[src.id]) {   // 3.10: уже трогали — как в окне, переспрашиваем
    pick('Уже трогали', `«${src.name}» — ${claimTxt(src.claim)}${/\.$/.test(claimTxt(src.claim)) ? '' : '.'}\n\nВладелец, скорее всего, уже получил такое же предложение — повторное сообщение он примет за спам.`,
      [{ label: `Всё равно открыть ${k.label}`, pri: true, fn: () => { S.claimOk[src.id] = 1; contact(src, ch, owner, forced, btn); } }]);
    return;
  }
  if (!owner && !forced && src.twinHot && src.twinHot.length && !S.twinOk[src.id]) {
    pick('Тот же владелец', `У «${src.name}» тот же владелец, что у:\n${src.twinHot.map(x => '• ' + x).join('\n')}\n\nВы уже работали с этим человеком. Всё равно открыть чат?`,
      [{ label: `Открыть ${k.label}`, pri: true, fn: () => { S.twinOk[src.id] = 1; contact(src, ch, owner, true, btn); } }]);
    return;
  }
  // поле черновика — там, откуда нажали: у лида есть и поле в карточке (#drawer), и в списке «Сообщений» под ней (раньше в DOM);
  // без кнопки (повтор после «Тот же владелец») — карточка, если открыта именно она
  const dr = document.getElementById('drawer');
  const scope = (btn && btn.closest && btn.closest('#drawer, .mcard')) || (S.lead && S.lead.id === src.id && dr && !dr.hidden ? dr : document);
  const box = scope.querySelector(`[data-draft="${CSS.escape(src.id)}"]`) || document.querySelector(`[data-draft="${CSS.escape(src.id)}"]`);
  // черновик с замечанием (ссылка, цена — src.risk от программы): в буфер и в ссылку чата не кладём, как contact() окна.
  // Поле правили после проверки, а сохранение ещё не ушло — замечание могло и остаться: решает свежая проверка программы.
  // Ждать её здесь нельзя — буфер телефона пускает копирование только сразу по нажатию, — поэтому сейчас не копируем
  // и чат не открываем: сохраняем черновик, следующее нажатие решит по свежему risk (saveDraft обновит его в списке и панели)
  // Прежний risk пуст, а в поле дописали ссылку или цену — тоже ждём проверки (грубая проверка здесь, точная — в программе).
  // Сохранение не прошло (retry) — честно: связи нет, «нажмите ещё раз» не поможет
  // только для черновика первого сообщения (src.firstDraft) — в ответах цена и демо законны, как и в программе;
  // повтор, пока сохранение ещё в пути (draftBusy), тоже ждёт: risk в списке ещё старый
  const pendD = !owner && src.firstDraft && (draftT[src.id] || (src.id in draftBusy ? { val: draftBusy[src.id] } : null));
  const RISK_RE = /https?:|www\.|[a-z0-9-]+\.(?:com|ua|net|org|site|app|me|io|shop|store|link|ly|page|online|xyz|cc|ee)\b|\.[a-z]{2,}\/|@[a-z][a-z0-9_]{3,}|\$\s?\d|\d\s?(?:\$|€|грн|гривен|гривн|uah|usd|доллар|долар|тис|тыс)/i;
  if (pendD && (src.risk || RISK_RE.test(pendD.val != null ? pendD.val : box ? box.value : ''))) {
    haptic('sel'); toast(pendD.retry ? 'Черновик не сохранился — нет связи с программой' : 'Сохраняю черновик — нажмите ещё раз через секунду'); if (draftT[src.id]) flushDraft().catch(() => {}); return;
  }
  const risky = !!src.risk;
  let text = owner ? src.ownerText : src.text;
  if (!owner && box && (box && box.value ? box.value.trim() : '') && !risky) text = box.value;
  const copied = text ? copyNow(text) : null;
  // в ссылке wa.me программа уже прислала свой text= (старый черновик) — ставим текущий текст вместо него, а не только в пустой
  if (k.ch === 'wa' && text) k.url = /[?&]text=/.test(k.url) ? k.url.replace(/([?&]text=)[^&#]*/, (m, p) => p + encodeURIComponent(text)) : k.url + (k.url.includes('?') ? '&' : '?') + 'text=' + encodeURIComponent(text);
  // не ждём: iOS открывает viber:/whatsapp: только сразу по нажатию. Касание уходит после сохранения черновика
  // (программа записывает отправленный текст из черновика), а чат открывается уже сейчас
  const fl = flushDraft().catch(() => {});
  if (ch === 'viber' && !k.web) {   // у Viber нет веб-ссылки: пробуем открыть приложение, а касание — по кнопке
    openUrl(k.url);
    const vOp = newOpId();   // двойное «Написал» по тосту — одна запись
    toast(`Viber: ${risky && !text ? 'черновик с замечанием — не скопирован, проверьте на компьютере' : text ? (copied ? 'текст скопирован' : 'текст НЕ скопирован') : 'текста нет'}. Написали?`, [{ label: 'Написал', fn: () => act(src.id, 'contact', { ch, owner, text: !!text, copied, twinOk: forced }, null, vOp) }], 12000);
    return;
  }
  haptic('ok');
  if (btn) btn.setAttribute('aria-busy', 'true');
  const opId = newOpId(), arg = { ch, owner, text: !!text, copied, twinOk: forced };
  const p = fl.then(() => api('act', { id: src.id, act: 'contact', arg, opId }));   // запрос уходит за сохранением черновика
  openUrl(k.url);
  // «Записать» — с тем же opId: если касание на самом деле дошло (потерялся только ответ), второй раз не запишется
  try { const d = await p; after(src.id, d); } catch (e) { toast('Чат открыт, но касание не записалось: ' + (e.message || e), [{ label: 'Записать', fn: () => act(src.id, 'contact', arg, null, opId) }], 12000); haptic('err'); }
  finally { if (btn && btn.isConnected) btn.removeAttribute('aria-busy'); }
}
// ответ программы на действие: тост с «Отменить», обновить панель и список
// a — какое действие: после «ИИ»/готового ответа новый текст ставим в поля черновика, даже если в них фокус (iOS держит фокус)
function after(id, d, quiet, a){
  const r = d.res || {};
  if (r.msg && !r.quiet) toast(r.msg, r.undo ? [{ label: 'Отменить', fn: () => act(id, 'undo', r.undo) }] : []);
  if (!quiet) haptic(r.ok === false ? 'err' : 'ok');
  const fresh = (a === 'gen' || a === 'quick') && r.ok && d.lead;
  if (fresh) {
    const dt = d.lead.draftText || '';
    clearTimeout((draftT[id] || {}).t); delete draftT[id];   // набранное до ответа заменено новым текстом — старое не досохранять поверх
    document.querySelectorAll(`[data-draft="${CSS.escape(id)}"]`).forEach(b => { b.value = dt; });
    const it = S.items[id]; if (it) { it.draftText = dt; it.text = d.lead.text || ''; it.risk = d.lead.risk || ''; }
    dstat(id, '');
  }
  if (S.lead && S.lead.id === id) {
    if (!d.lead) {   // лида больше нет («В стоп»): в очереди — к следующему, а не закрыть панель
      const { ids, label } = S.nav, i = ids.indexOf(id), nx = label && i >= 0 ? ids[i + 1] : '';
      if (label && i >= 0) S.nav = { ids: ids.filter(x => x !== id), label };
      if (nx) { openLead(nx); if (!r.quiet) show(true); } else closeLead();
      return;
    }
    S.lead.data = d.lead; renderLeadKeep(!!fresh);
  }
  if (!r.quiet) show(true);
}
// Перерисовать панель, не теряя набираемое: заметка/черновик в фокусе или ещё не сохранённые — вернуть значение, курсор и прокрутку
// (ответ долгого действия — сбор контактов, реестры, ИИ — раньше затирал заметку, которую печатали, пока он шёл)
let refocusing = false;
function renderLeadKeep(skipDraft){
  const dr = $('drawer'), y = dr.scrollTop, ae = document.activeElement, keep = [];
  dr.querySelectorAll('textarea[data-note],textarea[data-draft]').forEach(el => {
    const note = el.hasAttribute('data-note'); if (!note && skipDraft) return;
    const pend = note ? !!(notePend && notePend.id === el.dataset.note) : !!draftT[el.dataset.draft];
    if (el === ae || pend) keep.push({ sel: note ? 'textarea[data-note]' : 'textarea[data-draft]', v: el.value, f: el === ae, s: el.selectionStart, e: el.selectionEnd, st: el.scrollTop });
  });
  renderLead();
  for (const k of keep) {
    const el = dr.querySelector(k.sel); if (!el) continue;
    el.value = k.v; el.scrollTop = k.st;
    if (k.f) { refocusing = true; try { el.focus({ preventScroll: true }); el.setSelectionRange(k.s, k.e); } catch {} refocusing = false; }
  }
  dr.scrollTop = y;
}
async function act(id, a, arg, btn, opId){
  opId = opId || newOpId();
  if (btn) btn.setAttribute('aria-busy', 'true');
  if (a === 'scan' || a === 'reg' || a === 'gen' || a === 'who' || a === 'quick') toast(a === 'scan' ? 'Сбор контактов: читаю сайт и профиль — до минуты…' : a === 'reg' ? 'Проверяю реестры…' : a === 'who' ? 'Спрашиваю Telegram…' : 'Пишу текст…', null, 60000);
  try { const d = await api('act', { id, act: a, arg, opId }); after(id, d, false, a); }
  catch (e) { failRetry(e, () => act(id, a, arg, null, opId)); }
  finally { if (btn && btn.isConnected) btn.removeAttribute('aria-busy'); }
}
// черновик: сохраняется сам, пока печатаете (как поле в окне)
const draftT = {}, draftSeq = {}, draftBusy = {};   // draftBusy — сохранение черновика уже в пути (draftT удалён в его начале)
const dstat = (id, t, cls) => document.querySelectorAll(`[data-dstat="${CSS.escape(id)}"]`).forEach(el => { el.textContent = t; el.className = 'dstat' + (cls ? ' ' + cls : ''); });
function queueDraft(id, val){ clearTimeout((draftT[id] || {}).t); draftT[id] = { val, t: setTimeout(() => saveDraft(id), 900) }; unsentPut('d', id, val); dstat(id, 'Печатаете… сохраню сам'); }
// M2: набранное, но не подтверждённое программой — в localStorage; при следующем открытии досохраняем (unsentResend)
function unsentGet(){ try { const v = JSON.parse(localStorage.getItem('rzm.unsent') || 'null'); return v && typeof v === 'object' ? { d: v.d || {}, n: v.n || {} } : { d: {}, n: {} }; } catch { return { d: {}, n: {} }; } }
function unsentPut(k, id, val){ try { const u = unsentGet(); if (val === null) delete u[k][id]; else u[k][id] = val; localStorage.setItem('rzm.unsent', JSON.stringify(u)); } catch {} }
function unsentDone(k, id, val){ const u = unsentGet(); if (u[k][id] === val) unsentPut(k, id, null); }
function unsentResend(){
  const u = unsentGet();
  for (const [id, val] of Object.entries(u.d)) if (!draftT[id]) draftT[id] = { val, t: setTimeout(() => saveDraft(id), 1500) };
  const notes = Object.entries(u.n);
  (async () => { for (const [id, val] of notes) { if (notePend && notePend.id === id) continue; try { const d = await api('act', { id, act: 'noteSet', arg: val }); if (!(d && d.res && d.res.ok === false)) unsentDone('n', id, val); } catch {} } })();
  if (Object.keys(u.d).length || notes.length) toast('Досохраняю набранное в прошлый раз…');
}
async function saveDraft(id){
  const x = draftT[id]; if (!x) return; delete draftT[id]; clearTimeout(x.t); draftBusy[id] = x.val;
  const seq = draftSeq[id] = (draftSeq[id] || 0) + 1;
  dstat(id, 'Сохраняю…');
  try {
    const d = await api('act', { id, act: 'draft', arg: x.val });
    unsentDone('d', id, x.val);
    dstat(id, d.res && d.res.queued ? 'Сохранено на телефоне — запишется, когда компьютер заберёт очередь' : (x.val || '').trim() ? 'Сохранено — уйдёт этот текст' : 'Черновик очищен', 'ok');
    const w = document.querySelector(`[data-dwarn="${CSS.escape(id)}"]`), warn = (d.res && d.res.warn) || [];
    if (w) { w.hidden = !warn.length; w.textContent = warn.length ? 'Проверьте: ' + warn.join('; ') : ''; }
    // очистили черновик — старый текст в it.text не оставляем (значок канала скопировал бы его): текст из ответа программы или пусто
    // черновик с замечанием (risk) — текст для копирования не держим, как и программа
    const it = S.items[id]; if (it) { it.draftText = x.val; if (d.lead) it.risk = d.lead.risk || ''; it.text = it.risk ? '' : (x.val || '').trim() ? x.val : d.lead ? d.lead.text || '' : ''; }
    if (S.lead && S.lead.id === id && d.lead) S.lead.data = d.lead;
  } catch (e) {
    // новее этого сохранения уже что-то ушло или печатается — старый текст не возвращаем (он перетёр бы новый)
    if (draftSeq[id] !== seq || draftT[id]) return;
    dstat(id, 'Не сохранилось: ' + (e.message || e) + ' — повторю сам', 'err');
    draftT[id] = { val: x.val, retry: true, t: setTimeout(() => saveDraft(id), 15000) };   // раньше повтора не было, а автообновление вставало навсегда
  } finally { if (draftBusy[id] === x.val) delete draftBusy[id]; }
}
function flushDraft(){ return Promise.all(Object.keys(draftT).map(saveDraft)); }
const draftTyping = () => Object.values(draftT).some(x => !x.retry);   // ждущий повтора черновик не останавливает обновление

// ---- меню выбора снизу (catmenu окна) ----
function pick(title, note, opts){
  $('pickH').textContent = title; $('pickP').textContent = note || ''; $('pickP').hidden = !note;
  $('pickO').innerHTML = opts.map((o, i) => o.head ? `<div class="opt-h">${esc(o.head)}</div>` : `<button type="button" class="opt${o.pri ? ' pri' : ''}" data-i="${i}"${o.cur ? ' aria-current="true"' : ''}>${o.col ? `<i style="background:${o.col}"></i>` : ''}${esc(o.label)}${o.small ? `<small>${esc(o.small)}</small>` : ''}</button>`).join('') + `<button type="button" class="opt cancel" data-i="-1">Отмена</button>`;
  $('pickO').onclick = e => { const b = e.target.closest('[data-i]'); if (!b) return; closePick(); const o = opts[+b.dataset.i]; if (o && o.fn) o.fn(); };
  $('pick').classList.add('open'); haptic('sel');
  if (tg) try { tg.BackButton.show(); } catch {}
}
function closePick(){ $('pick').classList.remove('open'); if (tg && !S.lead) try { tg.BackButton.hide(); } catch {} }
$('pick').addEventListener('click', e => { if (e.target === $('pick')) closePick(); });
$('scrim').addEventListener('click', () => closeLead());
function stagePick(id){
  const it = (S.lead && S.lead.id === id && S.lead.data) || S.items[id]; if (!it) return;
  const cur = it.stage, inBase = cur !== 'new';
  const opts = [{ head: 'В работе' }].concat([['queued', 'К отправке'], ['contacted', 'Жду ответа'], ['interested', 'Заинтересован'], ['client', 'Клиент'], ['declined', 'Отказ']]
    .map(([s, lab]) => ({ label: lab, col: STAGE_COLORS[s], cur: s === cur, fn: () => s !== cur && act(id, 'stage', s) })));
  if (inBase) opts.push({ label: 'Вернуть в новые', small: 'обратно в парсер', fn: () => act(id, 'stage', 'new') });
  const stops = (S.lead && S.lead.id === id && S.lead.data.stops) || S.stops;
  if (stops) opts.push({ head: 'Стоп' }, ...stops.map(s => ({ label: s.label, col: '#FF6B6B', fn: () => act(id, 'stop', s.id) })));
  pick(inBase ? 'Перенести: «' + it.name + '»' : 'В Базу: «' + it.name + '»', '', opts);
}
function fuPick(id){
  const it = (S.lead && S.lead.id === id && S.lead.data) || S.items[id]; if (!it) return;
  const w = it.fu ? 'Дожал · напомнить через ' : 'Напомнить через ';
  pick('Дожим: «' + it.name + '»', it.fu ? it.fu.txt : 'Напоминания нет', [3, 7, 14].map(n => ({ label: w + n + ' ' + plural(n, 'день', 'дня', 'дней'), fn: () => act(id, 'follow', n) })).concat([{ label: 'Не дожимать', small: 'снять напоминание', fn: () => act(id, 'follow', 0) }]));
}

// ---- панель лида ----
function kv(ic, k, sub, v){ return `<div class="kv">${ic ? icon(ic, 'lead-ic') : ''}<div class="k"><b>${k}</b>${sub ? `<small>${sub}</small>` : ''}</div>${v ? `<div class="v">${v}</div>` : ''}</div>`; }
function renderLead(){
  const L = S.lead.data, id = L.id;
  const { ids, label } = S.nav, i = ids.indexOf(id);
  const pos = i >= 0 ? `${nf.format(i + 1)} / ${nf.format(ids.length)}${label ? `<small>${esc(label)}</small>` : ''}` : L.inBase ? 'в Базе' : '';
  let h = `<header class="d-head"><div class="d-nav"><button type="button" class="cbtn" data-nav="-1" aria-label="Предыдущий"${i > 0 ? '' : ' disabled'}>${icon('left')}</button><span class="d-pos">${pos}</span><button type="button" class="cbtn" data-nav="1" aria-label="${label && i >= ids.length - 1 ? 'Закончить очередь' : 'Следующий'}"${i >= 0 && (i < ids.length - 1 || label) ? '' : ' disabled'}>${icon('right')}</button></div><button type="button" class="cbtn" data-close aria-label="Закрыть">${icon('x')}</button></header>`;
  h += `<div class="d-badges">${kindBadge(L, true)}${repliedBadge(L)}${L.twinN ? `<span class="twin">${icon('phone', 'sm')}×${L.twinN + 1}</span>` : ''}${sBadge(L)}</div>
    ${claimPlate(L, true)}
    <h2 class="d-name">${esc(L.name)}</h2>
    <p class="d-sub">${icon('pin', 'sm')}${esc(L.city || 'город не указан')}${L.category ? `<span class="dotsep"></span>${esc(L.category)}` : ''}</p>`;
  h += L.warns.map(w => `<p class="dwarn" style="margin-top:10px">${esc(w)}</p>`).join('');
  h += `<div class="d-actions"><button type="button" class="btn d-stage${L.inBase ? ' in' : ''}" data-stage="${esc(id)}">${L.inBase ? sdot(L.stage) + esc(L.stageShort) : icon('plus') + 'В Базу'}</button>${L.inBase && !L.fu && L.stage !== 'declined' && L.stage !== 'client' ? `<button type="button" class="btn" data-fu="${esc(id)}">${icon('clock')}Напомнить</button>` : ''}<button type="button" class="btn danger" data-act="stopPick">${icon('ban')}В стоп</button></div>`;
  h += `<div class="d-kpis kstrip"><div><b>${L.rating != null ? Number(L.rating).toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : '—'}</b><span>рейтинг</span></div><div><b>${nf.format(L.reviews || 0)}</b><span>${plural(L.reviews || 0, 'отзыв', 'отзыва', 'отзывов')}</span></div><div><b>${L.touch ? esc(L.touch) : '—'}</b><span>${L.touch ? 'последнее касание' : 'касаний не было'}</span></div></div>`;
  if (L.fu || L.noFollow) h += `<p class="card-next" style="margin-top:10px">${fuChip(L, id)}${L.noFollow ? '<span class="fu soon">не дожимать</span>' : ''}</p>`;
  if (!L.me) h += `<p class="dwarn" style="margin-top:12px">Впишите имя и регион в программе: Настройки → «Обо мне» — без них текст не собирается.</p>`;
  // Они написали
  if (L.incoming) h += `<section class="d-sec"><h4>Они написали</h4><p class="them"><small>${esc(L.incoming.via)}</small>${esc(L.incoming.text)}</p></section>`;
  else if (L.marked) h += `<section class="d-sec"><h4>Ответили</h4><p class="them"><small>отмечено вручную</small>${esc(L.marked.text || 'текста нет — впишите в заметку, что ответили')}</p></section>`;
  // Написать
  const has = ch => L.links.some(x => x.ch === ch);
  const chb = (ch, sub, extra) => `<button type="button" class="chbtn ch-${ch}${extra || ''}" data-ch="${ch}" data-id="${esc(id)}">${icon(CH[ch][1])}<span><b>${CH[ch][0]}</b><small>${esc(sub)}</small></span></button>`;
  const mobP = L.phones.find(p => p.mob), via = mobP && mobP.src !== 'Google' ? 'по номеру с сайта' : 'по номеру';
  let c = '';
  if (L.ig) c += chb('ig', '@' + L.ig.nick + ' · ' + (L.ig.sure ? L.igSrc : 'проверьте профиль'), L.ig.sure ? '' : ' unsure');
  else c += `<button type="button" class="chbtn ghost" data-act="scan">${icon('ig')}<span><b>${L.scanned ? 'Instagram не найден' : 'Найти Instagram'}</b><small>${L.scanned ? 'обновить поиск' : 'на сайте и в поиске'}</small></span></button>`;
  if (has('tg')) c += chb('tg', mobP ? via : '@' + L.tg);
  if (has('viber')) c += chb('viber', via);
  if (has('wa')) c += chb('wa', via + ', с текстом');
  if (has('fb')) c += chb('fb', L.fb);
  if (L.call) c += `<button type="button" class="chbtn" data-act="call" aria-expanded="${!!S.callOpen}">${icon('phone')}<span><b>Позвонить</b><small>номер, скрипт, итог</small></span></button>`;
  if (L.call && S.callOpen) c += callBox(L);
  if (!mobP && L.phones.length) c += `<p class="hint">Номер городской — мессенджеров нет, только звонок.</p>`;
  if (!L.phones.length && !L.ig && !L.tg && !L.fb) c += `<p class="hint">Телефона нет — остаётся Instagram или визит лично.</p>`;
  h += `<section class="d-sec"><h4>Написать <small>текст скопируется, чат откроется</small></h4><div class="d-channels">${c}</div></section>`;
  // Текст
  const draftBox = `<textarea class="input mdraft" name="draft" data-draft="${esc(id)}" rows="5" spellcheck="true" aria-label="Текст сообщения" placeholder="${esc(L.placeholder || 'Текста нет. Напишите ответ, выберите готовый ниже или нажмите ✦…')}">${esc(L.draftText)}</textarea>`;
  h += `<section class="d-sec"><h4>Текст сообщения <small>${(L.draftText || '').trim() ? 'черновик' : L.placeholder ? 'шаблон' : ''}</small></h4>${draftBox}
    ${L.draftOld ? `<p class="mnote" style="margin-top:6px">Этот текст уже отправлен ${esc(L.draftOld)}. Измените его или выберите ответ — получится новое сообщение.</p>` : ''}
    <span class="dstat" data-dstat="${esc(id)}"></span><p class="dwarn" data-dwarn="${esc(id)}"${L.draftWarn.length ? '' : ' hidden'}>${L.draftWarn.length ? 'Проверьте: ' + esc(L.draftWarn.join('; ')) : ''}</p>
    ${L.quick ? `<div class="mquick" style="margin-top:8px" role="group" aria-label="Готовый ответ">${[['yes', 'После «так»'], ['price', 'Цена'], ['qr', 'Есть QR'], ['boss', 'Руководство']].map(([k, lab]) => `<button type="button" data-quick="${k}" data-id="${esc(id)}">${lab}</button>`).join('')}</div>` : ''}
    <div class="btns" style="margin-top:10px"><button type="button" class="btn" data-copy="text">${icon('copy')}Скопировать текст</button><button type="button" class="btn" data-gen="${esc(id)}"${L.genDone ? ' disabled' : ''}>${icon('spark')}${L.genDone ? 'Дожимов нет' : (L.draftText || '').trim() ? 'Переписать ИИ' : 'Написать ИИ'}</button></div>
    <div class="own-row"><span>Уже написали сами?</span><button type="button" class="pill" data-act="sentPick">Написал в…</button>${L.canMr && L.inBase ? `<button type="button" class="pill" data-mr="${esc(id)}">${L.marked ? 'Снять «ответили»' : 'Ответили'}</button>` : ''}</div></section>`;
  // Продавец и сеть: реквизиты с сайта меню и другие точки того же хозяина
  const O = [];
  if (L.legal) O.push(kv('', esc((L.legal.kind === 'fop' ? (L.legal.form || 'ФОП') + ' ' : '') + L.legal.name), 'продавец на сайте меню' + (L.legal.taxId ? ' · код ' + esc(L.legal.taxId) : '')));
  (L.twins || []).forEach(x => O.push(kv('', 'Тот же владелец: ' + esc(x.name), esc([x.city, x.why, x.state].filter(Boolean).join(' · ')), x.id ? `<button type="button" class="cbtn" data-lead="${esc(x.id)}" aria-label="Открыть ${esc(x.name)}">${icon('right')}</button>` : '')));
  if (O.length) h += `<section class="d-sec"><h4>Продавец и сеть</h4><div class="kvlist">${O.join('')}</div></section>`;
  // Контакты и аналитика
  const K = [];
  (L.phones || []).forEach(p => K.push(kv('phone', `<span class="num">${esc(p.pretty)}</span>`, esc((p.mob ? 'мобильный · ' : 'городской · ') + p.src), `<a class="cbtn" href="tel:+${esc(p.d)}" aria-label="Позвонить ${esc(p.pretty)}">${icon('phone')}</a><button type="button" class="cbtn" data-copyv="${esc(p.pretty)}" aria-label="Скопировать номер">${icon('copy')}</button>`)));
  (L.emails || []).forEach(e => K.push(kv('mail', esc(e), 'почта', `<button type="button" class="cbtn" data-copyv="${esc(e)}" aria-label="Скопировать почту">${icon('copy')}</button>`)));
  if (L.address) K.push(kv('pin', esc(L.address), 'адрес', `<button type="button" class="cbtn" data-copyv="${esc(L.address)}" aria-label="Скопировать адрес">${icon('copy')}</button>${L.maps ? `<button type="button" class="cbtn" data-open="${esc(L.maps)}" aria-label="Google Карты">${icon('external')}</button>` : ''}`));
  if (L.ig) K.push(kv('ig', 'Instagram @' + esc(L.ig.nick), esc(L.ig.dead ? 'профиль не открывается' : [L.ig.followersLabel && L.ig.followersLabel + ' подписчиков', L.ig.posts != null && L.ig.posts + ' публикаций', !L.ig.sure && 'не подтверждён'].filter(Boolean).join(' · ')) + (L.ig.bio ? `<br>«${esc(L.ig.bio)}»` : ''), `<button type="button" class="cbtn" data-open="${esc(L.ig.url)}" aria-label="Открыть профиль">${icon('external')}</button>`));
  if (L.website) K.push(kv('globe', esc(L.website.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')), L.menu ? esc('меню ' + (L.menu.platform || '') + ': ' + L.menu.line) : 'сайт', /^https?:/.test(L.website) ? `<button type="button" class="cbtn" data-open="${esc(L.website)}" aria-label="Открыть сайт">${icon('external')}</button>` : ''));
  [['TikTok', L.tiktok && '@' + L.tiktok], ['Facebook', L.fb], ['Telegram', L.tg && '@' + L.tg]].forEach(([k, v]) => { if (v) K.push(kv('', esc(v), k)); });
  h += `<section class="d-sec"><h4>Контакты и аналитика <small>${L.scanned ? '' : 'поиск не проводился'}</small></h4><div class="kvlist">${K.join('') || '<p class="hint" style="margin:10px 0 0">Контактов нет — поиск найдет сайт, Instagram и номера.</p>'}</div>
    <div class="btns" style="margin-top:10px"><button type="button" class="btn" data-act="scan">${icon('scan')}${L.scanned ? 'Обновить данные' : 'Найти сайт, соцсети, номера'}</button></div></section>`;
  // Заметка и касания
  h += `<section class="d-sec"><h4>Заметка <span class="saved" id="noteSaved">сохранено</span></h4><textarea class="input d-note" data-note="${esc(id)}" name="note" maxlength="20000" aria-label="Заметка" placeholder="Например: перезвонить в пятницу, владелец — Олег…">${esc(L.note)}</textarea>
    ${L.history.length ? `<ul class="hist">${L.history.slice().reverse().map(x => `<li><small>${esc(x.label)}</small>${esc(x.text)}</li>`).join('')}</ul>` : ''}</section>`;
  if (ids.length > 1 && i >= 0) {
    const nx = ids[i + 1], nm = nx && S.items[nx] ? S.items[nx].name : '';
    h += `<div class="d-dock"><button type="button" class="btn" data-nav="-1" aria-label="Предыдущий"${i > 0 ? '' : ' disabled'}>${icon('left')}</button><button type="button" class="btn primary" data-nav="1"${nx || label ? '' : ' disabled'}><span>${nx ? 'Следующий' + (nm ? ': ' + esc(nm) : '') : label ? 'Закончить очередь' : 'Это последний'}</span>${nx ? icon('right') : ''}</button></div>`;
  }
  $('drawer').innerHTML = h;
}
function callBox(L){
  const c = L.call;
  return `<div class="callbox"><div class="callnum"><a class="btn primary" href="tel:+${esc(c.d)}">${icon('phone')}${esc(c.phone)}</a><button type="button" class="btn" data-copyv="${esc(c.phone)}" aria-label="Скопировать номер">${icon('copy')}</button></div>
    ${c.ask ? `<p class="callhint">Спросить: <b style="color:var(--ink)">${esc(c.ask.name)}</b>${c.ask.role ? ' (' + esc(c.ask.role) + ')' : ''}${c.ask.first ? ` — начните с «Доброго дня! Підкажіть, будь ласка, ${esc(c.ask.first)} на місці?»` : ''}</p>` : ''}
    <p class="callscript">${esc(c.script)}</p><p class="callhint">Фраза — пауза — фраза. Темп задаёте вы.</p>
    <div class="own-row"><span>Итог:</span>${[['no', 'Не взяли'], ['talk', 'Поговорили'], ['write', 'Просили написать'], ['fail', 'Сорвался']].map(([k, lab]) => `<button type="button" class="pill" data-callres="${k}">${lab}</button>`).join('')}</div></div>`;
}
async function openLead(id, nav){
  if (nav) S.nav = nav;
  S.lead = { id, data: null }; S.callOpen = false;
  const dr = $('drawer');
  dr.innerHTML = `<header class="d-head"><div class="d-nav"></div><button type="button" class="cbtn" data-close aria-label="Закрыть">${icon('x')}</button></header>` + skel(3);
  dr.classList.add('open'); dr.setAttribute('aria-hidden', 'false'); dr.scrollTop = 0; $('scrim').classList.add('on');
  document.querySelectorAll('.active').forEach(x => x.classList.remove('active'));
  if (tg) try { tg.BackButton.show(); } catch {}
  haptic();
  try {
    const d = await api('lead', { id });
    if (!S.lead || S.lead.id !== id) return;
    if (d.gone) { closeLead(); toast('Этого заведения уже нет в программе'); return; }
    S.lead.data = d.lead; S.stops = d.lead.stops; renderLead();
  } catch (e) { fail(e); closeLead(); }
}
// тихо перечитать открытую карточку (без скелета и без прокрутки наверх)
async function refreshLead(){
  if (!S.lead || !S.lead.data) return; const id = S.lead.id;
  try { const d = await api('lead', { id }); if (!S.lead || S.lead.id !== id) return; if (d.gone) { closeLead(); toast('Этого заведения уже нет в программе'); return; } S.lead.data = d.lead; renderLeadKeep(); } catch {}
}
function closeLead(){
  if (!S.lead) return;
  flushDraft(); flushNote();
  const id = S.lead.id;
  $('drawer').classList.remove('open'); $('drawer').setAttribute('aria-hidden', 'true'); $('scrim').classList.remove('on');
  S.lead = null; closePick();
  if (tg) try { tg.BackButton.hide(); } catch {}
  show(true).then(() => { const el = document.querySelector(`#view [data-lead="${CSS.escape(id)}"]`); if (el && el.matches('.card,.brow')) { el.classList.add('active'); el.scrollIntoView({ block: 'nearest' }); } });
}
function navLead(step){
  if (!S.lead) return;
  const { ids, label } = S.nav, i = ids.indexOf(S.lead.id);
  if (i < 0) return;   // панель открыта не из списка (ссылка «Тот же владелец», из бота) — ids[0] был бы чужим лидом
  const n = ids[i + step];
  if (n) { haptic('sel'); openLead(n); return; }
  if (step > 0 && label) { closeLead(); toast('Очередь пройдена'); }
}
// заметка — целиком, как поле в окне; сохраняется при паузе в наборе
let noteT = 0, notePend = null;
function flushNote(){
  if (!notePend) return; const x = notePend; notePend = null; clearTimeout(noteT);
  api('act', { id: x.id, act: 'noteSet', arg: x.val }).then(d => {
    const r = (d && d.res) || {};
    if (r.ok === false) { toast(r.msg || 'Заметка не сохранилась.'); return; }   // длиннее 20 000 — программа не режет молча, а отказывает
    unsentDone('n', x.id, x.val);
    if (S.lead && S.lead.id === x.id && d && d.lead) S.lead.data = d.lead;   // иначе «Позвонить» перерисовал бы старую заметку
    const s = $('noteSaved'); if (s) { s.classList.add('on'); setTimeout(() => s.classList.remove('on'), 1200); }
  })
    .catch(e => {   // заметка после звонка при плохой связи пропадала; теперь держим и повторяем, пока не уйдёт
      if (!notePend) { notePend = x; clearTimeout(noteT); noteT = setTimeout(flushNote, 15000); }
      toast('Заметка не сохранилась — повторю через 15 с: ' + (e.message || e));
    });
}

// ---- M3: поиск с телефона — пара «город × категория» из настроек программы, подтверждение с ценой ----
async function runPick(btn){
  if (btn) btn.setAttribute('aria-busy', 'true');
  let info; try { info = await api('runInfo'); } catch (e) { fail(e); return; } finally { if (btn && btn.isConnected) btn.removeAttribute('aria-busy'); }
  if (info.running) { toast('На компьютере уже идёт поиск…'); runWatch(); return; }
  if (!(info.cities || []).length || !(info.cats || []).length) { toast('В программе не заданы города или категории поиска — добавьте их на компьютере (вкладка «Поиск»).'); return; }
  pick('Поиск: город', 'Города и категории — из настроек поиска в программе.', info.cities.map(c => ({ label: c, fn: () => pick('Поиск: категория', c, info.cats.map(k => ({ label: k, fn: () => runConfirm(info, c, k) }))) })));
}
async function runConfirm(info, city, cat){
  let p = null; try { p = (await api('runInfo', { city, cat })).pair; } catch {}
  const req = (p && p.req) || info.pages || 1, cost = p ? p.cost : (req / 1000 * (info.price || 0)).toFixed(2).replace('.', ',');
  const note = `«${cat}» в ${city}\nДо ${req} ${plural(req, 'запроса', 'запросов', 'запросов')} к Google — максимум ≈ $${cost} по вашей цене (без бесплатного лимита Google).`
    + (p && p.recent ? `\nЭту пару уже искали ${p.recent.day}: нашлось ${p.recent.found}, новых ${p.recent.added}.` : '')
    + (info.key ? '' : '\nНа компьютере нет ключа Google API — поиск не запустится.')
    + (REMOTE && !pcOn() ? '\nКомпьютер сейчас не на связи — поиск выполнится, когда он заберёт очередь.' : '');
  pick('Запустить поиск?', note, [{ label: `Искать · ≈ $${cost}`, pri: true, fn: () => runGo(city, cat) }]);
}
async function runGo(city, cat){
  toast('Запускаю поиск…', null, 30000);
  try { const d = await api('run', { city, cat }); const r = d.res || {}; haptic(r.ok === false ? 'err' : 'ok'); toast(r.msg || (r.ok ? 'Поиск запущен' : 'Поиск не запустился'), null, 9000); if (r.ok && !r.queued) runWatch(); }
  catch (e) { fail(e); }
}
let runT = 0;
function runWatch(){
  clearTimeout(runT);
  runT = setTimeout(async () => {
    let st; try { st = await api('runState'); } catch { return; }
    if (st.running) { toast(`Поиск · ${st.pct || 0}% — ${st.log || 'идёт'}`, null, 6000); runWatch(); }
    else if (st.log) { toast(st.log, null, 12000); if (S.tab === 'new' && !S.lead) show(true); }
  }, REMOTE ? 5000 : 3000);
}

// ---- нажатия ----
document.addEventListener('click', e => {
  const t = e.target.closest('button,a,[data-lead]'); if (!t) return;
  if (t.matches('a[href^="tel:"]')) return;
  const d = t.dataset;
  if (t.id === 'sync') { haptic(); if (REMOTE) R.syncAt = 0; show(true); if (S.lead) refreshLead(); return; }   // постоянный адрес: и снимок перечитать сейчас
  if (d.tab) { if (t.classList.contains('rail-btn') && S.tab === d.tab && !S.q) { window.scrollTo({ top: 0, behavior: 'smooth' }); return; } haptic('sel'); setTab(d.tab); return; }
  if (t.hasAttribute('data-retry')) { show(); return; }
  if (t.hasAttribute('data-reopen')) { try { tg.close(); } catch {} return; }
  if (t.hasAttribute('data-close')) { closeLead(); return; }
  if (d.nav) { navLead(+d.nav); return; }
  if (d.ch) {
    const src = S.lead && S.lead.id === d.id && S.lead.data ? S.lead.data : S.items[d.id];
    if (src) contact(src, d.ch, !!d.owner, false, t); return;
  }
  if (d.stage) { stagePick(d.stage); return; }
  if (d.fu) { fuPick(d.fu); return; }
  if (d.mr) { const it = (S.lead && S.lead.id === d.mr && S.lead.data) || S.items[d.mr]; act(d.mr, 'mr', !(it && it.marked), t); return; }   // желаемое состояние: повтор не переключит назад
  if (d.gen) { flushDraft().then(() => act(d.gen, 'gen', null, t)); return; }
  if (d.quick) { flushDraft().then(() => act(d.id, 'quick', d.quick, t)); return; }
  if (d.callres) { S.callOpen = false; act(S.lead.id, 'call', d.callres); return; }
  if (d.blf) { haptic('sel'); if (d.blf !== P.bf) S.baseLim = 0; keep('bf', d.blf); if (S.tab !== 'base') setTab('base'); else show(); return; }
  if (t.hasAttribute('data-bmore') || t.hasAttribute('data-mmore')) {   // «Показать ещё» Базы / «Сообщений»: перечитать с бóльшим лимитом, прокрутка на месте
    // force: перерисовать и при фокусе в черновике; лимит запоминается, только если список вырос (ошибка — прежний)
    const bm = t.hasAttribute('data-bmore'), lim = { k: bm ? 'base' : 'msgs', n: (+d.shown || 0) + (bm ? 400 : 60) };
    // S.moreBusy — идёт показ по кнопке: таймер и возврат в приложение в это время свой тихий show не запускают
    // (новый show перебил бы этот по showSeq, и «ещё» не догрузилось бы)
    t.setAttribute('aria-busy', 'true'); haptic('sel'); S.moreBusy = (S.moreBusy || 0) + 1;
    flushDraft().then(() => show(true, true, lim)).catch(() => {}).finally(() => { S.moreBusy--; if (t.isConnected) t.removeAttribute('aria-busy'); });   // набранное в черновиках — сначала сохранить, перерисовка заменит поля
    return;
  }
  if (t.hasAttribute('data-queue')) { if (S.queue && S.queue.length) openLead(S.queue[0], { ids: S.queue.slice(), label: 'очередь' }); return; }
  if (t.hasAttribute('data-more')) { t.setAttribute('aria-busy', 'true'); viewNew(true).then(() => { const list = $('pList'); if (!list) return; const have = list.querySelectorAll('.card').length; list.insertAdjacentHTML('beforeend', S.parser.items.slice(have).map(pcard).join('')); $('pShown').textContent = nf.format(S.parser.items.length); t.removeAttribute('aria-busy'); const left = +t.dataset.left - (S.parser.items.length - have); t.dataset.left = left; if (left <= 0) t.parentNode.remove(); else t.innerHTML = icon('plus') + `Показать ещё ${Math.min(30, left)} из ${nf.format(left)}`; }).catch(e => { t.removeAttribute('aria-busy'); fail(e); }); return; }
  if (t.hasAttribute('data-reset')) { haptic('sel'); keep('nf', {}); show(); return; }
  if (t.hasAttribute('data-run')) { runPick(t); return; }
  if (t.hasAttribute('data-clearq')) { S.q = ''; $('q').value = ''; show(); return; }
  if (d.kind != null) { haptic('sel'); keep('nf', Object.assign({}, P.nf, { kind: d.kind })); show(); return; }
  if (t.hasAttribute('data-mob')) { haptic('sel'); keep('nf', Object.assign({}, P.nf, { mob: !P.nf.mob })); show(); return; }
  if (d.grp) { const k = S.tab + '|' + d.grp, f = Object.assign({}, P.fold); f[k] = !isFolded(d.grp); keep('fold', f); haptic('sel'); show(true); return; }
  if (d.open) { openUrl(d.open); return; }
  if (d.copyv) { copy(d.copyv); return; }
  const L = S.lead && S.lead.data;
  if (d.copy && L) { const box = $('drawer').querySelector('[data-draft]'); const txt = (box && (box && box.value ? box.value.trim() : '')) ? box.value : L.textAny; if (!txt) toast('Копировать нечего: черновика нет, а первое сообщение уже уходило. Напишите текст или нажмите «Сгенерировать».'); else copy(txt, box && (box && box.value ? box.value.trim() : '') ? 'Черновик скопирован' : 'Шаблон скопирован'); return; }
  if (d.act && L) {
    const a = d.act;
    if (a === 'call') { S.callOpen = !S.callOpen; renderLeadKeep(); return; }
    if (a === 'stopPick') return pick('В стоп — почему?', 'Заведение уйдёт из списков. Вернуть можно в программе: База → Стоп.', L.stops.map(s => ({ label: s.label, fn: () => act(L.id, 'stop', s.id) })));
    if (a === 'sentPick') { const chs = L.links.length ? L.links.map(x => [x.ch, x.label]) : Object.entries(CH).map(([k, v]) => [k, v[0]]); return pick('Написал сам — где?', 'Касание запишется, как на компьютере: стадия «Жду ответа», дожим перенесётся.', chs.map(([ch, lab]) => ({ label: lab, fn: () => act(L.id, 'contact', { ch, text: !!L.text, copied: false, manual: true }) }))); }   // ничего не копировали — свой текст тоста
    act(L.id, a, d.arg, t); return;
  }
  if (d.lead && !e.target.closest('button:not([data-lead]),a,select,textarea,input')) {
    const inList = t.closest('#view');
    openLead(d.lead, inList ? { ids: listIds(), label: '' } : null);
  }
});
document.addEventListener('input', e => {
  const t = e.target;
  if (t.matches('[data-draft]')) { queueDraft(t.dataset.draft, t.value); return; }
  if (t.matches('[data-note]')) { notePend = { id: t.dataset.note, val: t.value }; unsentPut('n', t.dataset.note, t.value); clearTimeout(noteT); noteT = setTimeout(flushNote, 900); }
});
document.addEventListener('focusin', e => {
  if (e.target.matches('[readonly],[data-tmp]')) return;   // временное поле copyNow — не «печатают»
  if (refocusing && e.target.matches('textarea')) { document.body.classList.add('typing'); return; }   // вернули фокус после перерисовки панели — без прокрутки
  if (e.target.matches('textarea,input[type=search],input:not([type])')) { document.body.classList.add('typing'); setTimeout(() => e.target.scrollIntoView({ block: 'center', behavior: 'smooth' }), 250); }
});
document.addEventListener('focusout', e => { if (e.target.matches('textarea,input')) setTimeout(() => { if (!document.activeElement || !document.activeElement.matches('textarea,input')) document.body.classList.remove('typing'); }, 60); });
document.addEventListener('focusout', e => { if (e.target.matches('[data-draft]')) saveDraft(e.target.dataset.draft); if (e.target.matches('[data-note]')) flushNote(); });
let qT = 0;
$('q').addEventListener('input', e => { clearTimeout(qT); qT = setTimeout(() => { S.q = e.target.value.trim(); window.scrollTo(0, 0); show(); }, 280); });
$('q').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); e.target.blur(); } });
document.addEventListener('keydown', e => { if (e.key === 'Escape') { if ($('pick').classList.contains('open')) closePick(); else if (S.lead) closeLead(); } });
// панель: смахнуть влево/вправо — соседний лид, как стрелки в окне
(() => {
  let x0 = 0, y0 = 0, t0 = 0;
  $('drawer').addEventListener('touchstart', e => { if (e.touches.length !== 1 || e.target.closest('textarea,input')) { t0 = 0; return; } x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; t0 = Date.now(); }, { passive: true });
  $('drawer').addEventListener('touchend', e => {
    if (!t0 || Date.now() - t0 > 600) return;
    const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
    if (Math.abs(dx) > 80 && Math.abs(dy) < 45) navLead(dx < 0 ? 1 : -1);
  }, { passive: true });
})();
// высота шапки — для липких заголовков групп
const topH = () => document.documentElement.style.setProperty('--top-h', $('top').offsetHeight + 'px');
window.addEventListener('resize', topH);

// ---- запуск ----
(async function start(){
  if (tg) {
    try {
      tg.ready(); tg.expand();
      tg.setHeaderColor && tg.setHeaderColor('#050505'); tg.setBackgroundColor && tg.setBackgroundColor('#030303'); tg.setBottomBarColor && tg.setBottomBarColor('#040404');
      if (tg.disableVerticalSwipes && tg.isVersionAtLeast && tg.isVersionAtLeast('7.7')) tg.disableVerticalSwipes();   // прокрутка вверх не сворачивает приложение
      tg.BackButton.onClick(() => { if ($('pick').classList.contains('open')) closePick(); else closeLead(); });
      const sa = () => { const s = tg.safeAreaInset || {}, c = tg.contentSafeAreaInset || {}; document.documentElement.style.setProperty('--tg-safe-t', ((s.top || 0) + (c.top || 0)) + 'px'); document.documentElement.style.setProperty('--tg-safe-b', ((s.bottom || 0) + (c.bottom || 0)) + 'px'); topH(); };
      sa(); tg.onEvent && tg.onEvent('safeAreaChanged', sa); tg.onEvent && tg.onEvent('contentSafeAreaChanged', sa);
    } catch {}
  }
  // Universal browser and Telegram compatibility
  if (!tg || !tg.initData) {
    console.info('LeadHunter WebApp: Browser preview mode active');
  }
  await prefsLoad();
  if (REMOTE) {   // последний снимок и очередь — сразу, без сети
    try { const c = JSON.parse(localStorage.getItem('rzm.snap') || 'null'); if (c && c.snap) { R.snap = c.snap; R.srvAt = c.srvAt || ''; } } catch {}
    try { R.pend = JSON.parse(localStorage.getItem('rzm.pend') || '{}') || {}; for (const [k, p] of Object.entries(R.pend)) if (!p || Date.now() - (p.at || 0) > 7 * 864e5) delete R.pend[k]; } catch { R.pend = {}; }
    setInterval(() => { if (!document.hidden && Object.keys(R.pend).length && !R.syncP) remoteSync(true).catch(() => syncState('off')); }, 4000);
  }
  gfxBoot();
  topH();
  // ссылка из бота: ?l=<id> — сразу карточка, ?t=<вкладка> — раздел
  const u = new URLSearchParams(location.search);
  const tab = TITLES[u.get('t')] ? u.get('t') : P.tab;
  S.tab = TITLES[tab] ? tab : 'today';
  document.querySelectorAll('.rail-btn').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === S.tab)));
  show().then(() => unsentResend());
  if (u.get('l')) openLead(u.get('l'), null);
  setInterval(() => {
    if (document.hidden || apiBusy || draftTyping() || $('pick').classList.contains('open') || document.body.classList.contains('typing') || S.q) return;
    if (S.lead) refreshLead(); else if (!S.moreBusy) show(true);
  }, 60000);
  // B4: свернули (ушли в чат, вызов) или закрывают — набранное уходит сейчас же, запрос переживает выгрузку (keepalive);
  // и лежит в localStorage до подтверждения программы
  const flushAll = () => { try { flushDraft().catch(() => {}); flushNote(); } catch {} };
  window.addEventListener('pagehide', flushAll);
  document.addEventListener('visibilitychange', () => { if (document.hidden) { clearTimeout(toastT); flushAll(); return; } armToast(); if (draftTyping()) return; if (!S.lead) { if (!S.moreBusy) show(true); } else if (!$('drawer').contains(document.activeElement) || !document.activeElement.matches('textarea,input')) refreshLead(); });
})();
