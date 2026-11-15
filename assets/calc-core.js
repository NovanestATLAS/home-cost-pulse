/*
 * Home Cost Pulse - calculator math.
 * Single source of truth: the browser uses it through site.js, and the build uses it
 * through scripts/calc_examples.js to write the worked examples on each page.
 * All inputs arrive in U.S. units (ft, in, ft², ft²/gal, short tons/yd³, price per yd³ / ft² / gal);
 * outputs are converted for display when units === 'metric'.
 * Prices are optional and always typed by the visitor: the site never guesses a material price.
 */
(function (root) {
  'use strict';

  var cache = {};
  function nf(d) {
    if (!cache[d]) cache[d] = new Intl.NumberFormat('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
    return cache[d];
  }
  function num(n, d) { return isFinite(n) ? nf(d || 0).format(n) : '-'; }
  function money(n) { if (!isFinite(n)) return '-'; return (n < 0 ? '-$' : '$') + nf(2).format(Math.abs(n)); }
  function money0(n) { if (!isFinite(n)) return '-'; return (n < 0 ? '-$' : '$') + nf(0).format(Math.abs(n)); }
  function cents(n) { return isFinite(n) ? nf(2).format(n) + '¢' : '-'; }
  function pos(n) { return isFinite(n) && n > 0 ? n : 0; }

  // metric value × TO_US[kind] = U.S. value
  // A price per m³, m² or litre is smaller than the same price per yd³, ft² or gallon.
  var TO_US = { length: 3.28084, small: 1 / 2.54, area: 10.7639, coverage: 40.7458, density: 1 / 1.18655,
                price_volume: 0.764555, price_area: 0.092903, price_liquid: 3.78541 };
  var UNIT_LABEL = {
    us: { length: 'ft', small: 'in', area: 'ft²', coverage: 'ft²/gal', density: 'tons/yd³',
          price_volume: '$ per yd³', price_area: '$ per ft²', price_liquid: '$ per gal' },
    metric: { length: 'm', small: 'cm', area: 'm²', coverage: 'm²/L', density: 't/m³',
              price_volume: 'per m³', price_area: 'per m²', price_liquid: 'per L' }
  };
  var FT3_M3 = 0.0283168, FT2_M2 = 0.092903, TON_T = 0.907185, GAL_L = 3.78541;

  function toUS(kind, value, units) { return (units === 'metric' && TO_US[kind]) ? value * TO_US[kind] : value; }
  function fromUS(kind, value, units) { return (units === 'metric' && TO_US[kind]) ? value / TO_US[kind] : value; }
  // Costs: dollars in U.S. mode; a plain amount in metric mode, because the visitor's currency is unknown.
  function cur(n, units) { return units === 'metric' ? num(n, 2) : money(n); }
  var COST_NOTE = 'Material only, at the price you entered. Labor, delivery, tax and tools are extra.';
  function area(ft2, units, d) { return units === 'metric' ? num(ft2 * FT2_M2, d === undefined ? 1 : d) + ' m²' : num(ft2, d || 0) + ' ft²'; }

  var calcs = {};

  calcs['electric-bill'] = function (v) {
    var kwh = pos(v.kwh), price = pos(v.price), fixed = pos(v.fixed);
    var energy = kwh * price / 100;
    var monthly = energy + fixed;
    var eff = kwh > 0 ? monthly / kwh * 100 : NaN;
    return {
      lines: [
        ['Energy: ' + num(kwh) + ' kWh × ' + cents(price), money(energy)],
        ['Fixed monthly charge', money(fixed)]
      ],
      total: ['Estimated monthly bill', money(monthly)],
      extra: [['Per year', money(monthly * 12)], ['Your all-in price', cents(eff) + ' per kWh']],
      raw: { energy: energy, monthly: monthly, yearly: monthly * 12, effective: eff }
    };
  };

  calcs['appliance-energy-cost'] = function (v) {
    var kw = pos(v.watts) / 1000, hours = pos(v.hours), days = pos(v.days), price = pos(v.price);
    var perHour = kw * price / 100;
    var perDay = perHour * hours;
    var kwhMonth = kw * hours * days;
    var perMonth = kwhMonth * price / 100;
    return {
      lines: [
        ['Per hour of use', money(perHour)],
        ['Per day (' + num(hours, hours % 1 ? 2 : 0) + ' h)', money(perDay)],
        ['Energy per month', num(kwhMonth, 1) + ' kWh']
      ],
      total: ['Per month', money(perMonth)],
      extra: [['Per year', money(perMonth * 12)]],
      raw: { perHour: perHour, perDay: perDay, kwhMonth: kwhMonth, perMonth: perMonth }
    };
  };

  calcs['ev-charging-cost'] = function (v) {
    var miles = pos(v.miles), eff = pos(v.efficiency), loss = Math.min(pos(v.loss), 90) / 100;
    var price = pos(v.price), mpg = pos(v.mpg), gas = pos(v.gas);
    var kwh = eff > 0 ? miles / eff / (1 - loss) : NaN;
    var ev = kwh * price / 100;
    var per100 = miles > 0 ? ev / miles * 100 : NaN;
    var gasCost = mpg > 0 ? miles / mpg * gas : NaN;
    var diff = gasCost - ev;
    return {
      lines: [
        ['Electricity from the outlet', num(kwh, 1) + ' kWh'],
        ['Charging cost per 100 miles', money(per100)],
        ['Gas car for the same miles', money(gasCost)]
      ],
      total: ['Home charging per month', money(ev)],
      extra: [
        [diff >= 0 ? 'You save vs gas, per month' : 'Costs more than gas, per month', money(Math.abs(diff))],
        [diff >= 0 ? 'Savings per year' : 'Extra per year', money(Math.abs(diff) * 12)]
      ],
      raw: { kwh: kwh, ev: ev, per100: per100, gas: gasCost, diff: diff }
    };
  };

  calcs['solar-payback'] = function (v) {
    var size = pos(v.size), cpw = pos(v.cost_per_watt), inc = pos(v.incentives);
    var perKw = pos(v.production), price = pos(v.price);
    var share = Math.min(pos(v.credit_share), 100) / 100;
    var esc = (isFinite(v.escalation) ? v.escalation : 0) / 100;
    var deg = Math.min(pos(v.degradation), 50) / 100;
    var years = 25;
    var cost = Math.max(size * 1000 * cpw - inc, 0);
    var out1 = size * perKw;
    var cum = 0, payback = null, first = 0;
    for (var y = 1; y <= years; y++) {
      var out = out1 * Math.pow(1 - deg, y - 1);
      var p = price * Math.pow(1 + esc, y - 1);
      var save = out * p / 100 * share;
      if (y === 1) first = save;
      if (payback === null && save > 0 && cum + save >= cost) payback = (y - 1) + (cost - cum) / save;
      cum += save;
    }
    return {
      lines: [
        ['System cost after rebates', money0(cost)],
        ['Output in year one', num(out1) + ' kWh'],
        ['Savings in year one', money0(first)]
      ],
      total: ['Payback', payback === null ? 'Not within 25 years' : num(payback, 1) + ' years'],
      extra: [['Savings over 25 years', money0(cum)], ['Net of the system cost', money0(cum - cost)]],
      notes: ['No federal tax credit is included: the 30% residential credit (Section 25D) ended on December 31, 2025.'],
      raw: { cost: cost, out1: out1, first: first, payback: payback, total: cum, net: cum - cost }
    };
  };

  calcs['concrete'] = function (v, units) {
    var ft3 = pos(v.length) * pos(v.width) * pos(v.thickness) / 12 * (1 + pos(v.waste) / 100);
    var yd3 = ft3 / 27;
    var readyMix = yd3 * pos(v.price_yard);   // price_yard arrives as a price per yd³ in both unit systems
    var extra = [], notes = [];
    if (units === 'metric') {
      if (readyMix > 0) { extra.push(['Ready-mix cost', cur(readyMix, units)]); notes.push(COST_NOTE); }
      notes.push('Bag yields vary by brand and size; divide the volume by the yield printed on the bag.');
      return {
        lines: [['Volume with extra', num(ft3 * FT3_M3, 2) + ' m³']],
        total: ['Concrete needed', num(ft3 * FT3_M3, 2) + ' m³'],
        extra: extra, notes: notes,
        raw: { ft3: ft3, m3: ft3 * FT3_M3, readyMix: readyMix }
      };
    }
    var bags80 = Math.ceil(ft3 / 0.6 - 1e-9);
    var bagCost = bags80 * pos(v.price_bag);
    if (readyMix > 0) extra.push(['Ready-mix cost (' + num(yd3, 2) + ' yd³)', money(readyMix)]);
    if (bagCost > 0) extra.push(['Bag cost (' + num(bags80) + ' × 80 lb)', money(bagCost)]);
    if (extra.length) notes.push(COST_NOTE);
    return {
      lines: [
        ['Volume with extra', num(ft3, 1) + ' ft³'],
        ['80 lb bags (0.60 ft³ each)', num(bags80)],
        ['60 lb bags (0.45 ft³ each)', num(Math.ceil(ft3 / 0.45 - 1e-9))],
        ['40 lb bags (0.30 ft³ each)', num(Math.ceil(ft3 / 0.3 - 1e-9))]
      ],
      total: ['Concrete needed', num(yd3, 2) + ' yd³'],
      extra: extra, notes: notes,
      raw: { ft3: ft3, yd3: yd3, bags80: bags80, readyMix: readyMix, bagCost: bagCost }
    };
  };

  calcs['gravel-mulch'] = function (v, units) {
    var ft3 = pos(v.length) * pos(v.width) * pos(v.depth) / 12 * (1 + pos(v.waste) / 100);
    var yd3 = ft3 / 27;
    var tons = yd3 * pos(v.density);
    var lines = [];
    var cost = yd3 * pos(v.price_yard);
    var extra = cost > 0 ? [['Material cost', cur(cost, units)]] : [];
    var notes = cost > 0 ? [COST_NOTE] : [];
    if (units === 'metric') {
      if (tons > 0) lines.push(['Weight', num(tons * TON_T, 2) + ' tonnes']);
      return { lines: lines, total: ['Volume with extra', num(ft3 * FT3_M3, 2) + ' m³'], extra: extra, notes: notes, raw: { ft3: ft3, tons: tons, cost: cost } };
    }
    lines.push(['Volume with extra', num(ft3, 1) + ' ft³']);
    if (tons > 0) lines.push(['Weight', num(tons, 2) + ' tons']);
    lines.push(['2 ft³ bags', num(Math.ceil(ft3 / 2 - 1e-9))]);
    return { lines: lines, total: ['You need', num(yd3, 2) + ' yd³'], extra: extra, notes: notes, raw: { ft3: ft3, yd3: yd3, tons: tons, cost: cost } };
  };

  calcs['paint'] = function (v, units) {
    var L = pos(v.length), W = pos(v.width), H = pos(v.height);
    var wall = 2 * (L + W) * H;
    var openings = pos(v.doors) * 20 + pos(v.windows) * 15;
    var ceiling = v.ceiling ? L * W : 0;
    var paintArea = Math.max(wall - openings, 0) + ceiling;
    var coats = Math.max(Math.round(pos(v.coats)), 1);
    var cov = pos(v.coverage);
    var gal = cov > 0 ? paintArea * coats / cov : NaN;
    var lines = [['Wall area', area(wall, units)], ['Doors and windows', '−' + area(openings, units)]];
    if (ceiling) lines.push(['Ceiling', area(ceiling, units)]);
    lines.push(['Area to paint × ' + coats + (coats === 1 ? ' coat' : ' coats'), area(paintArea * coats, units)]);
    var perGal = pos(v.price_gal);   // price per gallon in both unit systems
    if (units === 'metric') {
      var liters = gal * GAL_L, buyL = Math.ceil(liters - 1e-9);
      var extraM = [['Buy at least', num(buyL) + ' L']];
      var costM = buyL * perGal / GAL_L;
      if (costM > 0) extraM.push(['Paint cost (' + num(buyL) + ' L)', cur(costM, units)]);
      return { lines: lines, total: ['Paint needed', num(liters, 1) + ' L'], extra: extraM, notes: costM > 0 ? [COST_NOTE] : [], raw: { area: paintArea, liters: liters, cost: costM } };
    }
    var buy = Math.ceil(gal - 1e-9);
    var extra = [['Buy', num(buy) + ' gallon' + (buy === 1 ? '' : 's')]];
    var cost = buy * perGal;
    if (cost > 0) extra.push(['Paint cost (' + num(buy) + ' gal)', money(cost)]);
    return { lines: lines, total: ['Paint needed', num(gal, 2) + ' gal'], extra: extra, notes: cost > 0 ? [COST_NOTE] : [], raw: { area: paintArea, gallons: gal, cost: cost } };
  };

  calcs['drywall'] = function (v, units) {
    var L = pos(v.length), W = pos(v.width), H = pos(v.height);
    var boardArea = 2 * (L + W) * H + (v.ceiling ? L * W : 0);
    var withExtra = boardArea * (1 + pos(v.waste) / 100);
    var sheetArea = pos(parseFloat(v.sheet)) || 32;
    var sheets = Math.ceil(withExtra / sheetArea - 1e-9);
    var sheetCost = sheets * pos(v.price_sheet);
    return {
      lines: [
        ['Board area', area(boardArea, units)],
        ['With extra', area(withExtra, units)],
        ['Screws (about 1 per ft²)', num(Math.ceil(withExtra / 10 - 1e-9) * 10)]
      ],
      total: ['Sheets', num(sheets)],
      extra: sheetCost > 0 ? [['Sheet cost (' + num(sheets) + ' sheets)', cur(sheetCost, units)]] : [],
      notes: sheetCost > 0 ? [COST_NOTE] : [],
      raw: { area: boardArea, withExtra: withExtra, sheets: sheets, cost: sheetCost }
    };
  };

  calcs['flooring-tile'] = function (v, units) {
    var floor = pos(v.length) * pos(v.width);
    var need = floor * (1 + pos(v.waste) / 100);
    var box = pos(v.box);
    var boxes = box > 0 ? Math.ceil(need / box - 1e-9) : NaN;
    var bought = box > 0 ? boxes * box : need;            // you pay for whole boxes
    var cost = bought * pos(v.price_area);                // price_area arrives as a price per ft²
    return {
      lines: [['Floor area', area(floor, units)], ['With extra for cuts', area(need, units)]],
      total: ['Boxes to buy', num(boxes)],
      extra: cost > 0 ? [['Flooring cost (' + area(bought, units) + ')', cur(cost, units)]] : [],
      notes: cost > 0 ? [COST_NOTE] : [],
      raw: { floor: floor, need: need, boxes: boxes, bought: bought, cost: cost }
    };
  };

  calcs['roofing'] = function (v, units) {
    var factor = Math.sqrt(1 + Math.pow(pos(v.pitch) / 12, 2));
    var roof = pos(v.length) * pos(v.width) * factor;
    var withExtra = roof * (1 + pos(v.waste) / 100);
    var squares = withExtra / 100;
    var lines = [['Pitch factor', num(factor, 3)], ['Roof area', area(roof, units)], ['With extra', area(withExtra, units)]];
    if (units === 'metric') {
      var costM = withExtra * FT2_M2 * pos(v.price_m2);   // typed per m², used as is
      var notesM = ['Divide this area by the coverage printed on each pack of roofing.'];
      if (costM > 0) notesM.unshift(COST_NOTE);
      return { lines: lines, total: ['Roof area to cover', area(withExtra, units)],
               extra: costM > 0 ? [['Roofing material cost', cur(costM, units)]] : [], notes: notesM,
               raw: { roof: roof, withExtra: withExtra, cost: costM } };
    }
    lines.push(['Squares (100 ft² each)', num(squares, 1)]);
    var bundles = Math.ceil(squares * 3 - 1e-9);
    var cost = bundles * pos(v.price_bundle);
    return { lines: lines, total: ['Shingle bundles (3 per square)', num(bundles)],
             extra: cost > 0 ? [['Shingle cost (' + num(bundles) + ' bundles)', money(cost)]] : [],
             notes: cost > 0 ? [COST_NOTE] : [],
             raw: { factor: factor, roof: roof, squares: squares, bundles: bundles, cost: cost } };
  };

  var api = {
    calcs: calcs,
    compute: function (id, values, units) {
      var fn = calcs[id];
      if (!fn) throw new Error('Unknown calculator: ' + id);
      return fn(values, units === 'metric' ? 'metric' : 'us');
    },
    toUS: toUS,
    fromUS: fromUS,
    unitLabel: function (kind, units) { return (UNIT_LABEL[units === 'metric' ? 'metric' : 'us'] || {})[kind] || ''; },
    format: { num: num, money: money, money0: money0, cents: cents }
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.HCPCalc = api;
})(typeof self !== 'undefined' ? self : this);
