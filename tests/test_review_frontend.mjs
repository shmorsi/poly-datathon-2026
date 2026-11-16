import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(new URL('../web/review.js', import.meta.url));
const {parseReviewInput, drawdownSeries, companyExposure} = await import(`data:text/javascript;base64,${source.toString('base64')}`);

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
