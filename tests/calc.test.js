// Run with: node --test tests/
// Checks the calculator math against hand-worked answers (the same ones quoted in the FAQs).
const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('../assets/calc-core.js');

const close = (a, b, tol = 0.01) => assert.ok(Math.abs(a - b) <= tol, `${a} != ${b}`);

test('electric bill: 869 kWh at 18.31¢ + $0', () => {
  const r = C.compute('electric-bill', { kwh: 869, price: 18.31, fixed: 0 }).raw;
  close(r.monthly, 159.11, 0.01);
  close(r.yearly, 1909.35, 0.05);
});

test('electric bill: fixed charge changes the all-in price', () => {
  const r = C.compute('electric-bill', { kwh: 1000, price: 15, fixed: 20 }).raw;
  close(r.monthly, 170);
  close(r.effective, 17);
});

test('appliance: 1,500 W space heater at 18¢ costs 27¢ an hour', () => {
  const r = C.compute('appliance-energy-cost', { watts: 1500, hours: 8, days: 30, price: 18 }).raw;
  close(r.perHour, 0.27);
  close(r.kwhMonth, 360);
  close(r.perMonth, 64.8);
});

test('EV: 100 miles at 3.5 mi/kWh with 10% losses needs 31.75 kWh', () => {
  const r = C.compute('ev-charging-cost', { miles: 100, efficiency: 3.5, loss: 10, price: 18, mpg: 30, gas: 3.5 }).raw;
  close(r.kwh, 31.746, 0.001);
  close(r.ev, 5.714, 0.001);
  close(r.gas, 11.667, 0.001);
});

test('solar: flat prices, no degradation gives cost / yearly savings', () => {
  // 5 kW × $2/W = $10,000; 5 × 1,000 kWh = 5,000 kWh × 20¢ = $1,000/yr → 10.0 years
  const r = C.compute('solar-payback', { size: 5, cost_per_watt: 2, incentives: 0, production: 1000, price: 20, credit_share: 100, escalation: 0, degradation: 0 }).raw;
  close(r.cost, 10000);
  close(r.first, 1000);
  close(r.payback, 10, 1e-9);
  close(r.total, 25000);
});

test('solar: never pays back is reported, not crashed', () => {
  const r = C.compute('solar-payback', { size: 5, cost_per_watt: 50, incentives: 0, production: 1000, price: 10, credit_share: 100, escalation: 0, degradation: 0.5 });
  assert.equal(r.total[1], 'Not within 25 years');
});

test('concrete: 10 × 10 × 4 in with 10% extra = 1.36 yd³ and 62 bags of 80 lb', () => {
  const r = C.compute('concrete', { length: 10, width: 10, thickness: 4, waste: 10 }).raw;
  close(r.yd3, 1.358, 0.001);
  assert.equal(r.bags80, 62);
});

test('concrete: exactly 45 bags of 80 lb per cubic yard', () => {
  const r = C.compute('concrete', { length: 27, width: 1, thickness: 12, waste: 0 }).raw;
  assert.equal(r.bags80, 45);
});

test('gravel: 20 × 10 × 3 in with 5% extra', () => {
  const r = C.compute('gravel-mulch', { length: 20, width: 10, depth: 3, density: 1.4, waste: 5 }).raw;
  close(r.ft3, 52.5);
  close(r.yd3, 1.944, 0.001);
  close(r.tons, 2.722, 0.001);
});

test('paint: 12 × 12 room, 8 ft, 1 door, 2 windows, 2 coats = 1.91 gal', () => {
  const r = C.compute('paint', { length: 12, width: 12, height: 8, doors: 1, windows: 2, coats: 2, coverage: 350, ceiling: false }).raw;
  close(r.area, 334);
  close(r.gallons, 1.909, 0.001);
});

test('drywall: 12 × 12 room with ceiling = 19 sheets of 4 × 8', () => {
  const r = C.compute('drywall', { length: 12, width: 12, height: 8, sheet: '32', waste: 10, ceiling: true }).raw;
  close(r.area, 528);
  assert.equal(r.sheets, 19);
});

test('flooring: 12 × 10 with 10% extra and 20 ft² boxes = 7 boxes', () => {
  const r = C.compute('flooring-tile', { length: 12, width: 10, waste: 10, box: 20 }).raw;
  assert.equal(r.boxes, 7);
});

test('roofing: 40 × 30 at 6/12 with 10% extra = 45 bundles', () => {
  const r = C.compute('roofing', { length: 40, width: 30, pitch: 6, waste: 10 }).raw;
  close(r.factor, 1.118, 0.001);
  close(r.roof, 1341.6, 0.1);
  assert.equal(r.bundles, 45);
});

test('metric round trip: 3 m is about 9.84 ft and back', () => {
  const ft = C.toUS('length', 3, 'metric');
  close(ft, 9.8425, 0.001);
  close(C.fromUS('length', ft, 'metric'), 3, 1e-9);
});

test('metric concrete matches U.S. volume', () => {
  const us = C.compute('concrete', { length: 10, width: 10, thickness: 4, waste: 0 }, 'us').raw;
  const m = C.compute('concrete', { length: 10, width: 10, thickness: 4, waste: 0 }, 'metric').raw;
  close(m.m3, us.ft3 * 0.0283168, 1e-6);
});
