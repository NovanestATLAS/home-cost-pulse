#!/usr/bin/env node
// Reads {"jobs":[{"id":..., "units":"us", "values":{...}}]} on stdin and prints the results
// from assets/calc-core.js, so the worked examples on each page use exactly the browser's math.
const path = require('path');
const C = require(path.join(__dirname, '..', 'assets', 'calc-core.js'));

let input = '';
process.stdin.on('data', (d) => { input += d; });
process.stdin.on('end', () => {
  const { jobs } = JSON.parse(input);
  const out = {};
  for (const job of jobs) {
    try {
      const r = C.compute(job.id, job.values, job.units);
      out[job.id] = { lines: r.lines, total: r.total, extra: r.extra || [], notes: r.notes || [] };
    } catch (e) {
      out[job.id] = { error: String(e) };
    }
  }
  process.stdout.write(JSON.stringify(out));
});
