// Import wizard. All file data is rendered with textContent (never innerHTML).
(() => {
    const $ = (id) => document.getElementById(id);
    const fileInput = $('fileInput');
    const dropzone = $('dropzone');
    const apiKeyInput = $('apiKey');
    const KEY_STORE = 'attendance_api_key';
    const SHAPE_FIELDS = {
        punch_log: ['employee_code', 'name', 'punch_datetime', 'date', 'time', 'status', 'day_status',
            'record_no', 'device_no', 'action', 'apb', 'job_code'],
        daily: ['employee_code', 'name', 'date', 'time_in', 'time_out', 'day_status', 'status',
            'record_no', 'device_no', 'action', 'apb', 'job_code'],
        monthly_matrix: ['employee_code', 'name', 'record_no', 'device_no'],
    };

    let fields = {};
    let analysis = null;   // last reply from /import/analyze
    let targets = {};      // column name -> chosen target
    let aiMarked = new Set();
    let profiles = [];
    let lastErrors = [];
    let busy = false;
    let analyzeRequest = 0;
    let aiStatusRequest = 0;

    if (apiKeyInput) {
        try { apiKeyInput.value = sessionStorage.getItem(KEY_STORE) || ''; } catch (_) { /* storage blocked */ }
    }

    const formatSize = (bytes) => {
        if (!bytes) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB'];
        const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
        return `${(bytes / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`;
    };

    const setStatus = (el, text, isError = false) => {
        el.textContent = text;
        el.classList.toggle('error', isError);
    };

    function headers(json) {
        const h = json ? { 'Content-Type': 'application/json' } : {};
        if (apiKeyInput && apiKeyInput.value) {
            h['X-API-Key'] = apiKeyInput.value;
            try { sessionStorage.setItem(KEY_STORE, apiKeyInput.value); } catch (_) { /* ignore */ }
        }
        return h;
    }

    async function api(path, options = {}) {
        const res = await fetch(path, options);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            const detail = typeof data.detail === 'string' ? data.detail
                : Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join('; ')
                : `Server returned ${res.status}`;
            throw new Error(res.status === 401 ? 'API key is missing or wrong.' : detail);
        }
        return data;
    }

    function cell(tag, text, cls) {
        const el = document.createElement(tag);
        el.textContent = text == null ? '' : String(text);
        if (cls) el.className = cls;
        return el;
    }

    function fillTable(table, heads, rows) {
        table.replaceChildren();
        const thead = document.createElement('thead');
        const hr = document.createElement('tr');
        heads.forEach((h) => hr.appendChild(cell('th', h)));
        thead.appendChild(hr);
        const tbody = document.createElement('tbody');
        rows.forEach((r) => {
            const tr = document.createElement('tr');
            r.forEach((v) => tr.appendChild(v instanceof HTMLElement ? v : cell('td', v)));
            tbody.appendChild(tr);
        });
        table.append(thead, tbody);
    }

    // ---------- step 1: file ----------
    function resetWizard() {
        analyzeRequest += 1; // whatever was still loading no longer applies
        analysis = null;
        targets = {};
        aiMarked = new Set();
        $('mapCard').hidden = true;
        $('resultCard').hidden = true;
        setStatus($('mapStatus'), '');
    }

    async function onFileChosen() {
        resetWizard();
        const file = fileInput.files[0];
        const ok = !!file && /\.(xlsx|xls|csv)$/i.test(file.name);
        $('dzTitle').textContent = file ? file.name : 'Drop a file here or click to browse';
        $('dzSub').textContent = file ? formatSize(file.size) : '.xlsx, .xls or .csv';
        if (!file) { setStatus($('status'), ''); return; }
        if (!ok) { setStatus($('status'), 'Please choose an Excel (.xlsx, .xls) or CSV (.csv) file.', true); return; }
        await analyze({ fresh: true });
    }

    fileInput.addEventListener('change', onFileChosen);
    ['dragenter', 'dragover'].forEach((ev) => dropzone.addEventListener(ev, () => dropzone.classList.add('dragover')));
    ['dragleave', 'drop'].forEach((ev) => dropzone.addEventListener(ev, () => dropzone.classList.remove('dragover')));

    async function analyze({ fresh = false } = {}) {
        const file = fileInput.files[0];
        if (!file) return;
        const body = new FormData();
        body.append('file', file);
        body.append('date_order', $('dateOrder').value);
        if (!fresh) {
            if ($('sheet').value) body.append('sheet', $('sheet').value);
            if ($('headerRow').value) body.append('header_row', $('headerRow').value);
        }
        setStatus($('status'), 'Reading file…');
        // A slower reply for an earlier file must not replace the current one.
        const request = ++analyzeRequest;
        try {
            if (!Object.keys(fields).length) fields = (await api('/import/fields', { headers: headers() })).fields;
            const reply = await api('/import/analyze', { method: 'POST', body, headers: headers() });
            await loadProfiles();
            if (request !== analyzeRequest) return;
            analysis = reply;
            setStatus($('status'), '');
            showMapping();
            refreshAiStatus();
        } catch (err) {
            if (request !== analyzeRequest) return;
            $('mapCard').hidden = true;
            setStatus($('status'), err.message, true);
        }
    }

    // ---------- step 2: mapping ----------
    function showMapping() {
        targets = {};
        aiMarked = new Set();
        analysis.columns.forEach((c) => { targets[c.name] = c.target; });

        $('shape').value = analysis.shape;
        $('period').value = analysis.period || '';
        $('headerRow').value = analysis.header_row;

        const sheets = analysis.sheets || [];
        $('sheetLabel').hidden = sheets.length < 2;
        $('sheet').replaceChildren(...sheets.map((s) => {
            const o = cell('option', s);
            o.value = s;
            return o;
        }));
        if (analysis.sheet) $('sheet').value = analysis.sheet;

        $('fileSummary').textContent = `${analysis.row_count} rows, ${analysis.columns.length} columns`;
        $('profileNotice').hidden = true;
        $('profileSelect').value = '';
        if (analysis.matched_profile) {
            applyProfile(analysis.matched_profile);
            $('profileSelect').value = String(analysis.matched_profile.id);
            $('profileNotice').textContent = `This file looks like your saved mapping "${analysis.matched_profile.name}", so it was applied. Check it below.`;
            $('profileNotice').hidden = false;
        }
        syncProfileButtons();
        renderMapping();
        $('mapCard').hidden = false;
        $('resultCard').hidden = true;
    }

    function dayColumns() {
        return analysis.columns.filter((c) => c.is_day);
    }

    function renderMapping() {
        const shape = $('shape').value;
        const isMatrix = shape === 'monthly_matrix';
        $('periodLabel').hidden = !isMatrix;

        const days = isMatrix ? dayColumns() : [];
        $('dayHint').hidden = !days.length;
        $('dayHint').textContent = days.length ? `${days.length} day columns found (${days[0].name} to ${days[days.length - 1].name}). They are read automatically.` : '';

        const visible = analysis.columns.filter((c) => !(isMatrix && c.is_day));
        fillTable($('mapTable'), ['Column in your file', 'Sample values', 'Use as'], visible.map((c) => {
            const name = cell('td', c.name);
            const sample = cell('td', c.samples.slice(0, 3).join(' · ') || '(empty)', 'samples');
            const td = document.createElement('td');
            td.append(targetSelect(c.name, shape));
            if (aiMarked.has(c.name)) td.append(cell('span', 'AI suggestion, please check', 'tag'));
            return [name, sample, td];
        }));
    }

    function targetSelect(column, shape) {
        const select = document.createElement('select');
        select.setAttribute('aria-label', `Use column ${column} as`);
        const add = (value, label) => {
            const o = cell('option', label);
            o.value = value;
            select.append(o);
        };
        add('extra', 'Keep as extra data');
        add('ignore', 'Do not import');
        SHAPE_FIELDS[shape].forEach((f) => add(f, fields[f]));
        const current = targets[column];
        select.value = SHAPE_FIELDS[shape].includes(current) || current === 'ignore' ? current : 'extra';
        select.addEventListener('change', () => {
            aiMarked.delete(column);
            // One field fits one column: release it from any other column.
            if (select.value !== 'extra' && select.value !== 'ignore') {
                Object.keys(targets).forEach((other) => {
                    if (other !== column && targets[other] === select.value) {
                        targets[other] = 'extra';
                        aiMarked.delete(other);
                    }
                });
            }
            targets[column] = select.value;
            renderMapping();
        });
        return select;
    }

    $('shape').addEventListener('change', renderMapping);
    // Date format only affects reading the rows, so it keeps the mapping the person has made.
    $('headerRow').addEventListener('change', () => analyze());
    $('sheet').addEventListener('change', () => {
        $('headerRow').value = ''; // each sheet finds its own heading row
        analyze();
    });

    function currentColumns() {
        const shape = $('shape').value;
        const columns = {};
        analysis.columns.forEach((c) => {
            if (shape === 'monthly_matrix' && c.is_day) {
                columns[c.name] = 'day';
                return;
            }
            const t = targets[c.name];
            columns[c.name] = SHAPE_FIELDS[shape].includes(t) || t === 'ignore' ? t : 'extra';
        });
        return columns;
    }

    // ---------- profiles ----------
    async function loadProfiles() {
        profiles = await api('/import/profiles', { headers: headers() }).catch(() => []);
        const none = cell('option', 'None');
        none.value = '';
        $('profileSelect').replaceChildren(none, ...profiles.map((p) => {
            const o = cell('option', p.name);
            o.value = String(p.id);
            return o;
        }));
    }

    function applyProfile(profile) {
        analysis.columns.forEach((c) => {
            targets[c.name] = profile.columns[c.name] || (c.is_day && profile.shape === 'monthly_matrix' ? 'day' : 'extra');
        });
        $('shape').value = profile.shape;
        $('dateOrder').value = profile.date_order;
        $('profileName').value = profile.name;
    }

    function syncProfileButtons() {
        $('deleteProfileBtn').hidden = !$('profileSelect').value;
    }

    $('profileSelect').addEventListener('change', () => {
        const profile = profiles.find((p) => String(p.id) === $('profileSelect').value);
        if (profile) applyProfile(profile);
        else $('profileName').value = '';
        syncProfileButtons();
        renderMapping();
    });

    $('saveProfileBtn').addEventListener('click', async () => {
        const name = $('profileName').value.trim();
        if (!name) { setStatus($('mapStatus'), 'Type a name for this mapping first.', true); return; }
        try {
            const saved = await api('/import/profiles', {
                method: 'POST',
                headers: headers(true),
                body: JSON.stringify({
                    name,
                    shape: $('shape').value,
                    columns: currentColumns(),
                    date_order: $('dateOrder').value,
                    headers: analysis.columns.map((c) => c.name),
                }),
            });
            await loadProfiles();
            $('profileSelect').value = String(saved.id);
            syncProfileButtons();
            setStatus($('mapStatus'), `Mapping "${saved.name}" saved. Files with the same columns will use it automatically.`);
        } catch (err) {
            setStatus($('mapStatus'), err.message, true);
        }
    });

    $('deleteProfileBtn').addEventListener('click', async () => {
        const id = $('profileSelect').value;
        if (!id) return;
        try {
            await api(`/import/profiles/${encodeURIComponent(id)}`, { method: 'DELETE', headers: headers() });
            await loadProfiles();
            $('profileSelect').value = '';
            $('profileName').value = '';
            syncProfileButtons();
            setStatus($('mapStatus'), 'Saved mapping deleted.');
        } catch (err) {
            setStatus($('mapStatus'), err.message, true);
        }
    });

    // ---------- AI (optional) ----------
    async function refreshAiStatus() {
        const btn = $('aiBtn');
        // The check can take seconds when Ollama is off; only the newest answer counts.
        const request = ++aiStatusRequest;
        try {
            const s = await api('/import/ai/status', { headers: headers() });
            if (request !== aiStatusRequest) return;
            btn.disabled = !s.available;
            $('aiHint').textContent = !s.available ? s.hint
                : s.external ? `Uses ${s.model} at ${s.host}. Headings and a few sample values of unmatched columns are sent there.`
                : `Runs on this computer with ${s.model}. Only headings and a few sample values are used.`;
        } catch (_) {
            if (request !== aiStatusRequest) return;
            btn.disabled = true;
            $('aiHint').textContent = 'AI suggestions are off.';
        }
    }

    $('aiBtn').addEventListener('click', async () => {
        const shape = $('shape').value;
        const unknown = analysis.columns.filter((c) => targets[c.name] === 'extra' && !(shape === 'monthly_matrix' && c.is_day));
        if (!unknown.length) { setStatus($('mapStatus'), 'Every column is already matched.'); return; }
        const already = Object.values(targets).filter((t) => t !== 'extra' && t !== 'ignore' && t !== 'day');
        $('aiBtn').disabled = true;
        setStatus($('mapStatus'), 'Asking the local AI model. This can take a minute…');
        try {
            const body = JSON.stringify({
                columns: unknown.map((c) => ({ name: c.name, samples: c.samples })),
                already_mapped: already,
            });
            const reply = await api('/import/ai/suggest', { method: 'POST', headers: headers(true), body });
            const usable = reply.suggestions.filter((s) => SHAPE_FIELDS[shape].includes(s.field));
            usable.forEach((s) => {
                targets[s.column] = s.field;
                aiMarked.add(s.column);
            });
            renderMapping();
            setStatus($('mapStatus'), usable.length
                ? `AI suggested ${usable.length} matches. Please check them before importing.`
                : 'AI had no confident suggestion for the remaining columns.');
        } catch (err) {
            setStatus($('mapStatus'), err.message, true);
        } finally {
            $('aiBtn').disabled = false;
        }
    });

    let setupLoaded = false;
    $('aiSetup').addEventListener('toggle', async () => {
        if (!$('aiSetup').open || setupLoaded) return;
        try {
            const setup = await api('/import/ai/setup', { headers: headers() });
            setupLoaded = true;
            const verdict = $('specVerdict');
            verdict.textContent = setup.system.message;
            verdict.className = `spec-verdict ${setup.system.verdict}`;
            const show = (value, unit) => (value == null ? 'Unknown' : `${value}${unit ? ` ${unit}` : ''}`);
            const mark = (ok) => (ok == null ? 'Please check' : ok ? 'OK' : 'Too low');
            fillTable($('specTable'), ['', 'This computer', 'Minimum', ''], setup.system.lines.map((l) => [
                l.label, show(l.have, l.unit), show(l.need, l.unit),
                cell('td', mark(l.ok), l.ok === false ? 'err' : ''),
            ]));
            $('ollamaLink').href = setup.local.download_url;
            $('pullCommand').textContent = setup.local.pull_command;
            $('apiEnv').textContent = setup.api.env_example;
        } catch (err) {
            $('specVerdict').textContent = err.message;
            $('specVerdict').className = 'spec-verdict low';
        }
    });

    // ---------- step 3: check / import ----------
    async function run(dryRun) {
        const file = fileInput.files[0];
        if (!file || !analysis || busy) return;
        const plan = {
            shape: $('shape').value,
            columns: currentColumns(),
            date_order: $('dateOrder').value,
            period: $('period').value || null,
            sheet: $('sheet').value || null,
            header_row: analysis.header_row,
        };
        const body = new FormData();
        body.append('file', file);
        body.append('plan', JSON.stringify(plan));
        body.append('dry_run', dryRun ? 'true' : 'false');

        busy = true;
        $('importBtn').disabled = $('checkBtn').disabled = true;
        setStatus($('mapStatus'), dryRun ? 'Checking file…' : 'Importing and saving…');
        try {
            const data = await api('/import/run', { method: 'POST', body, headers: headers() });
            setStatus($('mapStatus'), '');
            showResult(data, dryRun);
        } catch (err) {
            setStatus($('mapStatus'), err.message, true);
        } finally {
            busy = false;
            $('importBtn').disabled = $('checkBtn').disabled = false;
        }
    }

    $('checkBtn').addEventListener('click', () => run(true));
    $('importBtn').addEventListener('click', () => run(false));
    $('resetBtn').addEventListener('click', () => {
        fileInput.value = '';
        $('profileName').value = '';
        onFileChosen();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    function showResult(data, dryRun) {
        $('resultCard').hidden = false;
        $('resultTitle').textContent = dryRun ? 'Check result (nothing saved)' : 'Import result';

        const msg = $('resultMessage');
        msg.textContent = data.message;
        const nothingGood = dryRun ? data.records_found === 0 : data.saved === 0 && data.duplicates_skipped === 0;
        msg.className = 'result-message ' + (nothingGood ? 'err' : data.failed_imports ? 'warn' : 'ok');

        const stats = [
            ['Rows in file', data.total_records],
            ['Records found', data.records_found],
            dryRun ? null : ['Saved', data.saved],
            dryRun ? null : ['Duplicates skipped', data.duplicates_skipped],
            data.skipped_blank ? ['Empty rows skipped', data.skipped_blank] : null,
            ['Problems', data.failed_imports],
        ].filter(Boolean);
        $('stats').replaceChildren(...stats.map(([label, value]) => {
            const box = cell('div', '', 'stat');
            box.append(cell('div', value, 'stat-value'), cell('div', label, 'stat-label'));
            return box;
        }));

        const warnings = data.warnings || [];
        $('warnings').hidden = !warnings.length;
        $('warnings').replaceChildren(...warnings.map((w) => cell('li', w)));

        lastErrors = data.errors || [];
        $('errorsBlock').hidden = lastErrors.length === 0;
        if (lastErrors.length) {
            $('errorsHint').textContent = data.errors_truncated
                ? `Showing the first ${lastErrors.length} of ${data.failed_imports} problems. Fix them in the file and import again: saved rows are skipped.`
                : 'Fix these rows in your file and import again. Rows already saved are skipped automatically.';
            const columns = currentColumns();
            const codeColumn = Object.keys(columns).find((k) => columns[k] === 'employee_code');
            const nameColumn = Object.keys(columns).find((k) => columns[k] === 'name');
            fillTable($('errorsTable'), ['Row', 'Problem', 'Employee code', 'Name'],
                lastErrors.map((e) => [e.row, cell('td', e.error, 'err'), e.data?.[codeColumn], e.data?.[nameColumn]]));
        }

        const preview = data.preview || [];
        $('previewBlock').hidden = preview.length === 0;
        if (preview.length) {
            const inOut = (s) => (s === 0 ? 'In' : s === 1 ? 'Out' : '');
            fillTable($('previewTable'), ['Employee code', 'Name', 'Date & time', 'In/Out', 'Day status', 'Extra columns'],
                preview.map((r) => [r.uid, r.name, r.day_status ? r.date_time.slice(0, 10) : r.date_time, inOut(r.status),
                    r.day_status, Object.keys(r.extra || {}).length || '']));
        }
        $('resultCard').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    $('downloadErrors').addEventListener('click', () => {
        if (!lastErrors.length) return;
        const cols = Array.from(new Set(lastErrors.flatMap((e) => Object.keys(e.data || {}))));
        const esc = (v) => {
            const s = v == null ? '' : String(v);
            // Prefix formula-like values so spreadsheets don't execute them.
            const safe = /^[=+\-@]/.test(s) ? `'${s}` : s;
            return /[",\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
        };
        const lines = [['Row', 'Error', ...cols].map(esc).join(',')]
            .concat(lastErrors.map((e) => [e.row, e.error, ...cols.map((c) => e.data?.[c])].map(esc).join(',')));
        const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'attendance_problems.csv';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(a.href);
    });
})();
