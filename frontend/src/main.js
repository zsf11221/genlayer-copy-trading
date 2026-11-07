import { createClient, createAccount } from 'genlayer-js';
import { studionet } from 'genlayer-js/chains';
import { TransactionStatus, TransactionHashVariant } from 'genlayer-js/types';
import { I18N } from './i18n.js';
import {
  CONTRACT_ADDRESS, CHAIN_ID, CHAIN_ID_HEX, RPC_URL, EXPLORER, MICRO, isConfigured,
} from './config.js';

const $ = (id) => document.getElementById(id);
const readClient = createClient({ chain: studionet });
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// ---------- i18n ----------
let lang = localStorage.getItem('ca-lang') || 'zh';
const t = (key, vars) => {
  let s = (I18N[lang] && I18N[lang][key]) ?? I18N.en[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v));
  return s;
};
const fmtInt = (n) => new Intl.NumberFormat(lang === 'zh' ? 'zh-CN' : 'en-US').format(n);
const fmtNum = (n, d = 2) => new Intl.NumberFormat(lang === 'zh' ? 'zh-CN' : 'en-US', { minimumFractionDigits: d, maximumFractionDigits: d }).format(n);

function applyLang(next) {
  lang = next;
  localStorage.setItem('ca-lang', lang);
  document.documentElement.lang = lang === 'zh' ? 'zh' : 'en';
  document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $('lang-en').setAttribute('aria-pressed', String(lang === 'en'));
  $('lang-zh').setAttribute('aria-pressed', String(lang === 'zh'));
  renderAll();
}

// ---------- state ----------
const state = {
  traders: [], // {address,name,stake,reputation,followers,copy_pnl,badge}
  records: [], // {id,trader,evidence,status,verdict,verdict_reason,history,appeal_count}
  copies: [], // {id,trader,follower,principal,status,pnl,trader_share,follower_return}
  pool: null,
  selectedTrader: null, // address
  filterMine: false,
  signer: null, // {kind:'wallet', address, provider} | {kind:'test', account, address}
  balance: null,
  feed: [],
  updatedAt: null,
  loaded: false, // true after the first chain load attempt (success or fail)
  prevOrder: [],
  prevVerdict: {},
  displayed: {}, // key -> current animated number (GEN float)
};

const shortAddr = (a) => (a ? `${a.slice(0, 6)}…${a.slice(-4)}` : '—');
const txUrl = (h) => `${EXPLORER}/tx/${h}`;
const addrUrl = (a) => `${EXPLORER}/address/${a}`;
const escapeHtml = (s) => String(s ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const microToGen = (micro) => Number(BigInt(String(micro ?? '0'))) / 1e6;
const fmtGen = (micro, d = 2) => fmtNum(microToGen(micro), d);
const signedGen = (micro) => {
  const v = microToGen(micro);
  return (v > 0 ? '+' : '') + fmtNum(v, 2);
};

// ---------- toast ----------
let toastTimer = null;
function toast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 4500);
}

// ---------- chain reads (Map / object tolerant) ----------
function asArray(v) {
  if (Array.isArray(v)) return v;
  if (v && typeof v === 'object') return Object.values(v);
  return [];
}
function asObject(v) {
  if (v instanceof Map) return Object.fromEntries(v);
  return v && typeof v === 'object' ? v : {};
}

async function readView(fn, args) {
  return readClient.readContract({
    address: CONTRACT_ADDRESS,
    functionName: fn,
    args,
    transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
  });
}

async function loadAll() {
  if (!isConfigured) {
    $('not-deployed').hidden = false;
    $('wall').innerHTML = '';
    $('wall-empty').hidden = false;
    $('copies-body').innerHTML = `<tr><td colspan="8" class="empty">${t('hall.empty')}</td></tr>`;
    $('tick-pool').textContent = '—';
    $('tick-traders').textContent = '—';
    $('tick-copypnl').textContent = '—';
    const link = $('contract-link');
    link.textContent = t('foot.contract');
    link.removeAttribute('href');
    $('foot-contract').textContent = '—';
    $('foot-contract').removeAttribute('href');
    return;
  }
  try {
    $('wall').setAttribute('aria-label', t('hall.loading'));
    const [tradersRaw, recordsRaw, copiesRaw, poolRaw] = await Promise.all([
      readView('list_traders', []),
      readView('list_records', []),
      readView('list_copies', []),
      readView('get_platform_pool', []),
    ]);
    state.traders = asArray(tradersRaw).map(asObject)
      .sort((a, b) => Number(b.copy_pnl || '0') - Number(a.copy_pnl || '0') || Number(b.reputation || '0') - Number(a.reputation || '0'));
    state.records = asArray(recordsRaw).map(asObject).sort((a, b) => Number(a.id) - Number(b.id));
    state.copies = asArray(copiesRaw).map(asObject).sort((a, b) => Number(a.id) - Number(b.id));
    state.pool = poolRaw;
    state.updatedAt = new Date();
    state.loaded = true;
    renderAll();
    await refreshBalance();
  } catch (e) {
    console.error('loadAll', e);
    state.loaded = true;
    $('wall').innerHTML = '';
    $('wall-empty').hidden = true;
    const wall = $('wall');
    const li = document.createElement('li');
    li.innerHTML = `<p class="wall-empty">${escapeHtml(t('hall.loadFailed'))}</p>`;
    wall.appendChild(li);
    toast(t('trade.networkError'));
  }
}

async function refreshBalance() {
  const line = (v) => { $('balance-line').textContent = v; $('balance-line-2').textContent = v; };
  if (!state.signer) { line(t('balance.noWallet')); return; }
  try {
    const bal = await readView('get_balance', [state.signer.address]);
    state.balance = BigInt(String(bal));
    line(t('balance.gen', { gen: fmtGen(state.balance, 6) }));
  } catch (e) {
    console.error('balance', e);
  }
}

// ---------- live numbers (Stripe-style: tween to the real value) ----------
function tweenNumber(el, key, target, format) {
  if (reducedMotion || typeof target !== 'number' || !Number.isFinite(target)) {
    el.textContent = format(target);
    state.displayed[key] = target;
    return;
  }
  const from = state.displayed[key] ?? 0;
  const start = performance.now();
  const dur = 650;
  const step = (now) => {
    const p = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    const v = from + (target - from) * eased;
    el.textContent = format(v);
    if (p < 1) requestAnimationFrame(step);
    else state.displayed[key] = target;
  };
  requestAnimationFrame(step);
}

// ---------- rendering ----------
function renderAll() {
  renderTicker();
  renderWall();
  renderRoom();
  renderCopies();
  renderSelects();
  renderSignerLine();
  if (state.updatedAt) {
    const time = state.updatedAt.toLocaleTimeString(lang === 'zh' ? 'zh-CN' : 'en-US');
    $('updated-line').textContent = t('hero.updated', { time });
    $('foot-updated').textContent = t('hero.updated', { time });
  }
  if (isConfigured) {
    const link = $('contract-link');
    link.textContent = shortAddr(CONTRACT_ADDRESS);
    link.href = addrUrl(CONTRACT_ADDRESS);
    const foot = $('foot-contract');
    foot.textContent = CONTRACT_ADDRESS;
    foot.href = addrUrl(CONTRACT_ADDRESS);
  }
}

function renderTicker() {
  if (!isConfigured) return;
  const totalPnl = state.traders.reduce((s, tr) => s + microToGen(tr.copy_pnl || '0'), 0);
  tweenNumber($('tick-pool'), 'pool', microToGen(state.pool ?? '0'), (v) => fmtNum(v, 2));
  tweenNumber($('tick-traders'), 'traders', state.traders.length, (v) => fmtInt(Math.round(v)));
  const el = $('tick-copypnl');
  tweenNumber(el, 'copypnl', totalPnl, (v) => (v > 0 ? '+' : '') + fmtNum(v, 2));
  el.classList.toggle('pos', totalPnl > 0);
  el.classList.toggle('neg', totalPnl < 0);
}

function badgeClass(v) {
  const s = String(v || '').toLowerCase().replaceAll(' ', '_');
  if (!s || s === 'none' || s === 'unverified') return 'badge-none';
  if (/(pass|verified|approved|listed)/.test(s)) return 'badge-verified';
  if (/(fail|rejected|flagged|disputed)/.test(s)) return 'badge-rejected';
  return 'badge-pending';
}

function renderWall() {
  const wall = $('wall');
  const order = state.traders.map((tr) => String(tr.address));
  const orderChanged = JSON.stringify(order) !== JSON.stringify(state.prevOrder) && state.prevOrder.length > 0;
  state.prevOrder = order;
  const doRender = () => {
    // Keep the skeleton until the first chain load attempt finishes.
    if (!state.traders.length && isConfigured && !state.loaded) return;
    wall.classList.remove('wall-skeleton');
    wall.innerHTML = '';
    $('wall-empty').hidden = state.traders.length > 0;
    if (!state.traders.length) return;
    for (const [i, tr] of state.traders.entries()) {
      const li = document.createElement('li');
      const pnl = microToGen(tr.copy_pnl || '0');
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `trader-card${String(tr.address) === state.selectedTrader ? ' sel' : ''}`;
      btn.style.viewTransitionName = `trader-${String(tr.address).slice(2, 10)}`;
      btn.setAttribute('aria-label', `${tr.name || shortAddr(tr.address)} — ${t('card.openRoom')}`);
      btn.innerHTML = `
        <span class="trader-top">
          <span class="avatar" aria-hidden="true">${escapeHtml(String(tr.name || '?').trim().charAt(0).toUpperCase() || '?')}</span>
          <span class="badge ${badgeClass(tr.badge)}">${escapeHtml(tr.badge || '—')}</span>
          <span class="trader-rank">#${i + 1}</span>
        </span>
        <span class="trader-name">${escapeHtml(tr.name || shortAddr(tr.address))}</span>
        <span class="trader-addr">${escapeHtml(shortAddr(tr.address))}</span>
        <span class="trader-pnl-label">${escapeHtml(t('card.copyPnl'))}</span>
        <span class="trader-pnl ${pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : ''}">${pnl > 0 ? '+' : ''}${fmtNum(pnl, 2)}<small> GEN</small></span>
        <span class="trader-meta">
          <span>${t('card.reputation')} <strong>${fmtInt(Number(tr.reputation || '0'))}</strong></span>
          <span><strong>${fmtInt(Number(tr.followers || '0'))}</strong> ${t('card.followers')}</span>
          <span>${t('card.stake')} <strong>${fmtGen(tr.stake || '0')} GEN</strong></span>
        </span>`;
      btn.addEventListener('click', () => {
        state.selectedTrader = String(tr.address);
        renderWall();
        renderRoom();
        document.getElementById('room').scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
      });
      li.appendChild(btn);
      wall.appendChild(li);
    }
  };
  // E8: a rank change travels instead of flashing.
  if (orderChanged && !reducedMotion && document.startViewTransition) {
    document.startViewTransition(doRender);
  } else {
    doRender();
  }
}

function latestRecordFor(address) {
  const mine = state.records.filter((r) => String(r.trader).toLowerCase() === String(address).toLowerCase());
  return mine.length ? mine[mine.length - 1] : null;
}

function renderRoom() {
  const body = $('room-body');
  const empty = $('room-empty');
  const tr = state.traders.find((x) => String(x.address) === state.selectedTrader);
  if (!tr) { body.hidden = true; empty.hidden = false; return; }
  body.hidden = false;
  empty.hidden = true;
  const rec = latestRecordFor(tr.address);
  $('room-avatar').textContent = String(tr.name || '?').trim().charAt(0).toUpperCase() || '?';
  $('room-name').textContent = tr.name || shortAddr(tr.address);
  const badge = $('room-badge');
  badge.textContent = tr.badge || '—';
  badge.className = `badge ${badgeClass(tr.badge)}`;
  $('room-address').textContent = tr.address;
  const verdictEl = $('room-verdict');
  const verdictText = rec ? String(rec.verdict || rec.status || '—') : '—';
  verdictEl.textContent = verdictText;
  const isPos = /pass|verified|approved/i.test(verdictText);
  const isNeg = /fail|rejected/i.test(verdictText);
  verdictEl.className = `verdict-word${isPos ? ' pos' : ''}${isNeg ? ' neg' : ''}`;
  // E3: when a verdict lands (changed since last render), the word gets heavier.
  if (rec && state.prevVerdict[String(rec.id)] && state.prevVerdict[String(rec.id)] !== verdictText) {
    verdictEl.classList.add('landed');
    setTimeout(() => verdictEl.classList.remove('landed'), 900);
  }
  if (rec) state.prevVerdict[String(rec.id)] = verdictText;
  $('room-verdict-text').textContent = verdictText;
  $('room-reason').textContent = rec ? (rec.verdict_reason || '—') : t('room.noRecord');
  $('room-appeals').textContent = rec ? String(rec.appeal_count ?? '0') : '—';
  $('room-evidence').textContent = rec ? (rec.evidence || '—') : t('room.noRecord');
  const hist = $('room-history');
  hist.innerHTML = '';
  const lines = rec && rec.history ? String(rec.history).split('\n').map((s) => s.trim()).filter(Boolean) : [];
  if (!lines.length) {
    const li = document.createElement('li');
    li.textContent = '—';
    hist.appendChild(li);
  } else {
    for (const line of lines) {
      const li = document.createElement('li');
      li.textContent = line;
      hist.appendChild(li);
    }
  }
  const hasRecord = Boolean(rec);
  $('audit-btn').disabled = !hasRecord;
  $('adjudicate-btn').disabled = !hasRecord;
  $('dispute-audit-btn').disabled = !hasRecord;
  for (const f of ['appeal-form', 'dispute-form', 'witness-form']) {
    $(f).querySelector('button[type="submit"]').disabled = !hasRecord;
  }
}

function renderCopies() {
  const body = $('copies-body');
  if (!isConfigured) return;
  let rows = state.copies;
  if (state.filterMine && state.signer) {
    rows = rows.filter((c) => String(c.follower).toLowerCase() === state.signer.address.toLowerCase());
  }
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="8" class="empty">${t('copies.empty')}</td></tr>`;
    return;
  }
  body.innerHTML = '';
  for (const c of rows) {
    const tr = document.createElement('tr');
    const pnl = microToGen(c.pnl || '0');
    const trader = state.traders.find((x) => String(x.address).toLowerCase() === String(c.trader).toLowerCase());
    tr.innerHTML = `<td>#${escapeHtml(String(c.id))}</td>
      <td>${escapeHtml(trader?.name || shortAddr(c.trader))}</td>
      <td>${escapeHtml(shortAddr(c.follower))}</td>
      <td>${fmtGen(c.principal || '0')} GEN</td>
      <td class="${pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : ''}">${signedGen(c.pnl || '0')} GEN</td>
      <td>${escapeHtml(String(c.status || '—'))}</td>
      <td>${fmtGen(c.trader_share || '0')} GEN</td>
      <td>${fmtGen(c.follower_return || '0')} GEN</td>`;
    body.appendChild(tr);
  }
}

function renderSelects() {
  const fill = (sel, items, emptyText, pickText) => {
    const el = $(sel);
    const prev = el.value;
    el.innerHTML = '';
    if (!items.length) {
      const o = document.createElement('option');
      o.value = '';
      o.textContent = emptyText;
      el.appendChild(o);
    } else {
      const ph = document.createElement('option');
      ph.value = '';
      ph.textContent = pickText;
      el.appendChild(ph);
      for (const it of items) {
        const o = document.createElement('option');
        o.value = it.value;
        o.textContent = it.label;
        el.appendChild(o);
      }
    }
    if ([...el.options].some((o) => o.value === prev)) el.value = prev;
  };
  fill('follow-trader', state.traders.map((tr) => ({ value: String(tr.address), label: `${tr.name || shortAddr(tr.address)} (${shortAddr(tr.address)})` })), t('form.noTraders'), t('form.pickTrader'));
  fill('copy-copy', state.copies.map((c) => ({ value: String(c.id), label: `#${c.id} — ${fmtGen(c.principal || '0')} GEN` })), t('form.noCopies'), t('form.pickCopy'));
  fill('settle-copy', state.copies.map((c) => ({ value: String(c.id), label: `#${c.id} — ${fmtGen(c.principal || '0')} GEN` })), t('form.noCopies'), t('form.pickCopy'));
}

function renderSignerLine() {
  const el = $('signer-line');
  if (!state.signer) { el.textContent = ''; return; }
  if (state.signer.kind === 'wallet') {
    el.textContent = `${t('wallet.connected')}: ${state.signer.address}`;
  } else {
    el.innerHTML = '';
    const span = document.createElement('span');
    span.textContent = `${t('wallet.testAccount')}: ${state.signer.address} — ${t('trade.testAccountNote')}`;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-ghost';
    btn.style.marginLeft = '0.6rem';
    btn.textContent = t('wallet.discardTest');
    btn.addEventListener('click', discardTestAccount);
    el.append(span, btn);
  }
}

// ---------- amount parsing (string math only, never floats) ----------
function parseGenToMicro(str) {
  const s = String(str ?? '').trim();
  const m = /^(-?)(\d+)(?:\.(\d{1,6}))?$/.exec(s);
  if (!m) return null;
  const frac = (m[3] || '').padEnd(6, '0');
  const v = BigInt(m[2]) * MICRO + BigInt(frac || '0');
  return m[1] === '-' ? -v : v;
}
function parseWhole(str) {
  const s = String(str ?? '').trim();
  if (!/^\d+$/.exec(s)) return null;
  return BigInt(s);
}

// ---------- evidence builder (structured fields -> one English text) ----------
function buildEvidence(fd) {
  const total = parseWhole(fd.get('total'));
  const wins = parseWhole(fd.get('wins'));
  const pnl = String(fd.get('pnl') || '').trim();
  const detail = String(fd.get('detail') || '').trim();
  const source = String(fd.get('source') || '').trim();
  if (total === null || wins === null || wins > total) return null;
  const rate = total > 0n ? Number((wins * 10000n) / total) / 100 : 0;
  const rateStr = total > 0n ? `${rate.toFixed(2)}%` : '0.00%';
  return {
    text: `Track record: ${total} trades, ${wins} wins (${rateStr} win rate), total PnL ${pnl} GEN. Representative trade: ${detail}. Source: ${source}.`,
    rateStr,
  };
}

function refreshEvidencePreview() {
  const form = $('record-form');
  const fd = new FormData(form);
  const total = parseWhole(fd.get('total'));
  const wins = parseWhole(fd.get('wins'));
  const rateEl = $('win-rate-line');
  if (total !== null && wins !== null && total > 0n && wins <= total) {
    const rate = Number((wins * 10000n) / total) / 100;
    rateEl.textContent = `${t('desk.recordWinRate')}: ${rate.toFixed(2)}%`;
  } else {
    rateEl.textContent = '';
  }
  const built = buildEvidence(fd);
  $('evidence-preview').textContent = built ? built.text : '—';
}

// ---------- wallet: any injected EVM wallet, multi-provider aware ----------
function discoverProviders() {
  const found = [];
  const push = (provider, name) => {
    if (!provider || found.some((f) => f.provider === provider)) return;
    found.push({ provider, name: name || provider?.info?.name || 'Wallet' });
  };
  if (typeof window === 'undefined') return found;
  const eth = window.ethereum;
  if (eth) {
    if (Array.isArray(eth.providers)) for (const p of eth.providers) push(p, p?.info?.name);
    else push(eth, eth?.info?.name);
  }
  // EIP-6963 announcements collected on window
  for (const p of window.__caProviders || []) push(p.provider, p.info?.name);
  return found;
}

// Collect EIP-6963 providers as they announce themselves.
window.__caProviders = [];
window.addEventListener('eip6963:announceProvider', (ev) => {
  const d = ev.detail;
  if (d && d.provider && !window.__caProviders.some((p) => p.provider === d.provider)) {
    window.__caProviders.push(d);
  }
});
try { window.dispatchEvent(new Event('eip6963:requestProvider')); } catch { /* older browsers */ }

function pickProvider(providers) {
  if (providers.length <= 1) return Promise.resolve(providers[0] || null);
  return new Promise((resolve) => {
    const picker = $('provider-picker');
    const list = $('provider-list');
    list.innerHTML = '';
    for (const p of providers) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn';
      b.textContent = p.name;
      b.addEventListener('click', () => { picker.hidden = true; resolve(p); });
      list.appendChild(b);
    }
    $('picker-cancel').onclick = () => { picker.hidden = true; resolve(null); };
    picker.hidden = false;
  });
}

async function connectWallet() {
  const providers = discoverProviders();
  if (!providers.length) {
    toast(t('wallet.noWallet'));
    offerTestAccount();
    return;
  }
  const chosen = await pickProvider(providers);
  if (!chosen) return;
  const provider = chosen.provider;
  try {
    const accounts = await provider.request({ method: 'eth_requestAccounts' });
    const address = accounts && accounts[0];
    if (!address) throw new Error('no account');
    state.signer = { kind: 'wallet', address, provider };
    $('wallet-btn').textContent = shortAddr(address);
    renderSignerLine();
    await ensureChain(provider);
    await refreshBalance();
    toast(t('wallet.connected'));
    provider.on?.('accountsChanged', (accs) => {
      if (!accs || !accs.length) {
        state.signer = null;
        $('wallet-btn').textContent = t('wallet.connect');
        renderSignerLine();
        refreshBalance();
      } else if (state.signer?.kind === 'wallet') {
        state.signer.address = accs[0];
        $('wallet-btn').textContent = shortAddr(accs[0]);
        renderSignerLine();
        refreshBalance();
      }
    });
    provider.on?.('chainChanged', () => { loadAll(); refreshBalance(); });
  } catch (e) {
    console.error('connectWallet', e);
    if (isUserRejection(e)) toast(t('wallet.userRejected'));
    else toast(t('wallet.connectFailed'));
  }
}

async function ensureChain(provider) {
  const chainId = await provider.request({ method: 'eth_chainId' });
  if (Number(chainId) === CHAIN_ID) return;
  try {
    await provider.request({
      method: 'wallet_switchEthereumChain',
      params: [{ chainId: CHAIN_ID_HEX }],
    });
  } catch (e) {
    if (e && (e.code === 4902 || String(e.message || '').includes('4902'))) {
      try {
        await provider.request({
          method: 'wallet_addEthereumChain',
          params: [{
            chainId: CHAIN_ID_HEX,
            chainName: 'GenLayer Stable Studionet',
            rpcUrls: [RPC_URL],
            blockExplorerUrls: [EXPLORER],
            nativeCurrency: { name: 'GEN', symbol: 'GEN', decimals: 18 },
          }],
        });
      } catch (addErr) {
        throw new Error('switch-failed');
      }
    } else if (isUserRejection(e)) {
      throw e;
    } else {
      throw new Error('switch-failed');
    }
  }
  const after = await provider.request({ method: 'eth_chainId' });
  if (Number(after) !== CHAIN_ID) throw new Error('switch-failed');
}

function offerTestAccount() {
  if (state.signer) return;
  if (!confirm(`${t('wallet.useTest')}?\n\n${t('trade.testAccountNote')}`)) return;
  createTestAccount();
}

function createTestAccount() {
  // Key lives only in memory (state), never in storage; discarded on tab close or button press.
  const account = createAccount();
  state.signer = { kind: 'test', address: account.address, account };
  $('wallet-btn').textContent = `${t('wallet.testAccount')}: ${shortAddr(account.address)}`;
  renderSignerLine();
  refreshBalance();
  toast(t('toast.testAccountCreated'));
}

function discardTestAccount() {
  if (state.signer && state.signer.kind === 'test') {
    state.signer = null;
    $('wallet-btn').textContent = t('wallet.connect');
    renderSignerLine();
    refreshBalance();
    toast(t('toast.testAccountDiscarded'));
  }
}

function isUserRejection(e) {
  const m = String((e && (e.message || e)) || '').toLowerCase();
  return e?.code === 4001 || m.includes('user denied') || m.includes('user rejected') || m.includes('rejected the request');
}

// ---------- writes: submit -> wait FINALIZED -> read back ----------
function setSteps(stage) {
  const ol = $('tx-steps');
  if (!stage) { ol.hidden = true; return; }
  ol.hidden = false;
  const order = ['submit', 'consensus', 'final'];
  const idx = order.indexOf(stage);
  ol.querySelectorAll('li').forEach((li) => {
    const i = order.indexOf(li.dataset.step);
    li.classList.toggle('on', i === idx);
    li.classList.toggle('done', i < idx);
  });
}

function friendlyError(e, fallbackKey = 'trade.generic') {
  const m = String((e && (e.message || e)) || '');
  if (isUserRejection(e)) return t('wallet.userRejected');
  if (/switch-failed/.test(m)) return t('wallet.switchFailed');
  if (/Insufficient GEN/i.test(m)) return t('trade.insufficient');
  if (/already claimed/i.test(m)) return t('trade.alreadyClaimed');
  if (/network|fetch|Failed to fetch|ECONN/i.test(m)) return t('trade.networkError');
  return t(fallbackKey);
}

function addFeedEntry({ method, hash, note, state: st }) {
  const entry = { method, hash, note, state: st, time: new Date() };
  state.feed.unshift(entry);
  renderFeed();
  return entry;
}

function renderFeed() {
  const ul = $('tx-feed');
  ul.innerHTML = '';
  if (!state.feed.length) {
    const li = document.createElement('li');
    li.className = 'empty';
    li.textContent = t('activity.empty');
    ul.appendChild(li);
    return;
  }
  for (const e of state.feed) {
    const li = document.createElement('li');
    const stateLabel = e.state === 'final' ? t('steps.final')
      : e.state === 'wait' ? t('steps.consensus')
      : e.state === 'error' ? t('trade.failed') : e.state;
    const stateClass = e.state === 'final' ? 'final' : e.state === 'wait' ? 'wait' : 'err';
    li.innerHTML = `<span class="tx-method">${escapeHtml(e.method)}</span>
      <span class="tx-state ${stateClass}">${escapeHtml(stateLabel)}</span>
      <span>${escapeHtml(e.note || '')}</span>
      ${e.hash ? `<a class="tx-hash" href="${txUrl(e.hash)}" target="_blank" rel="noopener">${e.hash.slice(0, 10)}…${e.hash.slice(-6)} ↗</a>` : ''}
      <span class="tx-time">${e.time.toLocaleTimeString(lang === 'zh' ? 'zh-CN' : 'en-US')}</span>`;
    ul.appendChild(li);
  }
}

async function runWrite({ method, args, successNote, readBack }) {
  if (!isConfigured) throw new Error(t('hero.notDeployed'));
  if (!state.signer) {
    throw new Error(t('trade.needSigner'));
  }
  const signer = state.signer;
  if (signer.kind === 'wallet') {
    try { await ensureChain(signer.provider); }
    catch (e) {
      throw new Error(isUserRejection(e) ? t('wallet.userRejected') : t('wallet.switchFailed'));
    }
  }
  const account = signer.kind === 'wallet' ? signer.address : signer.account;
  const writeClient = createClient({
    chain: studionet,
    account,
    ...(signer.kind === 'wallet' ? { provider: signer.provider } : {}),
  });
  setSteps('submit');
  $('tx-status').textContent = t('trade.submitted');
  let hash;
  try {
    hash = await writeClient.writeContract({
      account,
      address: CONTRACT_ADDRESS,
      functionName: method,
      args,
      value: 0n,
    });
  } catch (e) {
    setSteps(null);
    $('tx-status').textContent = '';
    throw new Error(friendlyError(e));
  }
  const entry = addFeedEntry({ method, hash, note: '', state: 'wait' });
  $('tx-status').innerHTML = `${t('trade.waiting')} <a href="${txUrl(hash)}" target="_blank" rel="noopener">${hash.slice(0, 10)}…${hash.slice(-6)} ↗</a>`;
  setSteps('consensus');
  try {
    const receipt = await readClient.waitForTransactionReceipt({
      hash,
      status: TransactionStatus.FINALIZED,
      interval: 10000,
      retries: 150,
    });
    const exec = receipt?.txExecutionResult ?? receipt?.execution_result ?? receipt?.executionResult;
    const failedExec = typeof exec === 'string' && !/success/i.test(exec);
    setSteps('final');
    entry.state = failedExec ? 'error' : 'final';
    let note = successNote || '';
    try {
      if (readBack) note = await readBack();
    } catch { /* read-back failure surfaces via the refresh below */ }
    entry.note = note;
    renderFeed();
    await loadAll();
    $('tx-status').textContent = failedExec
      ? t('trade.failed')
      : `${t('trade.finalized')} ${note ? t('trade.readback', { text: note }) : ''}`;
    if (failedExec) throw new Error(t('trade.failed'));
    return { hash, receipt };
  } catch (e) {
    if (String(e.message || '').includes(t('trade.failed'))) throw e;
    entry.state = 'wait';
    renderFeed();
    setSteps('consensus');
    $('tx-status').textContent = t('trade.timeout');
    throw new Error(t('trade.timeout'));
  }
}

// ---------- form helpers ----------
function showFormError(form, msg) {
  const el = form.querySelector('.form-error');
  if (!el) return;
  el.hidden = false;
  el.textContent = msg;
}
function clearFormError(form) {
  const el = form.querySelector('.form-error');
  if (el) el.hidden = true;
}
function needSignerOrOffer() {
  if (!state.signer) {
    offerTestAccount();
    return false;
  }
  return true;
}

// Contract not deployed yet: fail fast with a human message, no chain call.
function guardConfigured(form) {
  if (isConfigured) return true;
  const msg = t('hero.notDeployed');
  if (form) showFormError(form, msg);
  else if (form === null) $('tx-status').textContent = msg;
  else roomError(msg);
  return false;
}

async function onClaim() {
  const btn = $('claim-btn');
  btn.disabled = true;
  if (!guardConfigured(null)) { btn.disabled = false; return; }
  try {
    if (!needSignerOrOffer()) return;
    await runWrite({
      method: 'claim_test_gen',
      args: [],
      successNote: t('claim.success'),
      readBack: async () => {
        const bal = await readView('get_balance', [state.signer.address]);
        return t('activity.claimed', { gen: fmtGen(BigInt(String(bal)), 6) });
      },
    });
    toast(t('claim.success'));
  } catch (err) {
    $('tx-status').textContent = err.message || t('trade.generic');
  } finally {
    btn.disabled = false;
  }
}

async function onRegister(e) {
  e.preventDefault();
  const form = e.target;
  clearFormError(form);
  if (!guardConfigured(form)) return;
  const fd = new FormData(form);
  const name = String(fd.get('name') || '').trim();
  const stake = parseGenToMicro(fd.get('stake'));
  if (!name || !stake || stake <= 0n) {
    showFormError(form, !name ? t('form.empty') : t('trade.amountInvalid'));
    return;
  }
  if (state.balance !== null && state.balance < stake) {
    showFormError(form, t('trade.claimFirst'));
    return;
  }
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    if (!needSignerOrOffer()) return;
    await runWrite({
      method: 'register_trader',
      args: [name, stake.toString()],
      successNote: '',
      readBack: async () => {
        const tr = asObject(await readView('get_trader', [state.signer.address]));
        return t('activity.registered', { name: tr.name || name, stake: fmtGen(tr.stake || stake) });
      },
    });
    form.reset();
    toast(t('trade.finalized'));
  } catch (err) {
    showFormError(form, err.message || t('trade.generic'));
  } finally {
    btn.disabled = false;
  }
}

async function onRecord(e) {
  e.preventDefault();
  const form = e.target;
  clearFormError(form);
  if (!guardConfigured(form)) return;
  const fd = new FormData(form);
  const built = buildEvidence(fd);
  const pnl = parseGenToMicro(fd.get('pnl'));
  const detail = String(fd.get('detail') || '').trim();
  const source = String(fd.get('source') || '').trim();
  if (!built || pnl === null || !detail || !source) {
    showFormError(form, !built ? t('form.badNumber') : pnl === null ? t('form.badPnl') : t('form.empty'));
    return;
  }
  if (built.text.length > 2000) { showFormError(form, t('form.evidenceLong')); return; }
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    if (!needSignerOrOffer()) return;
    const before = Number(await readView('get_next_record_id', []));
    await runWrite({
      method: 'submit_track_record',
      args: [built.text],
      successNote: '',
      readBack: async () => {
        const after = Number(await readView('get_next_record_id', []));
        const id = after > before ? after - 1 : before;
        return t('activity.recordSubmitted', { id });
      },
    });
    form.reset();
    refreshEvidencePreview();
    toast(t('trade.finalized'));
  } catch (err) {
    showFormError(form, err.message || t('trade.generic'));
  } finally {
    btn.disabled = false;
  }
}

async function onFollow(e) {
  e.preventDefault();
  const form = e.target;
  clearFormError(form);
  if (!guardConfigured(form)) return;
  const fd = new FormData(form);
  const trader = String(fd.get('trader') || '').trim();
  const principal = parseGenToMicro(fd.get('principal'));
  if (!trader || !principal || principal <= 0n) {
    showFormError(form, !trader ? t('form.empty') : t('trade.amountInvalid'));
    return;
  }
  if (state.balance !== null && state.balance < principal) {
    showFormError(form, t('trade.claimFirst'));
    return;
  }
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    if (!needSignerOrOffer()) return;
    const before = Number(await readView('get_next_copy_id', []));
    const tr = state.traders.find((x) => String(x.address) === trader);
    await runWrite({
      method: 'follow_trader',
      args: [trader, principal.toString()],
      successNote: '',
      readBack: async () => {
        const after = Number(await readView('get_next_copy_id', []));
        const id = after > before ? after - 1 : before;
        return t('activity.followed', { trader: tr?.name || shortAddr(trader), principal: fmtGen(principal), id });
      },
    });
    form.reset();
    toast(t('trade.finalized'));
  } catch (err) {
    showFormError(form, err.message || t('trade.generic'));
  } finally {
    btn.disabled = false;
  }
}

async function onCopy(e) {
  e.preventDefault();
  const form = e.target;
  clearFormError(form);
  if (!guardConfigured(form)) return;
  const fd = new FormData(form);
  const copyId = String(fd.get('copy') || '').trim();
  const amount = parseGenToMicro(fd.get('amount'));
  if (!copyId || !amount || amount <= 0n) {
    showFormError(form, !copyId ? t('form.empty') : t('trade.amountInvalid'));
    return;
  }
  if (state.balance !== null && state.balance < amount) {
    showFormError(form, t('trade.claimFirst'));
    return;
  }
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    if (!needSignerOrOffer()) return;
    await runWrite({
      method: 'copy_position',
      args: [copyId, amount.toString()],
      successNote: '',
      readBack: async () => {
        const c = asObject(await readView('get_copy', [copyId]));
        return t('activity.copied', { id: copyId, amount: fmtGen(amount) }) +
          (c.principal ? ` · ${t('copies.principal')}: ${fmtGen(c.principal)} GEN` : '');
      },
    });
    form.reset();
    toast(t('trade.finalized'));
  } catch (err) {
    showFormError(form, err.message || t('trade.generic'));
  } finally {
    btn.disabled = false;
  }
}

async function onSettle(e) {
  e.preventDefault();
  const form = e.target;
  clearFormError(form);
  if (!guardConfigured(form)) return;
  const fd = new FormData(form);
  const copyId = String(fd.get('copy') || '').trim();
  const pnl = parseGenToMicro(fd.get('pnl'));
  if (!copyId || pnl === null) {
    showFormError(form, !copyId ? t('form.empty') : t('form.badPnl'));
    return;
  }
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    if (!needSignerOrOffer()) return;
    await runWrite({
      method: 'settle_copy',
      args: [copyId, pnl.toString()],
      successNote: '',
      readBack: async () => {
        const c = asObject(await readView('get_copy', [copyId]));
        return t('activity.settled', {
          id: copyId,
          pnl: fmtNum(microToGen(c.pnl ?? pnl), 2),
          share: fmtGen(c.trader_share || '0'),
          ret: fmtGen(c.follower_return || '0'),
        });
      },
    });
    form.reset();
    toast(t('trade.finalized'));
  } catch (err) {
    showFormError(form, err.message || t('trade.generic'));
  } finally {
    btn.disabled = false;
  }
}

// ---------- record-room actions ----------
function currentRecord() {
  if (!state.selectedTrader) return null;
  return latestRecordFor(state.selectedTrader);
}

function roomError(msg) {
  const el = $('room-error');
  el.hidden = false;
  el.textContent = msg;
}

async function onAudit() {
  const rec = currentRecord();
  if (!rec) return;
  $('room-error').hidden = true;
  if (!guardConfigured()) return;
  const btn = $('audit-btn');
  btn.disabled = true;
  try {
    if (!needSignerOrOffer()) return;
    await runWrite({
      method: 'audit_record',
      args: [String(rec.id)],
      successNote: '',
      readBack: async () => {
        const after = asObject(await readView('get_record', [String(rec.id)]));
        return t('activity.audited', { id: rec.id, verdict: String(after.verdict || after.status || '—') });
      },
    });
    toast(t('trade.finalized'));
  } catch (err) {
    roomError(err.message || t('trade.generic'));
  } finally {
    btn.disabled = false;
  }
}

async function onAdjudicate() {
  const rec = currentRecord();
  if (!rec) return;
  $('room-error').hidden = true;
  if (!guardConfigured()) return;
  const btn = $('adjudicate-btn');
  btn.disabled = true;
  try {
    if (!needSignerOrOffer()) return;
    await runWrite({
      method: 'adjudicate_appeal',
      args: [String(rec.id)],
      successNote: '',
      readBack: async () => {
        const after = asObject(await readView('get_record', [String(rec.id)]));
        return t('activity.adjudicated', { id: rec.id, verdict: String(after.verdict || after.status || '—') });
      },
    });
    toast(t('trade.finalized'));
  } catch (err) {
    roomError(err.message || t('trade.generic'));
  } finally {
    btn.disabled = false;
  }
}

async function onDisputeAudit() {
  const rec = currentRecord();
  if (!rec) return;
  $('room-error').hidden = true;
  if (!guardConfigured()) return;
  const btn = $('dispute-audit-btn');
  btn.disabled = true;
  try {
    if (!needSignerOrOffer()) return;
    await runWrite({
      method: 'audit_dispute',
      args: [String(rec.id)],
      successNote: '',
      readBack: async () => {
        const after = asObject(await readView('get_record', [String(rec.id)]));
        return t('activity.disputeAudited', { id: rec.id, verdict: String(after.verdict || after.status || '—') });
      },
    });
    toast(t('trade.finalized'));
  } catch (err) {
    roomError(err.message || t('trade.generic'));
  } finally {
    btn.disabled = false;
  }
}

async function onAppeal(e) {
  e.preventDefault();
  const form = e.target;
  clearFormError(form);
  if (!guardConfigured(form)) return;
  const rec = currentRecord();
  if (!rec) return;
  const fd = new FormData(form);
  const evidence = String(fd.get('evidence') || '').trim();
  if (!evidence) { showFormError(form, t('form.empty')); return; }
  if (evidence.length > 2000) { showFormError(form, t('form.evidenceLong')); return; }
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    if (!needSignerOrOffer()) return;
    await runWrite({
      method: 'appeal',
      args: [String(rec.id), evidence],
      successNote: '',
      readBack: async () => t('activity.appealed', { id: rec.id }),
    });
    form.reset();
    toast(t('trade.finalized'));
  } catch (err) {
    showFormError(form, err.message || t('trade.generic'));
  } finally {
    btn.disabled = false;
  }
}

async function onDispute(e) {
  e.preventDefault();
  const form = e.target;
  clearFormError(form);
  if (!guardConfigured(form)) return;
  const rec = currentRecord();
  if (!rec) return;
  const fd = new FormData(form);
  const reason = String(fd.get('reason') || '').trim();
  if (!reason) { showFormError(form, t('form.empty')); return; }
  if (reason.length > 500) { showFormError(form, t('form.noteLong')); return; }
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    if (!needSignerOrOffer()) return;
    await runWrite({
      method: 'dispute_fake',
      args: [String(rec.id), reason],
      successNote: '',
      readBack: async () => t('activity.disputed', { id: rec.id }),
    });
    form.reset();
    toast(t('trade.finalized'));
  } catch (err) {
    showFormError(form, err.message || t('trade.generic'));
  } finally {
    btn.disabled = false;
  }
}

async function onWitness(e) {
  e.preventDefault();
  const form = e.target;
  clearFormError(form);
  if (!guardConfigured(form)) return;
  const rec = currentRecord();
  if (!rec) return;
  const fd = new FormData(form);
  const note = String(fd.get('note') || '').trim();
  if (!note) { showFormError(form, t('form.empty')); return; }
  if (note.length > 500) { showFormError(form, t('form.noteLong')); return; }
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    if (!needSignerOrOffer()) return;
    await runWrite({
      method: 'submit_witness',
      args: [String(rec.id), note],
      successNote: '',
      readBack: async () => t('activity.witnessed', { id: rec.id }),
    });
    form.reset();
    toast(t('trade.finalized'));
  } catch (err) {
    showFormError(form, err.message || t('trade.generic'));
  } finally {
    btn.disabled = false;
  }
}

// ---------- init ----------
function bindAll() {
  $('lang-en').addEventListener('click', () => applyLang('en'));
  $('lang-zh').addEventListener('click', () => applyLang('zh'));
  $('wallet-btn').addEventListener('click', async () => {
    if (state.signer) {
      if (state.signer.kind === 'test') discardTestAccount();
      else {
        state.signer = null;
        $('wallet-btn').textContent = t('wallet.connect');
        renderSignerLine();
        refreshBalance();
      }
      return;
    }
    await connectWallet();
  });
  $('claim-btn').addEventListener('click', onClaim);
  $('refresh-btn').addEventListener('click', loadAll);
  $('register-form').addEventListener('submit', onRegister);
  $('record-form').addEventListener('submit', onRecord);
  $('record-form').addEventListener('input', refreshEvidencePreview);
  $('follow-form').addEventListener('submit', onFollow);
  $('copy-form').addEventListener('submit', onCopy);
  $('settle-form').addEventListener('submit', onSettle);
  $('audit-btn').addEventListener('click', onAudit);
  $('adjudicate-btn').addEventListener('click', onAdjudicate);
  $('dispute-audit-btn').addEventListener('click', onDisputeAudit);
  $('appeal-form').addEventListener('submit', onAppeal);
  $('dispute-form').addEventListener('submit', onDispute);
  $('witness-form').addEventListener('submit', onWitness);
  $('filter-all').addEventListener('click', () => {
    state.filterMine = false;
    $('filter-all').setAttribute('aria-pressed', 'true');
    $('filter-mine').setAttribute('aria-pressed', 'false');
    renderCopies();
  });
  $('filter-mine').addEventListener('click', () => {
    state.filterMine = true;
    $('filter-mine').setAttribute('aria-pressed', 'true');
    $('filter-all').setAttribute('aria-pressed', 'false');
    renderCopies();
  });
  setInterval(() => { if (!document.hidden) loadAll(); }, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) loadAll(); });
}

applyLang(lang);
bindAll();
refreshEvidencePreview();
renderFeed();
loadAll();
refreshBalance();
