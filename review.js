/* Portfolio review. No third-party browser dependencies or network calls beyond the review service. */
const finite = (value) => typeof value === 'number' && Number.isFinite(value);
const number = (value) => String(value ?? '').trim() === '' ? NaN : Number(value);
const symbol = (value) => String(value ?? '').trim().toUpperCase();
const validSymbol = (value) => /^[A-Z0-9][A-Z0-9.-]{0,15}$/.test(value);
const rootSymbol = (value) => symbol(value).replace(/\.(US|NASDAQ|NYSE|NMS|NYS|UW|OQ)$/i, '');

/** Convert labelled percent values to the API's fractional contract without normalising mistakes. */
export function parseReviewInput({rows, amount, limit, capacity, order, cryptoLimit, valuesScreen}) {
  const holdings = new Map();
  for (const row of rows) {
    const ticker = symbol(row.ticker), weight = number(row.weight);
    if (!ticker && !String(row.weight ?? '').trim()) continue;
    if (!validSymbol(ticker)) throw new Error('Enter a valid ticker for every holding.');
    if (holdings.has(ticker)) throw new Error(`Add ${ticker} only once.`);
    if (!finite(weight) || weight <= 0 || weight > 100) throw new Error('Each holding needs a weight greater than 0% and at most 100%.');
    holdings.set(ticker, weight / 100);
  }
  if (Math.abs([...holdings.values()].reduce((a, b) => a + b, 0) - 1) > 0.000001) {
    throw new Error('Holdings must add up to 100%.');
  }
  const value = number(amount), drawdown = number(limit), hasCapacity = String(capacity ?? '').trim() !== '', maxLoss = number(capacity);
  const hasLimit = String(limit ?? '').trim() !== '';
  if (!finite(value) || value <= 0 || value > 1e12) throw new Error('Portfolio value must be greater than $0 and no more than $1 trillion.');
  if (hasLimit && (!finite(drawdown) || drawdown <= 0 || drawdown >= 100)) throw new Error('Drawdown limit must be greater than 0% and less than 100%, or left blank.');
  if (hasCapacity && (!finite(maxLoss) || maxLoss <= 0)) throw new Error('Enter a positive loss capacity or leave it blank.');
  if (hasCapacity && maxLoss >= value) throw new Error('Loss capacity must be below the portfolio value.');
  let change = null;
  if (order) {
    const ticker = symbol(order.ticker), weight = number(order.weight) / 100, from = symbol(order.from_ticker) || null;
    if (!validSymbol(ticker)) throw new Error('Enter a valid ticker to simulate.');
    const increase = weight - (holdings.get(ticker) || 0);
    if (!finite(weight) || increase <= 1e-10 || weight > 1) throw new Error('Set a target above the current weight and at most 100%.');
    if (from && (from === ticker || !holdings.has(from) || increase - holdings.get(from) > 1e-8)) {
      throw new Error('Choose a funding holding with enough weight to cover the increase.');
    }
    change = {ticker, weight, from_ticker: from};
  }
  const result = {portfolio:Object.fromEntries(holdings), amount:value, drawdown_limit:hasLimit ? drawdown / 100 : null, capacity:hasCapacity ? maxLoss : null, order:change};
  if (String(cryptoLimit ?? '').trim() !== '') {
    const cap = number(cryptoLimit);
    if (!finite(cap) || cap < 0 || cap > 100) throw new Error('Crypto limit must be between 0% and 100%, or left blank.');
    result.crypto_limit = cap / 100;
  }
  if (valuesScreen) result.values_screen = true;
  return result;
}

/** Historical decline at each observation, measured against its own running maximum. */
export function drawdownSeries(points = []) {
  let peak = -Infinity;
  return points.filter((p) => Array.isArray(p) && finite(p[1]) && p[1] > 0 && Number.isFinite(Date.parse(p[0]))).map(([date, value]) => {
    peak = Math.max(peak, value);
    return [date, value / peak - 1];
  });
}

export function companyExposure(entries, ticker) {
  const key = rootSymbol(ticker);
  return key ? (entries || []).find((row) => rootSymbol(row.ticker) === key) ?? null : null;
}

const securityGroups = {
  equity:'Stocks', etf_equity:'Equity ETFs', etf_bond:'Bond ETFs', etf_commodity:'Commodity ETFs', crypto:'Crypto assets',
};

export function matchSecurities(assets, query) {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return assets.filter((asset) => {
    const words = `${asset.ticker} ${asset.name} ${securityGroups[asset.asset_class] || ''}`.toLowerCase();
    return terms.every((term) => words.includes(term));
  });
}

/** Company totals are explicitly partial when a constituent list is missing or truncated. */
export function reviewCompanyExposure(result, side, ticker) {
  const mix = result[side];
  const ranked = companyExposure(result.exposure?.[side], ticker);
  const held = companyExposure(mix?.holdings, ticker);
  const direct = ranked?.direct_share ?? held?.weight ?? 0;
  const parts = new Map((ranked?.funds || []).map((fund) => [fund.ticker, fund.share]));
  const key = side === 'before' ? 'before_weight' : 'after_weight';
  const relevant = (result.funds || []).filter((fund) =>
    fund[key] > 0 && (!fund.asset_class || fund.asset_class === 'etf_equity'));
  for (const fund of relevant) {
    const disclosed = companyExposure(fund.companies, ticker);
    if (disclosed && !parts.has(fund.ticker)) parts.set(fund.ticker, fund[key] * disclosed.share);
  }
  const complete = Boolean(mix && relevant.every((fund) => {
    const count = fund.companies?.length || 0;
    return fund.company_coverage >= .999 && count > 0 && count >= (fund.companies_listed ?? count);
  }));
  const known = direct + [...parts.values()].reduce((total, share) => total + share, 0);
  const mapped = finite(ranked?.share) ? Math.max(known, ranked.share) : known > 0 || complete ? known : null;
  return {direct, funds:[...parts].map(([ticker,share]) => ({ticker,share})), mapped, complete};
}

/** Align reported rows by category or issuer, without filling missing observations with zero. */
export function compareAllocation(result, lens) {
  const rows = new Map();
  const add = (side, entries) => {
    for (const entry of entries || []) {
      const name = entry.name || entry.ticker;
      if (!name || !finite(entry.share)) continue;
      const key = lens === 'companies' && entry.ticker ? rootSymbol(entry.ticker) : name.trim().toLowerCase();
      const row = rows.get(key) || {name, ticker: entry.ticker, before:null, after:null};
      row[side] = entry;
      rows.set(key, row);
    }
  };
  for (const side of ['before','after']) {
    add(side, lens === 'companies' ? result.exposure?.[side] : result.allocation?.[side]?.industries);
  }
  return [...rows.values()].sort((left, right) => {
    const share = (row) => row.after?.share ?? row.before?.share ?? 0;
    return share(right) - share(left) || left.name.localeCompare(right.name);
  });
}

const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (s) => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[s]));
const icon = (name, cls = '') => `<svg aria-hidden="true" class="icon${cls ? ' ' + cls : ''}"><use href="#icon-${name}"/></svg>`;
const dollars = new Intl.NumberFormat('en-CA', {style:'currency', currency:'CAD', maximumFractionDigits:0});
const dateFormat = new Intl.DateTimeFormat('en-CA', {year:'numeric', month:'short', day:'numeric', timeZone:'UTC'});
const monthFormat = new Intl.DateTimeFormat('en-CA', {year:'2-digit', month:'short', timeZone:'UTC'});
const allMonths = new Intl.DateTimeFormat('en-CA', {year:'numeric', month:'short', timeZone:'UTC'});
const money = (value) => finite(value) ? dollars.format(value) : '—';
const pct = (value, precision = 1) => finite(value) ? `${(value * 100).toFixed(precision).replace(/\.0+$/, '').replace(/(\.\d*[1-9])0+$/, '$1').replace('-', '−')}%` : '—';
const pp = (fraction) => finite(fraction) ? `${(Math.abs(fraction) * 100).toFixed(1)} pp` : '—';
const date = (value) => Number.isFinite(Date.parse(value)) ? dateFormat.format(new Date(value)) : 'Not dated';
const reviewWindow = (start, end) => Number.isFinite(Date.parse(start)) && Number.isFinite(Date.parse(end)) ? `${allMonths.format(new Date(start))} – ${allMonths.format(new Date(end))}` : 'Historical window';
const whole = (value) => `${Math.max(0, Math.min(100, value * 100)).toFixed(2)}%`;
const percentInput = (value) => finite(value) ? String(Number((100 * value).toFixed(6))) : '';
const labelSymbol = (value) => symbol(value).replace(/\.(TO|US|V|NASDAQ|NYSE)$/i, '');
const percentBar = (value) => `<span class="meter" aria-hidden="true"><span style="--w:${whole(finite(value) ? Math.abs(value) : 0)}"></span></span>`;
const safeUrl = (value) => {
  if (typeof value !== 'string') return null;
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; }
  catch { return null; }
};
const sourceHTML = (source, fallback = '') => {
  const raw = typeof source === 'object' && source ? source.url || source.href || '' : source;
  const label = typeof source === 'object' && source ? source.label || source.name || '' : '';
  const url = safeUrl(raw);
  return url ? `<a class="text-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label || fallback || 'Open source')} ${icon('arrow-up-right')}</a>` : esc(label || raw || fallback);
};
// All dynamic strings are escaped at the boundary. Parse into a detached fragment,
// then allow only the elements and attributes used by the review before insertion.
function renderMarkup(target, markup) {
  const range = document.createRange();
  range.selectNodeContents(target);
  const fragment = range.createContextualFragment(markup);
  const tags = /^(a|button|div|p|strong|span|i|small|ul|li|details|summary|label|select|option|dl|dt|dd|input|table|thead|tbody|tr|th|td|h3|svg|use|defs|lineargradient|stop|path|text|line|circle)$/i;
  const standard = /^(class|id|role|hidden|tabindex|title|type|value|name|href|target|rel|for|selected|disabled|open|scope|min|max|step|inputmode|autocomplete|maxlength|placeholder|list|viewbox|x1|x2|y1|y2|x|y|text-anchor|stop-color|offset|stop-opacity|fill|d|r)$/i;
  for (const node of fragment.querySelectorAll('*')) {
    if (!tags.test(node.localName)) { node.remove(); continue; }
    for (const {name,value} of Array.from(node.attributes)) {
      const style = name === 'style' && /^(--w:[0-9.]+%|--symbol-ink:#[0-9a-f]{6};--symbol-tint:#[0-9a-f]{6})$/i.test(value);
      const idRef = value.startsWith('#');
      if (name === 'href' && !(idRef || (node.localName === 'a' && safeUrl(value)))) node.removeAttribute(name);
      else if (!style && !standard.test(name) && !/^(aria|data)-[a-z0-9-]+$/i.test(name)) node.removeAttribute(name);
    }
  }
  target.replaceChildren(fragment);
}
const empty = (title, description) => `<div class="empty-state"><strong>${esc(title)}</strong>${esc(description)}</div>`;
const measure = (mix) => Boolean(mix && mix.risk_measurable !== false && finite(mix.max_drawdown));
const warrant = (value) => value === true ? 'breached' : value === false ? 'within' : 'unverified';
const colors = [['#f0a8d3','#3b263d'],['#9cdfc8','#243a36'],['#abbdf3','#28324b'],['#efc78c','#3b302c'],['#d8b1fc','#3a2d50'],['#96d9ed','#263949']];
const colorsFor = (ticker) => colors[Array.from(String(ticker)).reduce((a, v) => a + v.charCodeAt(0), 0) % colors.length];

function init() {
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));
  const state = {examples:[], assets:[], example:null, input:null, result:null, live:false, order:false, lens:'money', holdingsState:'before', allocationView:'industries', allocationExpanded:false, fundView:'industries', fundTicker:null, feedToken:0, explanationToken:0, busy:false, allFunds:false};
  let resize = null;
  const picker = $('#example-picker'), dialog = $('#portfolio-editor'), setupDescription = $('#example-description');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const rootURL = new URL('.', window.location.href);
  const endpoint = (path) => new URL(path, rootURL);

  async function request(path, body, timeout = 16000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(endpoint(path), {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body), signal:controller.signal,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        const detail = typeof error?.detail === 'string' ? error.detail : typeof error?.error === 'string' ? error.error : typeof error?.message === 'string' ? error.message : '';
        const failure = new Error(detail || `Review service returned ${response.status}.`);
        failure.status = response.status;
        throw failure;
      }
      return await response.json();
    } finally { clearTimeout(timer); }
  }

  const announce = (message) => { $('#review-announcer').textContent = message; };
  const jump = (id, focus = false) => {
    const anchor = document.getElementById(id);
    if (!anchor) return;
    anchor.scrollIntoView({behavior:reducedMotion.matches ? 'instant' : 'smooth', block:'start'});
    if (focus) {
      const head = $('h2', anchor) || anchor;
      head.setAttribute('tabindex', '-1');
      head.focus({preventScroll:true});
    }
    history.replaceState(null, '', `#${id}`);
    setNav(id);
  };
  function setNav(id) {
    if (id === 'portfolio-allocation') id = 'look-through';
    $$('.primary-nav a').forEach((link) => {
      if (link.hash === `#${id}`) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
  }
  const after = () => state.order ? state.result?.after : null;
  const activeOrder = () => state.result?.order || state.input?.order;
  const canUseOrder = () => Boolean(state.result?.after && activeOrder());
  const analysisTicker = () => symbol(activeOrder()?.ticker || 'NVDA');
  const companyTicker = () => state.assets.some((asset) => asset.ticker === analysisTicker() && asset.asset_class === 'equity') ? analysisTicker() : 'NVDA';
  const companyName = (ticker) => state.assets.find((asset) => asset.ticker === ticker)?.name || labelSymbol(ticker);
  const mappedLabel = (data) => finite(data.mapped) ? `${pct(data.mapped,2)}${data.complete ? '' : ' identified'}` : 'Unknown';

  function renderMode() {
    const mode = !state.result ? 'loading' : state.result.mode === 'saved' || !state.live ? 'saved' : 'live';
    $('#mode-chip').dataset.mode = mode;
    $('#mode-text').textContent = {loading:'Loading review', saved:'Saved example', live:'Live calculations'}[mode];
    $('#mode-chip').title = mode === 'live' ? 'Calculations are running on the live review service using historical data.' : mode === 'saved' ? 'This result is a precomputed historical review.' : '';
    $('#open-editor').hidden = !state.live;
    $('#saved-hint').hidden = !state.result || state.live;
    const own = $('option[value="__own"]', picker);
    if (own) {
      own.disabled = !state.live;
      own.textContent = state.live ? 'Your portfolio' : 'Your portfolio / live only';
    }
  }

  function exampleName(example) {
    const id = String(example?.id || '');
    return /canad/i.test(id) ? 'Too Canadian?' : String(example?.name || id);
  }
  function renderSetup() {
    renderMode();
    if (!state.input || !state.result) return;
    const limits = state.result.limits || {};
    const cap = limits.capacity ?? state.input.capacity;
    const display = [money(state.result.amount ?? state.input.amount), finite(limits.drawdown ?? limits.drawdown_limit ?? state.input.drawdown_limit) ? pct(limits.drawdown ?? limits.drawdown_limit ?? state.input.drawdown_limit) : 'Not set', finite(cap) ? money(cap) : 'Not set'];
    $$('#setup-summary dd').forEach((element, i) => { element.textContent = display[i]; });
    setupDescription.textContent = state.example?.description || (state.example ? '' : 'Your holdings and risk limits.');
    $('#setup-note-text').textContent = state.example
      ? (state.example.limits_note || 'Illustrative limits for this example. The dollar budget sets a separate balance floor.')
      : 'Loss capacity sets a floor below the portfolio’s starting value.';
  }

  function renderScenario() {
    const button = $('#try-order');
    const ticker = analysisTicker(), hasSaved = canUseOrder();
    const name = ticker === 'NVDA' ? 'NVIDIA' : labelSymbol(ticker);
    const order = activeOrder();
    $('#scenario-title').textContent = hasSaved ? `What if you add ${name}?` : 'Try it before you trade.';
    $('#scenario-description').textContent = hasSaved && finite(order?.weight)
      ? `Preview a ${pct(order.weight)} target weight${order.from_ticker ? ` funded from ${labelSymbol(order.from_ticker)}` : ''}.`
      : 'Replay a simulated trade against your historical losses and your limits.';
    button.disabled = state.busy || (!hasSaved && !state.live);
    renderMarkup(button, `${esc(hasSaved ? (state.order ? 'View order preview' : `Try ${name} order`) : (state.live ? 'Simulate an order' : state.result ? 'No saved order for this example' : 'Loading order preview'))} ${icon('arrow')}`);
    $('#risk-actions').hidden = !after();
  }

  function renderHoldings() {
    const reviewingAfter = state.holdingsState === 'after' && Boolean(after());
    const mix = reviewingAfter ? after() : state.result?.before;
    if (!mix) return;
    $('#holding-states').hidden = !after();
    $$('[data-holdings-state]').forEach((item) => item.setAttribute('aria-pressed',String(item.dataset.holdingsState === (reviewingAfter ? 'after' : 'before'))));
    const risk = state.lens === 'risk';
    const rows = (Array.isArray(mix.holdings) ? mix.holdings : []).slice().sort((a,b) => ((risk ? b.risk_share : b.weight) ?? -Infinity) - ((risk ? a.risk_share : a.weight) ?? -Infinity));
    const available = rows.some((row) => finite(row.risk_share));
    $$('#portfolio [data-lens]').forEach((item) => item.setAttribute('aria-pressed', String(item.dataset.lens === state.lens)));
    if (!rows.length) {
      renderMarkup($('#holdings'), empty('Holdings unavailable', 'Choose another example or open a custom portfolio.'));
      return;
    }
    const option = risk ? 'Risk contribution' : 'Portfolio weight';
    renderMarkup($('#holdings'), `<div class="holdings-head"><p>${reviewingAfter ? 'Holdings after order' : 'Current holdings'}</p><p>${option}</p></div><ul class="holding-list">${rows.map((row) => {
      const [ink,tint] = colorsFor(row.ticker);
      const share = risk ? row.risk_share : row.weight;
      const name = row.name || row.ticker;
      return `<li class="holding-row" style="--symbol-ink:${ink};--symbol-tint:${tint}"><span class="ticker-symbol" aria-hidden="true" title="${esc(row.ticker)}">${esc(labelSymbol(row.ticker).slice(0,5))}</span><span class="ticker-details"><strong title="${esc(name)}">${esc(name)}</strong><small>${esc(row.ticker)}</small></span>${percentBar(share)}<strong class="holding-value" aria-label="${esc(`${option}: ${pct(share)}`)}">${pct(share)}</strong></li>`;
    }).join('')}</ul><p class="holdings-note">${risk ? (available ? 'Share of historical portfolio variance. Negative contributions offset portfolio risk.' : 'Risk contributions cannot be estimated from the available return history.') : reviewingAfter ? 'Portfolio weights after applying the proposed order.' : 'Portfolio weights before the proposed order.'}</p>`);
  }

  function renderExposure() {
    if (!state.result) return;
    const ticker = companyTicker();
    const current = reviewCompanyExposure(state.result,'before',ticker);
    const future = after() ? reviewCompanyExposure(state.result,'after',ticker) : null;
    const strip = $('#exposure-strip');
    if (!(current.mapped > 0 || future?.mapped > 0)) { strip.hidden = true; return; }
    const title = `${companyName(ticker)} exposure`;
    const summary = future ? `${mappedLabel(current)} current → ${mappedLabel(future)} after order` : mappedLabel(current);
    const portions = current.funds.map((fund) => `${pct(fund.share,2)} through ${labelSymbol(fund.ticker)}`);
    const currentParts = [`${pct(current.direct,2)} directly held`, ...portions].join(' + ');
    const hasGap = !current.complete || (future && !future.complete);
    const description = future ? (hasGap ? 'Additional exposure through funds may be unknown.' : 'Direct and disclosed ETF stakes combined.') : `${currentParts}.${hasGap ? ' Other ETF exposure may be unknown.' : ''}`;
    strip.hidden = false;
    renderMarkup(strip, `<span class="mini-icon">${icon('stack')}</span><div><strong>${esc(title)} / ${esc(summary)}</strong><p>${esc(description)}</p></div><a class="text-link" href="#look-through" data-company-jump>See calculation ${icon('arrow-up-right')}</a>`);
  }

  function metric(name, value, sub, tone = '') {
    return `<div class="metric" data-tone="${tone}"><p class="metric-label">${tone ? '<i></i>' : ''}${esc(name)}</p><p class="metric-value">${esc(value)}</p><p class="metric-sub">${esc(sub)}</p></div>`;
  }
  function checks(before, comparison) {
    const records = [...new Map([...(before?.checks || []), ...(comparison?.checks || [])].map((c) => [c.id,c])).values()];
    if (!records.length && !finite(before?.canada_share) && !finite(comparison?.canada_share)) return '';
    const chips = records.map((c) => `<p class="risk-notice" data-tone="${c.status === 'breached' ? 'warn' : c.status === 'within' ? 'ok' : 'unknown'}">${icon(c.status === 'within' ? 'check' : 'info')}<span><strong>${esc(c.label)}:</strong> ${esc(c.detail)}</span></p>`);
    if (finite(before?.canada_share) && !records.some((c) => /canad/i.test(c.label))) chips.push(`<p class="risk-notice">${icon('info')}<span><strong>Canada exposure:</strong> ${pct(before.canada_share)} current${finite(comparison?.canada_share) ? ` → ${pct(comparison.canada_share)} after order` : ''}.</span></p>`);
    return chips.join('');
  }
  function marketContext(context = []) {
    return Array.isArray(context) && context.length ? `<details class="context"><summary>${icon('book')} Market context ${icon('chevron','chevron')}</summary><ul>${context.map((c) => `<li><strong>${esc(c.title)}</strong>${c.date ? ` / ${esc(date(c.date))}` : ''}: ${esc(c.detail)} ${sourceHTML(c.source,'Source')}</li>`).join('')}</ul></details>` : '';
  }
  function renderRisk() {
    resize?.disconnect();
    resize = null;
    if (!state.result) return;
    const before = state.result.before, comparison = after(), mix = comparison || before;
    const loss = measure(mix), haveBoth = measure(before) && measure(comparison);
    const limits = state.result.limits || {};
    const drawdownLimit = limits.drawdown ?? limits.drawdown_limit ?? state.input.drawdown_limit;
    const capacity = limits.capacity ?? state.input.capacity;
    const hasDrawdownLimit = finite(drawdownLimit);
    const hasCapacity = finite(capacity);
    const order = activeOrder();
    $('#risk-description').textContent = comparison && order
      ? `${labelSymbol(order.ticker)} at ${pct(order.weight)} target weight${order.from_ticker ? ` / funded from ${labelSymbol(order.from_ticker)}` : ' / funded proportionally from other holdings'}.`
      : 'See how far your current portfolio fell from its running peak.';
    const example = Boolean(state.example);
    $('#risk-title').textContent = example ? 'Would it fit the example limits?' : 'Would it fit your limits?';
    const subject = comparison ? 'The proposed order' : 'The current portfolio';
    const note = example ? 'This replay uses the example’s assumed limits.' : 'This replay uses your entered limits.';
    const busted = [mix?.limit_breached === true ? 'drawdown limit' : '', mix?.capacity_breached === true ? 'dollar loss floor' : ''].filter(Boolean);
    const summary = !loss ? ['unknown', 'Historical loss could not be measured.', 'The available price history may not cover all holdings.']
      : !hasDrawdownLimit && !hasCapacity ? ['neutral', 'Historical loss measured.', 'Add an investor limit to compare it with the replay.']
      : busted.length ? ['warn', `${subject} would have crossed ${busted.length > 1 ? 'both limits' : `the ${busted[0]}`}.`, note]
      : ['ok', `${subject} stayed within ${hasDrawdownLimit && hasCapacity ? 'both limits' : hasDrawdownLimit ? 'the drawdown limit' : 'the dollar loss floor'} in this replay.`, note];
    const delta = haveBoth ? comparison.loss_dollars - before.loss_dollars : null;
    const shift = haveBoth ? Math.abs(comparison.max_drawdown) - Math.abs(before.max_drawdown) : null;
    const valueName = (row) => measure(row) ? `${money(row.loss_dollars)} peak-to-trough${row.trough_date ? ` / ${date(row.trough_date)}` : ''}` : 'Insufficient price history';
    const template = `<p class="risk-notice" data-tone="${summary[0]}">${icon(summary[0] === 'ok' ? 'check' : summary[0] === 'neutral' ? 'info' : 'alert')}<span><strong>${esc(summary[1])}</strong> ${esc(summary[2])}</span></p>`
      + `<div class="metrics">${metric('Current max drawdown', measure(before) ? pct(before.max_drawdown) : '—', valueName(before), 'before')}`
      + (comparison ? metric('After-order max drawdown', measure(comparison) ? pct(comparison.max_drawdown) : '—', valueName(comparison), 'after') : metric(example ? 'Example drawdown limit' : 'Your drawdown limit', hasDrawdownLimit ? pct(-drawdownLimit) : 'Not set', 'Peak-to-trough tolerance'))
      + (haveBoth && finite(delta) ? metric('Change in worst loss', `${delta > 0 ? '+' : delta < 0 ? '−' : ''}${money(Math.abs(delta))}`, `${pp(shift)} ${shift > 0 ? 'deeper' : shift < 0 ? 'shallower' : 'change'} drawdown`) : metric(example ? 'Example loss capacity' : 'Your loss capacity', finite(capacity) ? money(capacity) : 'Not set', 'Sets a floor below starting value')) + '</div>';
    const target = (comparison?.holdings || []).find((item) => rootSymbol(item.ticker) === rootSymbol(order?.ticker));
    const contrast = target && finite(target.risk_share) ? `<div class="risk-insight">${icon('wave')}<p><strong>${esc(target.name || target.ticker)} after the order</strong><span>${pct(target.weight)} of the money / ${pct(target.risk_share)} of measured portfolio risk</span></p></div>` : '';
    const capacityDetail = finite(capacity) && finite(mix?.capacity_sessions) ? `<div class="risk-insight">${icon('wallet')}<p><strong>Dollar loss floor: ${money((state.result.amount ?? state.input.amount) - capacity)}</strong><span>${mix.capacity_sessions} modeled sessions below it${comparison && finite(before?.capacity_sessions) ? `, versus ${before.capacity_sessions} in the current mix` : ''}. Lowest balance: ${money(mix.lowest_value)}.</span></p></div>` : '';
    const canChart = before?.points?.length > 1 || comparison?.points?.length > 1;
    const chart = canChart ? `<div class="chart-card"><div class="chart-top"><div><h3>Drawdown from running peak</h3><p>${esc(reviewWindow(state.result.start, state.result.as_of))}${state.result.sampled || before?.sampled ? ' / sampled display' : ''} / Historical replay</p></div><ul class="chart-legend"><li><i></i> Current</li>${comparison ? '<li class="after"><i></i> After order</li>' : ''}${hasDrawdownLimit ? `<li class="limit"><i></i> ${example ? 'Example limit' : 'Your limit'} (${pct(-drawdownLimit)})</li>` : ''}</ul></div><div class="chart-frame" id="drawdown-chart"></div><div class="chart-readout" id="chart-readout"></div></div>` : empty('No chart available', 'There are too few dated observations to plot the historical path.');
    renderMarkup($('#risk-result'), template + chart + (contrast || capacityDetail ? `<div class="risk-insights">${contrast}${capacityDetail}</div>` : '') + checks(before, comparison) + marketContext(state.result.context));
    if (canChart) renderChart(before, comparison, drawdownLimit);
  }

  function renderChart(before, comparison, limit) {
    const host = $('#drawdown-chart'), readout = $('#chart-readout');
    const b = drawdownSeries(before?.points), a = drawdownSeries(comparison?.points);
    const dates = (b.length ? b : a).map(([d]) => d);
    if (dates.length < 2) return;
    const timestamp = (d) => Date.parse(d);
    const day = dates.map(timestamp), first = day[0], final = day[day.length - 1];
    const mapA = new Map(a), mapB = new Map(b);
    const bottomDepth = Math.max(.045, limit || 0, ...b.map(([,v]) => -v), ...a.map(([,v]) => -v));
    const step = Math.ceil(bottomDepth / 4 * 20) / 20;
    const bottom = Math.max(step, Math.ceil((bottomDepth + .001) / step) * step);
    const trough = dates.indexOf(comparison?.trough_date || before?.trough_date);
    let cursor = trough >= 0 ? trough : dates.length - 1;
    let geometry;
    const bind = () => {
      const {w,h,l,r,t,bottomY,x,y} = geometry;
      const points = (rows) => rows.map(([d,v],i) => `${i ? 'L' : 'M'}${x(d).toFixed(1)} ${y(v).toFixed(1)}`).join('');
      const plotA = points(a), plotB = points(b), fillRows = a.length ? a : b, fillData = a.length ? plotA : plotB;
      const fill = fillData ? `${fillData}L${x(fillRows.at(-1)[0]).toFixed(1)} ${bottomY}L${x(fillRows[0][0]).toFixed(1)} ${bottomY}Z` : '';
      const axis = Array.from({length:Math.round(bottom/step) + 1}, (_,i) => {
        const share = -i * step, row = y(share);
        return `<line class="axis-line" x1="${l}" x2="${w-r}" y1="${row}" y2="${row}"/><text x="${l-5}" y="${row+3}" text-anchor="end">${pct(share,0)}</text>`;
      }).join('');
      const ticks = w < 420 ? 4 : 6;
      const timeLabels = Array.from({length:ticks}, (_,i) => {
        const at = i / (ticks - 1), index = Math.round(at * (dates.length - 1));
        return `<text x="${x(dates[index])}" y="${h-6}" text-anchor="${i === 0 ? 'start' : i === ticks - 1 ? 'end' : 'middle'}">${esc(monthFormat.format(new Date(day[index])))}</text>`;
      }).join('');
      renderMarkup(host, `<svg class="chart-svg" viewBox="0 0 ${w} ${h}" aria-hidden="true"><defs><linearGradient id="chart-fade" x2="0" y2="1"><stop stop-color="${a.length ? '#ff5fc8' : '#bdc5d1'}" stop-opacity=".17"/><stop offset="1" stop-color="${a.length ? '#ff5fc8' : '#bdc5d1'}" stop-opacity=".018"/></linearGradient></defs>${axis}${timeLabels}<path d="${fill}" fill="url(#chart-fade)"/>${finite(limit) ? `<line class="limit-line" x1="${l}" x2="${w-r}" y1="${y(-limit)}" y2="${y(-limit)}"/>` : ''}<path class="before-line" d="${plotB}"/><path class="after-line" d="${plotA}"/><line x1="0" x2="0" y1="${t}" y2="${bottomY}" class="chart-cursor" id="chart-cursor"/><circle r="3.1" fill="#596780" class="chart-dot" id="chart-before-dot"/><circle r="3.7" fill="#751739" class="chart-dot" id="chart-after-dot"/></svg><div class="chart-access" tabindex="0" role="slider" aria-label="Historical chart date. Use left and right arrows to explore" aria-valuemin="0" aria-valuemax="${dates.length-1}"></div>`);
      const control = $('.chart-access',host);
      const navigate = (e) => {
        const rect = control.getBoundingClientRect();
        const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left - l)/(w - l - r)));
        const target = first + (final - first) * ratio;
        let lo = 0, hi = day.length - 1;
        while (lo < hi) { const mid = (lo+hi) >>> 1; if (day[mid] < target) lo = mid+1; else hi = mid; }
        if (lo && Math.abs(day[lo-1] - target) < Math.abs(day[lo] - target)) lo--;
        move(lo);
      };
      control.addEventListener('pointermove', (e) => { if (e.pointerType !== 'touch') navigate(e); });
      control.addEventListener('click', navigate);
      control.addEventListener('keydown', (e) => {
        const options = {ArrowLeft:cursor-1,ArrowRight:cursor+1,ArrowUp:cursor+1,ArrowDown:cursor-1,PageUp:cursor+20,PageDown:cursor-20,Home:0,End:dates.length-1};
        if (!(e.key in options)) return;
        e.preventDefault(); move(options[e.key]);
      });
      move(cursor);
    };
    function move(next) {
      cursor = Math.max(0, Math.min(dates.length-1,next));
      const d = dates[cursor], x = geometry.x(d), vb = mapB.get(d), va = mapA.get(d);
      const mark = $('#chart-cursor',host);
      mark.setAttribute('x1',x); mark.setAttribute('x2',x);
      [[vb,'#chart-before-dot'],[va,'#chart-after-dot']].forEach(([value,key]) => {
        const dot = $(key,host); dot.style.display = finite(value) ? '' : 'none';
        if (finite(value)) { dot.setAttribute('cx',x); dot.setAttribute('cy',geometry.y(value)); }
      });
      const control = $('.chart-access',host), datestr = date(d);
      control.setAttribute('aria-valuenow',cursor);
      control.setAttribute('aria-valuetext',`${datestr}. Current ${pct(vb)}${a.length ? `, after order ${pct(va)}` : ''}`);
      renderMarkup(readout, `<span><strong>${esc(datestr)}</strong> / Current ${pct(vb)}${a.length ? ` / After order ${pct(va)}` : ''}</span><span>Hover or use arrow keys</span>`);
    }
    function layout() {
      const w = Math.max(190,Math.floor(host.clientWidth)), h = Math.max(150,Math.floor(host.clientHeight));
      if (geometry?.w === w && geometry?.h === h) return;
      const l = 42, r = 8, t = 13, bottomY = h - 24;
      geometry = {w,h,l,r,t,bottomY,x:(d) => l + (timestamp(d)-first)/Math.max(1,final-first)*(w-l-r),y:(v) => t + (-v/bottom)*(bottomY-t)};
      bind();
    }
    layout();
    if (typeof ResizeObserver !== 'undefined') { resize = new ResizeObserver(layout); resize.observe(host); }
  }

  function directCompanyRows(side) {
    const equity = new Set(state.assets.filter((asset) => asset.asset_class === 'equity').map((asset) => asset.ticker));
    return (state.result[side]?.holdings || []).filter((holding) => equity.has(holding.ticker)).map((holding) => ({
      ticker:holding.ticker, name:holding.name, share:holding.weight, direct_share:holding.weight,
    }));
  }

  function renderAllocation() {
    const panel = $('#portfolio-allocation');
    panel.hidden = !after();
    if (panel.hidden) return;
    const host = $('#allocation-result');
    const companies = state.allocationView === 'companies';
    const allocation = state.result.allocation || {};
    const saved = state.result.mode === 'saved';
    const exposure = {};
    for (const side of ['before','after']) {
      const covered = state.result.exposure?.[side];
      exposure[side] = Array.isArray(covered) ? covered : directCompanyRows(side);
    }
    const records = compareAllocation({allocation,exposure},state.allocationView);
    $$('[data-allocation-view]',panel).forEach((button) => button.setAttribute('aria-pressed',String(button.dataset.allocationView === state.allocationView)));
    if (!records.length) {
      const message = companies ? 'No named company positions are available for these mixes.' : 'Portfolio-wide industry mapping is unavailable in this review. You can still inspect individual ETF snapshots below.';
      renderMarkup(host,empty(companies ? 'No mapped companies' : 'Industry breakdown unavailable',message));
      return;
    }
    const isUnmapped = (name) => /unmapped|unknown|unclassified/i.test(name);
    const complete = (side) => {
      if (companies) {
        if (saved) {
          const equityETFs = new Set(state.assets.filter((asset) => asset.asset_class === 'etf_equity').map((asset) => asset.ticker));
          return !(state.result[side]?.holdings || []).some((holding) => equityETFs.has(holding.ticker));
        }
        const coverage = allocation[side]?.equity_company_coverage;
        return coverage === null || (finite(coverage) && coverage >= 1 - 1e-8);
      }
      const rows = allocation[side]?.industries;
      return Array.isArray(rows) && !rows.some((entry) => entry.share > 0 && isUnmapped(entry.name));
    };
    const cell = (record, side, unmapped) => {
      if (!record) return `<td>${complete(side) || (unmapped && allocation[side]?.industries?.length) ? '0%' : '<span class="small">Unknown</span>'}</td>`;
      const direct = finite(record.direct_share) ? record.direct_share : 0;
      const viaFunds = Math.max(0,record.share - direct);
      const split = companies && record.share > 0 ? `<small>${pct(direct,2)} direct + ${pct(viaFunds,2)} via ETFs</small>` : '';
      return `<td><strong>${pct(record.share,2)}</strong>${split}</td>`;
    };
    const initialRows = records.slice(0,8);
    if (!companies) {
      for (const row of records.slice(8)) if (isUnmapped(row.name)) initialRows.push(row);
    }
    const shown = state.allocationExpanded ? records : initialRows;
    const coverageLabel = (side) => {
      if (saved) return 'Direct stock holdings shown';
      const value = allocation[side]?.equity_company_coverage;
      return value === null ? 'No equity exposure' : finite(value) ? `${pct(value,2)} of equity covered` : 'Coverage unavailable';
    };
    const coverage = companies ? `<div class="allocation-coverage"><span>Current: ${esc(coverageLabel('before'))}</span><span>After order: ${esc(coverageLabel('after'))}</span></div>` : '';
    const explanation = companies ? (saved ? 'Saved examples show direct stock holdings. The live review includes covered ETF constituents.' : 'Company totals combine direct holdings and named ETF constituents as shares of the whole portfolio. Additional exposure may be unknown when coverage is partial.') : 'Direct holdings and disclosed ETF industries are measured as shares of the whole portfolio. Unmapped equity is listed at its portfolio weight. Fund dates and sources appear in the individual ETF views.';
    const table = `<table class="fund-table allocation-table"><thead><tr><th scope="col">${companies ? 'Company' : 'Industry or asset type'}</th><th scope="col">Current</th><th scope="col">After order</th></tr></thead><tbody>${shown.map((row) => {
      const unmapped = !companies && isUnmapped(row.name);
      const highlighted = companies && rootSymbol(row.ticker) === rootSymbol(activeOrder()?.ticker);
      return `<tr class="${unmapped ? 'other-row' : highlighted ? 'featured-company' : ''}"><td><strong>${esc(row.name)}</strong>${row.ticker ? `<small>${esc(row.ticker)}</small>` : ''}</td>${cell(row.before,'before',unmapped)}${cell(row.after,'after',unmapped)}</tr>`;
    }).join('')}</tbody></table>`;
    const more = records.length > initialRows.length ? `<button type="button" class="button outline" id="show-allocation-rows" aria-expanded="${state.allocationExpanded}">${state.allocationExpanded ? 'Show fewer' : `Show all ${records.length}`}</button>` : '';
    renderMarkup(host,`${coverage}${table}<div class="allocation-foot"><p class="small">${esc(explanation)}</p>${more}</div>`);
    $('#show-allocation-rows',host)?.addEventListener('click',() => {
      state.allocationExpanded = !state.allocationExpanded;
      renderAllocation();
      $('#show-allocation-rows',host)?.focus({preventScroll:true});
    });
  }

  function renderFunds() {
    if (!state.result) return;
    const host = $('#fund-result'), funds = state.result.funds || [];
    const view = state.fundView, companies = view === 'companies';
    $$('#look-through [data-fund-view]').forEach((item) => item.setAttribute('aria-pressed', String(item.dataset.fundView === view)));
    if (!funds.length) { renderMarkup(host, empty('No ETF holdings available', 'This portfolio has no tracked ETF holdings in the current review.')); return; }
    const fund = funds.find((f) => f.ticker === state.fundTicker) || funds[0];
    state.fundTicker = fund.ticker;
    const entries = (Array.isArray(fund[view]) ? fund[view] : []).slice().sort((a,b) => (b.share || 0)-(a.share || 0));
    const coverage = companies ? fund.company_coverage ?? fund.coverage : fund.industry_coverage ?? fund.coverage;
    const timestamp = companies ? fund.date : fund.industry_date ?? fund.date;
    const compare = Boolean(after());
    const ticker = companyTicker();
    const featured = (r) => companies && rootSymbol(r.ticker) === rootSymbol(ticker);
    const sample = state.allFunds ? entries : entries.slice(0,7);
    if (companies && !sample.some(featured)) { const focus = entries.find(featured); if (focus) sample.push(focus); }
    const directAndFund = companies ? exposureCalculation(ticker) : '';
    const rows = sample.map((row) => {
      const current = row.before_share ?? row.share * fund.before_weight;
      const future = row.after_share ?? row.share * fund.after_weight;
      return `<tr class="${featured(row) ? 'featured-company' : ''}"><td><strong>${esc(row.name || row.ticker)}</strong>${companies && row.ticker ? `<small>${esc(row.ticker)}</small>` : ''}</td><td>${pct(row.share,2)}${percentBar(row.share)}</td><td>${pct(current,2)}</td>${compare ? `<td>${pct(future,2)}</td>` : ''}</tr>`;
    }).join('');
    const other = finite(coverage) && coverage < .998
      ? `<tr class="other-row"><td>Unmapped in snapshot</td><td>${pct(1 - coverage,2)}</td><td>—</td>${compare ? '<td>—</td>' : ''}</tr>` : '';
    const data = entries.length ? `<table class="fund-table"><thead><tr><th scope="col">${companies ? 'Company' : 'Industry'}</th><th scope="col">Of this ETF</th><th scope="col">Of your portfolio${compare ? ' / current' : ''}</th>${compare ? '<th scope="col">Of your portfolio / after</th>' : ''}</tr></thead><tbody>${rows}${other}</tbody></table>` : empty(companies && fund.companies_listed ? 'Company names aren’t included in this view' : `${companies ? 'Company' : 'Industry'} breakdown unavailable`, companies && fund.companies_listed ? `The issuer snapshot reports ${fund.companies_listed} mapped constituents. Open the issuer source for their latest breakdown.` : 'This snapshot has no mapped holdings for this breakdown. Missing exposure is unknown.');
    const footing = entries.length ? `Portfolio share = the fund’s portfolio weight × its constituent weight.${entries.length > sample.length ? ` Showing ${sample.length} of ${entries.length}.` : ''}` : 'A missing breakdown is not zero exposure.';
    const badge = finite(coverage) ? `${pct(coverage,1)} ${entries.length ? 'mapped' : 'in source'}` : 'Coverage unavailable';
    renderMarkup(host, `<div class="fund-selector"><label class="field" for="fund-select"><span>Choose a fund</span><span class="select-wrap"><select id="fund-select">${funds.map((f) => `<option value="${esc(f.ticker)}" ${f.ticker === fund.ticker ? 'selected' : ''}>${esc(`${labelSymbol(f.ticker)} / ${f.name || f.ticker}`)}</option>`).join('')}</select>${icon('chevron')}</span></label><span class="badge ${!entries.length || !finite(coverage) || coverage < .95 ? 'low' : 'ok'}">${icon('info')} ${esc(badge)}</span></div>`
      + `<dl class="fund-meta"><div><dt>Data date</dt><dd>${esc(date(timestamp))}</dd></div><div><dt>Current fund weight</dt><dd>${pct(fund.before_weight)}</dd></div><div><dt>${compare ? 'After-order fund weight' : (companies ? 'Company coverage' : 'Industry coverage')}</dt><dd>${compare ? pct(fund.after_weight) : pct(coverage)}</dd></div></dl>` + directAndFund + data
      + `<div class="fund-footer"><p class="small">${esc(footing)}</p>${sourceHTML(fund.source,'Issuer source')}</div>${entries.length > 7 ? `<button class="button outline fund-more" id="fund-more" type="button">${state.allFunds ? 'Show fewer' : `Show all ${entries.length}`}</button>` : ''}`);
    $('#fund-select',host).addEventListener('change', (e) => { state.fundTicker = e.target.value; state.allFunds = false; renderFunds(); $('#fund-select',host)?.focus({preventScroll:true}); });
    $('#fund-more',host)?.addEventListener('click', () => { state.allFunds = !state.allFunds; renderFunds(); $('#fund-more',host)?.focus({preventScroll:true}); });
  }

  function exposureCalculation(ticker) {
    const current = reviewCompanyExposure(state.result,'before',ticker);
    const future = after() ? reviewCompanyExposure(state.result,'after',ticker) : null;
    if (!(current.mapped > 0 || future?.mapped > 0)) return '';
    const groups = [[current,'Current'], ...(future ? [[future,'After order']] : [])];
    const text = groups.map(([entry,name]) => {
      const parts = entry.funds.map((fund) => `${pct(fund.share,2)} through ${labelSymbol(fund.ticker)}`);
      const components = [`${pct(entry.direct,2)} directly held`,...parts].join(' + ');
      const coverage = entry.complete ? '' : ' Additional exposure through ETFs may be unknown.';
      return `<li><strong>${name}:</strong> ${esc(components)}. ${esc(mappedLabel(entry))}.${coverage}</li>`;
    }).join('');
    return `<details class="company-calc" id="company-calculation" open><summary>${esc(companyName(ticker))} across the portfolio</summary><ul>${text}</ul></details>`;
  }

  function renderEvidence() {
    if (!state.result) return;
    const isCurrent = !after() && Boolean(state.result.after);
    const beforeEvidence = isCurrent && Array.isArray(state.result.before_evidence) ? state.result.before_evidence : null;
    const records = beforeEvidence || state.result.evidence || [];
    const mix = after() || state.result.before;
    function detail(item) {
      if (!isCurrent || beforeEvidence) return item.detail;
      if (item.id === 'drawdown' && measure(mix)) return `The current portfolio’s largest decline was ${pct(Math.abs(mix.max_drawdown))}, a fall of ${money(mix.loss_dollars)} from peak to trough.`;
      if (item.id === 'capacity') return 'The loss budget defines a floor from the portfolio’s starting value. The replay counts the days spent below this floor.';
      if (item.id === 'risk') return 'The Risk lens uses each holding’s historical contribution to portfolio variance.';
      if (item.id === 'countries' && finite(mix?.canada_share)) return `The current estimated Canadian allocation is ${pct(mix.canada_share)}.`;
      return item.detail;
    }
    renderMarkup($('#evidence-list'), records.length ? records.map((item) => `<details class="evidence-item" id="proof-${esc(item.id)}"><summary><span>${icon('book')}${esc(item.label)}</span>${icon('chevron','chevron')}</summary><div class="evidence-item-body"><p>${esc(detail(item))}</p>${item.source ? `<p>${sourceHTML(item.source,'Open source')}</p>` : ''}</div></details>`).join('') : empty('No evidence record available', 'Run a portfolio review to inspect the sources behind it.'));
    const explain = $('#explain-result');
    state.explanationToken++;
    explain.hidden = true;
    explain.replaceChildren();
    $('#explain-button').disabled = false;
    $('#explain-concern').disabled = !state.live;
  }

  async function explain() {
    if (!state.result) return;
    const focus = $('#explain-goal').value;
    const target = $('#explain-result');
    const button = $('#explain-button');
    const concern = $('#explain-concern').value.trim().slice(0,240);
    const methodRef = $('#proof-method') ? 'method' : 'drawdown';
    const shortcuts = {
      limits: ['drawdown','Explain my loss limits'],
      exposure: ['funds','Where is my ETF company exposure?'],
      method: [methodRef,'Explain how the historical replay was calculated'],
    };
    const [ref, phrase] = shortcuts[focus] || shortcuts.limits;
    const result = state.result;
    const token = ++state.explanationToken;
    const reviewID = result.after && !state.order ? result.before_review_id : result.review_id;
    const evidenceNode = (id) => document.getElementById(`proof-${id}`);
    const localText = evidenceNode(ref)?.querySelector('.evidence-item-body p')?.textContent;
    const local = localText || 'This focus has no entry in the review record. Check the available evidence.';
    let output = {mode:'rules', summary:local, evidence_id:ref};
    target.hidden = false;
    renderMarkup(target, '<p>Reading the review evidence…</p>');
    button.disabled = true;
    if (state.live && result.mode === 'live' && reviewID) {
      try {
        output = await request('api/review/explain',{review_id:reviewID,goal:concern || phrase}, 16500);
      } catch (error) {
        if ((concern || error.status === 422) && token === state.explanationToken) {
          const message = error.name === 'AbortError' ? 'The explanation took too long. Try again or use an evidence shortcut.' : error.message;
          renderMarkup(target, `<p class="form-error" role="alert">${esc(message)}</p>`);
          button.disabled = false;
          return;
        }
      }
    } else if (concern) {
      target.textContent = 'The live explanation is available after you run a custom portfolio or preview the saved order.';
      button.disabled = false;
      return;
    }
    if (token !== state.explanationToken) return;
    const raw = output.evidence_id || ref;
    const link = evidenceNode(raw) ? raw : ref;
    if (!concern && focus === 'method' && evidenceNode(methodRef)) evidenceNode(methodRef).open = true;
    const related = Array.isArray(output.suggestions) ? output.suggestions.filter((item) => item.evidence_id !== link && evidenceNode(item.evidence_id)).slice(0,3) : [];
    const suggestions = related.length ? `<div class="explain-suggestions"><strong>Related evidence</strong><ul>${related.map((item) => `<li><a href="#proof-${esc(item.evidence_id)}" class="text-link" data-explanation-link="${esc(item.evidence_id)}">${esc(item.label)} ${icon('arrow-up-right')}</a>${item.summary ? `<p>${esc(item.summary)}</p>` : ''}</li>`).join('')}</ul></div>` : '';
    const proof = evidenceNode(link) ? `<a href="#proof-${esc(link)}" class="text-link" data-explanation-link="${esc(link)}">Read supporting evidence ${icon('arrow-up-right')}</a>` : '';
    let trace = '';
    if (output.mode === 'bedrock' && output.request_id) {
      const count = 1 + related.length;
      trace = `<details class="agent-trace"><summary>Agent trace</summary><p><strong>Tool:</strong> open_evidence</p><p>Opened ${count} evidence ${count === 1 ? 'card' : 'cards'}</p><p><strong>Request ID:</strong> <span>${esc(output.request_id)}</span></p></details>`;
    }
    renderMarkup(target, `<span class="badge ${output.mode === 'bedrock' ? 'ok' : ''}">${icon('spark')} ${output.mode === 'bedrock' ? 'Amazon Bedrock' : 'Evidence summary'}</span><p>${esc(output.summary || local)}</p>${proof}${suggestions}${trace}`);
    button.disabled = false;
  }

  function render() {
    renderSetup(); renderHoldings(); renderScenario(); renderExposure(); renderRisk(); renderAllocation(); renderFunds(); renderEvidence();
  }

  function setResult(input, result, configureOrder = false) {
    state.input = input;
    state.result = result;
    if (!state.example) state.holdingsState = 'before';
    state.order = configureOrder && canUseOrder();
    render();
  }

  async function activate(id, verify = true) {
    const example = state.examples.find((item) => item.id === id);
    if (!example) return;
    const token = ++state.feedToken;
    state.example = example;
    state.fundTicker = null;
    state.allFunds = false;
    state.allocationExpanded = false;
    state.holdingsState = 'before';
    picker.value = id;
    setResult(example.input, example.result);
    if (!verify) return;
    try {
      const result = await request('api/review',example.input,9000);
      if (token !== state.feedToken || !result?.before || result.mode !== 'live') return;
      state.live = true;
      setResult(example.input, result, state.order);
    } catch { /* Keep the named saved review usable in static and offline deployments. */ }
  }

  let rowNumber = 0;
  function holdingRow(ticker = '', weight = '') {
    const node = document.createElement('div');
    node.className = 'holding-editor-row';
    const id = ++rowNumber;
    renderMarkup(node, `<input aria-label="Holding ${id} ticker" class="edit-ticker" type="text" list="asset-list" maxlength="18" autocomplete="off" placeholder="e.g. XIU.TO" value="${esc(ticker)}"><input aria-label="Holding ${id} weight in percent" class="edit-weight" type="number" min="0.0001" max="100" step="any" inputmode="decimal" placeholder="0" value="${esc(weight)}"><button type="button" class="icon-button remove-holding" aria-label="Remove holding ${id}">${icon('close')}</button>`);
    $('#edit-rows').append(node);
    return node;
  }
  const readRows = () => $$('.holding-editor-row').map((row) => ({ticker:$('.edit-ticker',row).value,weight:$('.edit-weight',row).value}));
  function updateEditor(oldFunding) {
    const rows = readRows(), select = $('#edit-funding'), choice = typeof oldFunding === 'string' ? oldFunding : select.value;
    const total = rows.reduce((sum,row) => sum + (number(row.weight) || 0), 0);
    const totalNode = $('#editor-total');
    totalNode.textContent = `${Number(total.toFixed(3))}% allocated`;
    totalNode.dataset.valid = String(Math.abs(total - 100) < .0001);
    const held = [...new Set(rows.map((r) => symbol(r.ticker)).filter(validSymbol))];
    const selected = symbol($('#edit-order-ticker').value);
    renderMarkup(select, '<option value="">All other holdings, proportionally</option>' + held.filter((t) => t !== selected).map((t)=>`<option value="${esc(t)}">${esc(t)}</option>`).join(''));
    if (held.includes(choice) && choice !== selected) select.value = choice;
    $('#edit-order-fields').hidden = !$('#edit-has-order').checked;
  }
  function renderSecurities() {
    const matches = matchSecurities(state.assets,$('#security-search').value);
    const inPortfolio = new Set(readRows().map((row) => symbol(row.ticker)));
    const blocks = Object.entries(securityGroups).map(([className,label]) => {
      const assets = matches.filter((asset) => asset.asset_class === className);
      if (!assets.length) return '';
      return `<div class="security-group"><strong>${esc(label)}</strong><ul>${assets.map((asset) => `<li><button class="security-option" type="button" data-security-ticker="${esc(asset.ticker)}" ${inPortfolio.has(asset.ticker) ? 'disabled' : ''}><strong>${esc(asset.ticker)}</strong><span>${esc(asset.name)}</span>${icon(inPortfolio.has(asset.ticker) ? 'check' : 'plus')}</button></li>`).join('')}</ul></div>`;
    }).join('');
    renderMarkup($('#security-results'), blocks || '<p class="small">No matching investments in this data set.</p>');
  }

  function openEditor(configureOrder = state.order, own = false) {
    if (!state.live || !state.input) return;
    const input = own ? (state.customInput || {portfolio:{}, amount:100000, drawdown_limit:null, capacity:null}) : state.input;
    const order = input.order;
    $('#edit-amount').value = input.amount ?? '';
    $('#edit-limit').value = percentInput(input.drawdown_limit);
    $('#edit-capacity').value = input.capacity ?? '';
    $('#edit-crypto').value = percentInput(input.crypto_limit);
    $('#edit-values').checked = Boolean(input.values_screen);
    $('#edit-rows').replaceChildren(); rowNumber = 0;
    Object.entries(input.portfolio || {}).forEach(([ticker, weight]) => holdingRow(ticker,percentInput(weight)));
    if (!$('#edit-rows').children.length) holdingRow();
    $('#edit-has-order').checked = Boolean((configureOrder || own) && (order || !own));
    $('#edit-order-ticker').value = order?.ticker || 'NVDA';
    $('#edit-order-weight').value = percentInput(order?.weight) || '10';
    $('#editor-error').hidden = true;
    $('#security-search').value = '';
    $('#security-browser').open = false;
    $('#editor-limits').open = false;
    updateEditor(order?.from_ticker || '');
    if (!dialog.open) dialog.showModal();
  }
  async function submit(e) {
    e.preventDefault();
    if (state.busy) return;
    const error = $('#editor-error'), button = $('#run-review');
    error.hidden = true;
    try {
      const input = parseReviewInput({rows:readRows(),amount:$('#edit-amount').value,limit:$('#edit-limit').value,capacity:$('#edit-capacity').value,cryptoLimit:$('#edit-crypto').value,valuesScreen:$('#edit-values').checked,
        order:$('#edit-has-order').checked ? {ticker:$('#edit-order-ticker').value,weight:$('#edit-order-weight').value,from_ticker:$('#edit-funding').value} : null});
      state.busy = true; button.disabled = true; dialog.setAttribute('aria-busy','true');
      button.textContent = 'Running review…';
      const result = await request('api/review',input);
      if (!result?.before) throw new Error('The review service did not return a portfolio.');
      state.feedToken++; state.example = null; state.customInput = input; state.live = true; state.fundTicker = null;
      picker.value = '__own';
      setResult(input,result,Boolean(input.order));
      dialog.close();
      jump(input.order ? 'risk-review' : 'portfolio', true);
      announce('Your portfolio review is ready.');
    } catch (e) {
      error.textContent = e.name === 'AbortError' ? 'The review took too long. Please try again.' : e.message;
      error.hidden = false;
    } finally {
      state.busy = false; button.disabled = false; dialog.removeAttribute('aria-busy');
      renderMarkup(button, `Run portfolio review ${icon('arrow')}`);
      renderScenario();
    }
  }

  picker.addEventListener('change', (e) => {
    const id = e.target.value;
    if (id === '__own') {
      picker.value = state.example?.id || '__own';
      openEditor(false, true);
    } else { activate(id, state.live); announce(`${exampleName(state.examples.find((item) => item.id === id))} example selected.`); }
  });
  $('#open-editor').addEventListener('click', () => openEditor());
  $('#close-editor').addEventListener('click', () => { if (!state.busy) dialog.close(); });
  $('#cancel-editor').addEventListener('click', () => { if (!state.busy) dialog.close(); });
  dialog.addEventListener('cancel', (e) => { if (state.busy) e.preventDefault(); });
  $('#review-form').addEventListener('submit', submit);
  $('#add-holding').addEventListener('click', () => { $('.edit-ticker',holdingRow()).focus(); updateEditor(); });
  $('#edit-rows').addEventListener('input', updateEditor);
  $('#edit-rows').addEventListener('click', (e) => {
    const remove = e.target.closest('.remove-holding');
    if (!remove) return;
    remove.closest('.holding-editor-row').remove();
    if (!$('#edit-rows').children.length) holdingRow();
    updateEditor();
    $('#add-holding').focus();
  });
  $('#security-browser').addEventListener('toggle', (e) => { if (e.currentTarget.open) renderSecurities(); });
  $('#security-search').addEventListener('input', renderSecurities);
  $('#security-results').addEventListener('click', (event) => {
    const selection = event.target.closest('[data-security-ticker]');
    if (!selection || selection.disabled) return;
    const blank = $$('.holding-editor-row').find((row) => !$('.edit-ticker',row).value.trim() && !$('.edit-weight',row).value.trim());
    const row = blank || holdingRow();
    $('.edit-ticker',row).value = selection.dataset.securityTicker;
    $('#security-browser').open = false;
    $('.edit-weight',row).focus();
    updateEditor();
  });
  $('#edit-has-order').addEventListener('change', updateEditor);
  $('#edit-order-ticker').addEventListener('input', updateEditor);
  $('#try-order').addEventListener('click', () => {
    if (!canUseOrder()) { openEditor(true); return; }
    state.order = true; render(); jump('risk-review',true);
    announce('Historical results with the simulated order are ready.');
  });
  $('#clear-order').addEventListener('click', () => { state.order = false; render(); jump('risk-review',true); });
  $$('[data-lens]').forEach((button) => button.addEventListener('click', () => { state.lens = button.dataset.lens; renderHoldings(); }));
  $$('[data-holdings-state]').forEach((button) => button.addEventListener('click',() => { state.holdingsState = button.dataset.holdingsState; renderHoldings(); }));
  $('#show-allocation').addEventListener('click',(e) => { e.preventDefault(); jump('portfolio-allocation',true); });
  $$('[data-allocation-view]').forEach((button) => button.addEventListener('click',() => { state.allocationView = button.dataset.allocationView; state.allocationExpanded = false; renderAllocation(); }));
  $$('[data-fund-view]').forEach((button) => button.addEventListener('click', () => { state.fundView = button.dataset.fundView; state.allFunds = false; renderFunds(); }));
  $('#exposure-strip').addEventListener('click', (event) => {
    if (!event.target.closest('[data-company-jump]')) return;
    event.preventDefault();
    state.fundView = 'companies'; state.allFunds = false; renderFunds(); jump('look-through', true);
  });
  $('#explain-button').addEventListener('click', explain);
  $('#explain-result').addEventListener('click', (event) => {
    const link = event.target.closest('[data-explanation-link]');
    const node = link && document.getElementById(`proof-${link.dataset.explanationLink}`);
    if (!node) return;
    node.open = true;
  });
  $$('.primary-nav a').forEach((link) => link.addEventListener('click', () => setNav(link.hash.slice(1))));
  window.addEventListener('hashchange', () => { if ($(`.primary-nav a[href="${window.location.hash.replace(/[^#a-z-]/g,'')}"]`)) setNav(window.location.hash.slice(1)); });
  if (window.location.hash) setNav(window.location.hash.slice(1));

  async function boot() {
    const loadError = $('#load-error');
    try {
      const response = await fetch(endpoint('review-demo.json'));
      if (!response.ok) throw new Error('The saved examples could not be read.');
      const demo = await response.json();
      if (!Array.isArray(demo.examples) || !demo.examples.length) throw new Error('The review lists no saved examples.');
      state.examples = demo.examples.filter((item) => item.input && item.result?.before);
      state.assets = demo.assets || [];
      $('#security-count').textContent = `Browse ${state.assets.length} supported investments`;
      renderMarkup(picker, state.examples.map((item) => `<option value="${esc(item.id)}">${esc(exampleName(item))}</option>`).join('') + '<option value="__own" disabled>Your portfolio / live only</option>');
      renderMarkup($('#asset-list'), state.assets.map((item) => `<option value="${esc(item.ticker)}">${esc(item.name || item.ticker)}</option>`).join(''));
      picker.disabled = false;
      const canReachReview = document.querySelector('meta[name="epicentre-delivery"]')?.content !== 'static';
      await activate(state.examples.find((item) => String(item.id).toLowerCase() === 'robert')?.id || state.examples[0].id,
        canReachReview);
    } catch (error) {
      loadError.textContent = error.message || 'Could not load a review. Refresh to try again.';
      loadError.hidden = false;
      $('#mode-text').textContent = 'Review unavailable';
      renderMarkup($('#holdings'), empty('Review unavailable', 'Refresh this page to try loading the examples again.'));
      $('#risk-result').replaceChildren(); $('#fund-result').replaceChildren(); $('#evidence-list').replaceChildren();
    }
  }
  boot();
}

if (typeof document !== 'undefined') init();
