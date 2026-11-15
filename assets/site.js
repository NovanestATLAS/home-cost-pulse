/* Home Cost Pulse - page behaviour: calculators, state picker, sortable tables. No dependencies. */
(function () {
  'use strict';

  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var DATA = null;
  var dataEl = document.getElementById('hcp-data');
  if (dataEl) { try { DATA = JSON.parse(dataEl.textContent); } catch (e) { DATA = null; } }

  /* ---------- calculators ---------- */
  var C = window.HCPCalc;

  function roundFor(kind, n) {
    var d = kind === 'coverage' ? 1 : 2;
    var f = Math.pow(10, d);
    return Math.round(n * f) / f;
  }

  function readValues(form, units) {
    var v = {};
    $$('input, select', form).forEach(function (inp) {
      if (!inp.name || inp.name === 'units') return;
      if (inp.type === 'checkbox') { v[inp.name] = inp.checked; return; }
      if (inp.tagName === 'SELECT') { v[inp.name] = inp.value; return; }
      var n = parseFloat(inp.value);
      if (!isFinite(n)) n = 0;
      var kind = inp.getAttribute('data-kind');
      v[inp.name] = kind ? C.toUS(kind, n, units) : n;
    });
    return v;
  }

  function render(box, r) {
    var html = '<dl class="lines">';
    r.lines.forEach(function (l) { html += '<div class="line"><dt>' + esc(l[0]) + '</dt><dd>' + esc(l[1]) + '</dd></div>'; });
    html += '</dl><p class="total"><span>' + esc(r.total[0]) + '</span><strong>' + esc(r.total[1]) + '</strong></p>';
    if (r.extra && r.extra.length) {
      html += '<dl class="lines extra">';
      r.extra.forEach(function (l) { html += '<div class="line"><dt>' + esc(l[0]) + '</dt><dd>' + esc(l[1]) + '</dd></div>'; });
      html += '</dl>';
    }
    (r.notes || []).forEach(function (n) { html += '<p class="note">' + esc(n) + '</p>'; });
    box.innerHTML = html;
  }

  function setUnits(form, next) {
    var prev = form.getAttribute('data-units') || 'us';
    if (prev !== next) {
      $$('input[data-kind]', form).forEach(function (inp) {
        var kind = inp.getAttribute('data-kind');
        var n = parseFloat(inp.value);
        if (!isFinite(n)) return;
        inp.value = roundFor(kind, C.fromUS(kind, C.toUS(kind, n, prev), next));
      });
    }
    $$('.unit[data-kind]', form).forEach(function (s) { s.textContent = C.unitLabel(s.getAttribute('data-kind'), next); });
    form.setAttribute('data-units', next);
  }

  function applyState(form, code) {
    if (!DATA || !DATA[code]) return;
    var s = DATA[code];
    $$('[data-bind]', form).forEach(function (inp) {
      var val = s[inp.getAttribute('data-bind')];
      if (val === null || val === undefined) val = inp.getAttribute('data-default');
      if (val !== null && val !== undefined && val !== '') inp.value = val;
    });
  }

  function initCalc(form) {
    var id = form.getAttribute('data-calc');
    var box = document.querySelector('[data-receipt-for="' + id + '"]');
    if (!C || !box) return;
    var params = new URLSearchParams(window.location.search);

    function update() {
      var units = form.getAttribute('data-units') || 'us';
      try { render(box, C.compute(id, readValues(form, units), units)); } catch (e) { /* keep last result */ }
    }

    $$('select[data-sets]', form).forEach(function (sel) {
      sel.addEventListener('change', function () {
        if (sel.value === 'custom') return;
        var target = form.elements[sel.getAttribute('data-sets')];
        if (!target) return;
        var kind = target.getAttribute('data-kind');
        var n = parseFloat(sel.value);
        target.value = kind ? roundFor(kind, C.fromUS(kind, n, form.getAttribute('data-units') || 'us')) : n;
      });
    });

    var stateSel = form.querySelector('select[data-role="state"]');
    if (stateSel) {
      var q = (params.get('state') || '').toUpperCase();
      if (q && DATA && DATA[q]) stateSel.value = q;
      applyState(form, stateSel.value);
      stateSel.addEventListener('change', function () { applyState(form, stateSel.value); });
    }

    var unitsSel = form.elements.units;
    if (unitsSel) {
      form.setAttribute('data-units', 'us');
      if (params.get('units') === 'metric') unitsSel.value = 'metric';
      setUnits(form, unitsSel.value);
      unitsSel.addEventListener('change', function () { setUnits(form, unitsSel.value); });
    }

    form.addEventListener('input', update);
    form.addEventListener('change', update);
    form.addEventListener('submit', function (e) { e.preventDefault(); update(); });
    update();
  }

  $$('form.calc').forEach(initCalc);

  /* ---------- state picker (home page) ---------- */
  var picker = document.getElementById('state-picker');
  if (picker) {
    picker.addEventListener('submit', function (e) {
      var sel = picker.querySelector('select');
      if (sel && sel.value) { e.preventDefault(); window.location.href = sel.value; }
    });
  }

  /* ---------- sortable tables ---------- */
  $$('table[data-sortable]').forEach(function (table) {
    var tbody = table.tBodies[0];
    $$('th[data-sort] button', table).forEach(function (btn) {
      btn.addEventListener('click', function () {
        var th = btn.parentNode;
        var idx = Array.prototype.indexOf.call(th.parentNode.children, th);
        var numeric = th.getAttribute('data-sort') === 'num';
        var dir = th.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
        $$('th[data-sort]', table).forEach(function (h) { h.removeAttribute('aria-sort'); });
        th.setAttribute('aria-sort', dir);
        var rows = Array.prototype.slice.call(tbody.rows);
        rows.sort(function (a, b) {
          var x = a.cells[idx].getAttribute('data-v'), y = b.cells[idx].getAttribute('data-v');
          var cmp;
          if (numeric) {
            var nx = parseFloat(x), ny = parseFloat(y);
            if (!isFinite(nx)) nx = -Infinity;
            if (!isFinite(ny)) ny = -Infinity;
            cmp = nx - ny;
          } else {
            cmp = String(x).localeCompare(String(y));
          }
          return dir === 'ascending' ? cmp : -cmp;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });

  /* ---------- contact form (sent in the background; falls back to a normal form post) ---------- */
  $$('form[data-contact-form]').forEach(function (form) {
    var status = form.querySelector('[data-contact-status]');
    var btn = form.querySelector('button[type="submit"]');
    form.addEventListener('submit', function (e) {
      if (!window.fetch || !window.FormData) return;
      e.preventDefault();
      var data = {};
      new FormData(form).forEach(function (v, k) { data[k] = v; });
      if (data.botcheck) return;
      btn.disabled = true;
      status.className = 'cf-status';
      status.textContent = 'Sending...';
      fetch(form.action, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(data)
      }).then(function (r) { return r.json(); }).then(function (res) {
        if (!res || !res.success) throw new Error('not sent');
        form.reset();
        status.className = 'cf-status ok';
        status.textContent = 'Message sent. Thank you.';
      }).catch(function () {
        status.className = 'cf-status err';
        status.textContent = 'The message was not sent. Check your connection and try again.';
      }).then(function () { btn.disabled = false; });
    });
  });
})();
