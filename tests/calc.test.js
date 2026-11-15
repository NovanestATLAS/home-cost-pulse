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

// ---- optional prices: the visitor types a price and gets a material cost ----

test('no price typed means no cost line', () => {
  for (const id of ['concrete', 'gravel-mulch', 'drywall', 'flooring-tile', 'roofing']) {
    const r = C.compute(id, { length: 10, width: 10, thickness: 4, depth: 3, height: 8, pitch: 6, waste: 10, box: 20, density: 1.4, sheet: '32' });
    assert.deepEqual(r.extra || [], [], id);
  }
});

test('concrete cost: 1.358 yd³ at $170 = $230.86; 62 bags at $6.50 = $403', () => {
  const r = C.compute('concrete', { length: 10, width: 10, thickness: 4, waste: 10, price_yard: 170, price_bag: 6.5 }).raw;
  close(r.readyMix, 230.86, 0.01);
  assert.equal(r.bagCost, 403);
});

test('gravel cost: 20 × 10 × 3 in with 5% extra = 1.944 yd³, at $45 = $87.50', () => {
  const r = C.compute('gravel-mulch', { length: 20, width: 10, depth: 3, waste: 5, density: 1.4, price_yard: 45 }).raw;
  close(r.yd3, 1.9444, 0.001);
  close(r.cost, 87.5, 0.01);
});

test('paint cost: 1.91 gal means buying 2 gallons, at $40 = $80', () => {
  const r = C.compute('paint', { length: 12, width: 12, height: 8, doors: 1, windows: 2, coats: 2, coverage: 350, price_gal: 40 }).raw;
  assert.equal(r.cost, 80);
});

test('drywall cost: sheets × price per sheet', () => {
  const r = C.compute('drywall', { length: 12, width: 12, height: 8, sheet: '32', waste: 10, ceiling: true, price_sheet: 15 }).raw;
  assert.equal(r.cost, r.sheets * 15);
});

test('flooring cost uses whole boxes: 7 boxes × 20 ft² × $3 = $420', () => {
  const r = C.compute('flooring-tile', { length: 12, width: 10, waste: 10, box: 20, price_area: 3 }).raw;
  assert.equal(r.bought, 140);
  assert.equal(r.cost, 420);
});

test('roofing cost: 45 bundles at $38 = $1,710', () => {
  const r = C.compute('roofing', { length: 40, width: 30, pitch: 6, waste: 10, price_bundle: 38 }).raw;
  assert.equal(r.cost, 1710);
});

test('metric prices convert: 10 per litre is 37.85 per gallon; 222.35 per m³ is 170 per yd³', () => {
  close(C.toUS('price_liquid', 10, 'metric'), 37.8541, 1e-4);
  close(C.toUS('price_volume', 222.35, 'metric'), 170, 0.01);
  close(C.toUS('price_area', 32.29, 'metric'), 3, 0.001);
});

test('metric paint cost: 8 L at 10 per litre = 80, shown without a currency sign', () => {
  const r = C.compute('paint', { length: 12, width: 12, height: 8, doors: 1, windows: 2, coats: 2, coverage: 350,
                                 price_gal: C.toUS('price_liquid', 10, 'metric') }, 'metric');
  close(r.raw.cost, 80, 1e-6);
  assert.deepEqual(r.extra[1], ['Paint cost (8 L)', '80.00']);
});

test('metric roofing cost: area in m² × price per m²', () => {
  const r = C.compute('roofing', { length: 40, width: 30, pitch: 6, waste: 10, price_m2: 12 }, 'metric').raw;
  close(r.cost, r.withExtra * 0.092903 * 12, 1e-6);
});
