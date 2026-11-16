import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(new URL('../web/review.js', import.meta.url));
const {parseReviewInput, drawdownSeries, companyExposure, reviewCompanyExposure, matchSecurities, compareAllocation} = await import(`data:text/javascript;base64,${source.toString('base64')}`);

const base = {
  rows: [{ticker:' XBB.TO ', weight:'45'}, {ticker:'XIC.TO', weight:'55'}],
  amount:'600000', limit:'15', capacity:'90000',
  order:{ticker:'nvda', weight:'40', from_ticker:'XBB.TO'},
};

test('converts user-facing percent values and keeps the funding holding', () => {
  assert.deepEqual(parseReviewInput(base), {portfolio:{'XBB.TO':.45, 'XIC.TO':.55}, amount:600000, drawdown_limit:.15, capacity:90000, order:{ticker:'NVDA', weight:.4, from_ticker:'XBB.TO'}});
});

test('rejects unallocated money and repeated tickers instead of normalizing silently', () => {
  assert.throws(() => parseReviewInput({...base, rows:[{ticker:'XIC.TO',weight:'55'}]}), /100%/);
  assert.throws(() => parseReviewInput({...base, rows:[{ticker:'XIC.TO',weight:'45'}, {ticker:'xic.to',weight:'55'}]}), /once/);
});

test('rejects funding an order with more than the chosen holding and supports baseline-only reviews', () => {
  assert.throws(() => parseReviewInput({...base, order:{...base.order, weight:'46'}}), /funding holding/);
  assert.deepEqual(parseReviewInput({...base, order:null, capacity:''}), {portfolio:{'XBB.TO':.45, 'XIC.TO':.55}, amount:600000, drawdown_limit:.15, capacity:null, order:null});
});

test('historical drawdown is relative to the running peak and recovers to zero at new highs', () => {
  const result = drawdownSeries([['2020-01-01',100],['2020-01-02',120],['2020-01-03',90],['2020-01-04',132]]);
  assert.deepEqual(result, [['2020-01-01',0],['2020-01-02',0],['2020-01-03',-.25],['2020-01-04',0]]);
});

test('finds the disclosed company regardless of provider suffix and excludes similarly named issuers', () => {
  const signed = {ticker:'NVDA.US', name:'NVIDIA Corporation', share:.09, direct_share:.07, funds:[{ticker:'VFV.TO',share:.02}]};
  assert.equal(companyExposure([{ticker:'NVDS',name:'Inverse NVIDIA ETF',share:.5}, signed], 'NVDA'), signed);
  assert.equal(companyExposure([], 'NVDA'), null);
});


test('rejects a dollar floor at or above the portfolio and a 100% drawdown tolerance', () => {
  assert.throws(() => parseReviewInput({...base, capacity:'0'}), /positive/);
  assert.throws(() => parseReviewInput({...base, capacity:'600000'}), /below the portfolio value/);
  assert.throws(() => parseReviewInput({...base, limit:'100'}), /less than 100%/);
  assert.equal(parseReviewInput({...base, limit:''}).drawdown_limit, null);
});

test('a company omitted from the ranked results is unknown on that side', () => {
  const result = {
    before:{holdings:[{ticker:'QQQ',weight:1}]},
    after:{holdings:[{ticker:'NVDA',weight:.15},{ticker:'QQQ',weight:.85}]},
    exposure:{before:[{ticker:'FFF',share:.2}],after:[{ticker:'NVDA',share:.21,direct_share:.15,funds:[{ticker:'QQQ',share:.06}]}]},
    funds:[{ticker:'QQQ',asset_class:'etf_equity',company_coverage:.9,companies_listed:25,companies:[],before_weight:1,after_weight:.85}],
  };
  assert.equal(reviewCompanyExposure(result,'before','NVDA').mapped, null);
  assert.equal(reviewCompanyExposure(result,'after','NVDA').mapped, .21);
  assert.equal(reviewCompanyExposure(result,'after','NVDA').complete, false);
});

test('recovers disclosed ETF exposure from underlying rows even when the ranked list omits a company', () => {
  const result = {before:{holdings:[{ticker:'QQQ',weight:.15}]},funds:[{ticker:'QQQ',asset_class:'etf_equity',company_coverage:.5,companies_listed:20,companies:[{ticker:'NVDA.US',share:.065}],before_weight:.15}]};
  const row = reviewCompanyExposure(result,'before','NVDA');
  assert.ok(Math.abs(row.mapped - .00975) < 1e-10);
  assert.deepEqual(row.funds.map(f => f.ticker), ['QQQ']);
  assert.equal(row.complete, false);
});

test('finds a product by its full name, partial ticker, or supported label', () => {
  const assets = [{ticker:'XBB.TO',name:'iShares Core Canadian Universe Bond Index ETF',asset_class:'etf_bond'},{ticker:'BTC-USD',name:'Bitcoin',asset_class:'crypto'}];
  assert.deepEqual(matchSecurities(assets,'canadian bond'), [assets[0]]);
  assert.deepEqual(matchSecurities(assets,'btc'), [assets[1]]);
  assert.deepEqual(matchSecurities(assets,'Bitcoin'), [assets[1]]);
  assert.deepEqual(matchSecurities(assets,'options'), []);
});


test('compares combined direct and ETF exposure without treating missing companies as zero', () => {
  const result = {
    allocation:{before:{equity_company_coverage:.7},after:{equity_company_coverage:1}},
    exposure:{before:[{name:'Apple',ticker:'AAPL',share:.06,direct_share:.05}],
      after:[{name:'NVIDIA',ticker:'NVDA.US',share:.24,direct_share:.20},{name:'Apple',ticker:'AAPL.US',share:.03,direct_share:.02}]},
  };
  const rows = compareAllocation(result, 'companies');
  assert.deepEqual(rows.map(({name,before,after}) => [name,before?.share,after?.share]), [['NVIDIA',undefined,.24],['Apple',.06,.03]]);
});

test('retains unmapped equity at its known whole-portfolio weight', () => {
  const result = {allocation:{before:{industries:[{name:'Bonds',share:.6},{name:'Unmapped equity',share:.4}]},after:{industries:[{name:'Bonds',share:.4},{name:'Unmapped equity',share:.2},{name:'Technology',share:.4}]}}};
  const unknown = compareAllocation(result,'industries').find((row) => row.name === 'Unmapped equity');
  assert.deepEqual([unknown.before.share,unknown.after.share],[.4,.2]);
});
