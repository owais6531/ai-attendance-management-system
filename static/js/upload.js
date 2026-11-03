// Attendance upload page. All file data is rendered with textContent (never innerHTML).
(() => {
    const $ = (id) => document.getElementById(id);
    const form = $('uploadForm');
    const fileInput = $('fileInput');
    const dropzone = $('dropzone');
    const uploadBtn = $('uploadBtn');
    const checkBtn = $('checkBtn');
    const statusEl = $('status');
    const apiKeyInput = $('apiKey');
    let lastErrors = [];

    const KEY_STORE = 'attendance_api_key';
    if (apiKeyInput) {
        try { apiKeyInput.value = sessionStorage.getItem(KEY_STORE) || ''; } catch (_) { /* storage blocked */ }
    }

    const formatSize = (bytes) => {
        if (!bytes) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB'];
        const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
        return `${(bytes / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`;
    };

    const setStatus = (text, isError = false) => {
        statusEl.textContent = text;
        statusEl.classList.toggle('error', isError);
    };

    const onFileChosen = () => {
        const file = fileInput.files[0];
        const ok = !!file && /\.(xlsx|xls|csv)$/i.test(file.name);
        $('dzTitle').textContent = file ? file.name : 'Drop a file here or click to browse';
        $('dzSub').textContent = file ? formatSize(file.size) : '.xlsx, .xls or .csv';
        uploadBtn.disabled = checkBtn.disabled = !ok;
        setStatus(file && !ok ? 'Please choose an Excel (.xlsx, .xls) or CSV (.csv) file.' : '', file && !ok);
        $('resultCard').hidden = true;
    };

    fileInput.addEventListener('change', onFileChosen);
    ['dragenter', 'dragover'].forEach((ev) => dropzone.addEventListener(ev, () => dropzone.classList.add('dragover')));
    ['dragleave', 'drop'].forEach((ev) => dropzone.addEventListener(ev, () => dropzone.classList.remove('dragover')));

    async function send(dryRun) {
        const file = fileInput.files[0];
        if (!file) return;
        const body = new FormData();
        body.append('file', file);
        body.append('date_order', $('dateOrder').value);
        body.append('dry_run', dryRun ? 'true' : 'false');

        const headers = {};
        if (apiKeyInput && apiKeyInput.value) {
            headers['X-API-Key'] = apiKeyInput.value;
            try { sessionStorage.setItem(KEY_STORE, apiKeyInput.value); } catch (_) { /* ignore */ }
        }

        uploadBtn.disabled = checkBtn.disabled = true;
        setStatus(dryRun ? 'Checking file…' : 'Uploading and saving…');
        try {
            const res = await fetch('/upload/attendance', { method: 'POST', body, headers });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                const detail = typeof data.detail === 'string' ? data.detail
                    : Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join('; ')
                    : `Server returned ${res.status}`;
                setStatus(res.status === 401 ? 'API key is missing or wrong.' : detail, true);
                return;
            }
            setStatus('');
            showResult(data, dryRun);
        } catch (err) {
            setStatus(`Network error: ${err.message}`, true);
        } finally {
            uploadBtn.disabled = checkBtn.disabled = !fileInput.files[0];
        }
    }

    form.addEventListener('submit', (e) => { e.preventDefault(); send(false); });
    checkBtn.addEventListener('click', () => send(true));
    $('resetBtn').addEventListener('click', () => {
        form.reset();
        onFileChosen();
        if (apiKeyInput) { try { apiKeyInput.value = sessionStorage.getItem(KEY_STORE) || ''; } catch (_) { /* */ } }
    });

    function cell(tag, text, cls) {
        const el = document.createElement(tag);
        el.textContent = text == null ? '' : String(text);
        if (cls) el.className = cls;
        return el;
    }

    function fillTable(table, headers, rows) {
        table.replaceChildren();
        const thead = document.createElement('thead');
        const hr = document.createElement('tr');
        headers.forEach((h) => hr.appendChild(cell('th', h)));
        thead.appendChild(hr);
        const tbody = document.createElement('tbody');
        rows.forEach((r) => {
            const tr = document.createElement('tr');
            r.forEach((v) => tr.appendChild(v instanceof HTMLElement ? v : cell('td', v)));
            tbody.appendChild(tr);
        });
        table.append(thead, tbody);
    }

    function showResult(data, dryRun) {
        $('resultCard').hidden = false;
        $('resultTitle').textContent = dryRun ? 'Check result (nothing saved)' : 'Upload result';

        const msg = $('resultMessage');
        msg.textContent = data.message;
        const nothingGood = dryRun ? data.valid_records === 0 : data.saved === 0 && data.duplicates_skipped === 0;
        msg.className = 'result-message ' + (nothingGood ? 'err' : data.failed_imports ? 'warn' : 'ok');

        const stats = [
            ['Rows in file', data.total_records],
            ['Valid rows', data.valid_records],
            dryRun ? null : ['Saved', data.saved],
            dryRun ? null : ['Duplicates skipped', data.duplicates_skipped],
            ['Rows with errors', data.failed_imports],
        ].filter(Boolean);
        const statsEl = $('stats');
        statsEl.replaceChildren(...stats.map(([label, value]) => {
            const box = cell('div', '', 'stat');
            box.append(cell('div', value, 'stat-value'), cell('div', label, 'stat-label'));
            return box;
        }));

        lastErrors = data.errors || [];
        $('errorsBlock').hidden = lastErrors.length === 0;
        if (lastErrors.length) {
            $('errorsHint').textContent = data.errors_truncated
                ? `Showing the first ${lastErrors.length} of ${data.failed_imports} errors. Fix them in the file and upload again — rows already saved will be skipped.`
                : 'Fix these rows in your file and upload again. Rows already saved will be skipped automatically.';
            fillTable($('errorsTable'), ['Row', 'Problem', 'UID', 'Name', 'DateTime'],
                lastErrors.map((e) => [e.row, cell('td', e.error, 'err'), e.data?.UID, e.data?.Name, e.data?.DateTime]));
        }

        const preview = data.preview || [];
        $('previewBlock').hidden = preview.length === 0;
        if (preview.length) {
            fillTable($('previewTable'), ['No', 'DN', 'UID', 'Name', 'Status', 'Action', 'APB', 'Job code', 'Date & time'],
                preview.map((r) => [r.no, r.dn, r.uid, r.name, r.status, r.action, r.apb, r.job_code, r.date_time]));
        }
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
        a.download = 'attendance_errors.csv';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(a.href);
    });
})();
