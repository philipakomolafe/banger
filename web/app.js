const el = (id) => document.getElementById(id);

function setStatus(msg, kind) {
  const s = el('status');
  s.textContent = msg || '';
  s.className = 'status' + (kind ? ` ${kind}` : '');
}

async function fetchConfig() {
  try {
    const res = await fetch('/api/config');
    const cfg = await res.json();

    el('quota').textContent = `Remaining X API writes this month: ${cfg.remaining_writes ?? 0}`;
    window.COMMUNITY_URL = cfg.community_url || null;
  } catch (e) {
    el('quota').textContent = 'Quota unavailable';
  }
}

function optionCard(initialText, idx) {
  const card = document.createElement('div');
  card.className = 'card';

  const top = document.createElement('div');
  top.className = 'cardTop';

  const left = document.createElement('div');
  left.className = 'badge';
  left.textContent = `Option ${idx + 1}`;

  const count = document.createElement('div');
  count.className = 'count';

  top.appendChild(left);
  top.appendChild(count);

  const ta = document.createElement('textarea');
  ta.value = initialText;
  ta.style.minHeight = '86px';

  const updateCount = () => {
    const max = parseInt(el('max_chars').value || '280', 10);
    const n = (ta.value || '').length;
    count.textContent = `${n}${Number.isFinite(max) ? ` / ${max}` : ''}`;
    count.style.color = (Number.isFinite(max) && n > max) ? 'rgba(255,92,122,.95)' : 'var(--muted)';
  };
  ta.addEventListener('input', updateCount);
  updateCount();

  const actions = document.createElement('div');
  actions.className = 'cardActions';

  const btnCopy = document.createElement('button');
  btnCopy.className = 'btn';
  btnCopy.textContent = 'Copy';
  btnCopy.onclick = async () => {
    try {
      await navigator.clipboard.writeText(ta.value);
      setStatus('Copied to clipboard.', 'ok');
      setTimeout(() => setStatus('', ''), 1200);
    } catch {
      setStatus('Clipboard failed. Copy manually.', 'err');
    }
  };

  const btnPost = document.createElement('button');
  btnPost.className = 'btn primary';
  btnPost.textContent = 'Post via API';
  btnPost.onclick = async () => {
    const text = (ta.value || '').trim();
    if (!text) return setStatus('Empty draft.', 'err');

    setStatus('Posting via API…');
    const res = await fetch('/api/post', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, method: 'api' })
    });
    const data = await res.json();
    if (data.success) {
      setStatus(`Posted. Tweet ID: ${data.tweet_id}`, 'ok');
      fetchConfig();
    } else {
      if (data.intent_url) {
        const go = confirm(`API failed: ${data.error}\nOpen in X composer instead?`);
        if (go) window.open(data.intent_url, '_blank');
      }
      setStatus(`API failed: ${data.error || 'Unknown error'}`, 'err');
    }
  };

  const btnIntent = document.createElement('button');
  btnIntent.className = 'btn';
  btnIntent.textContent = 'Open in X';
  btnIntent.onclick = async () => {
    const text = (ta.value || '').trim();
    if (!text) return setStatus('Empty draft.', 'err');

    setStatus('Opening X composer…');
    const res = await fetch('/api/post', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, method: 'manual' })
    });
    const data = await res.json();
    if (data.intent_url) window.open(data.intent_url, '_blank');
    setStatus('Opened X composer (recorded to ledger).', 'ok');
    setTimeout(() => setStatus('', ''), 1500);
  };

  const btnCommunity = document.createElement('button');
  btnCommunity.className = 'btn';
  btnCommunity.textContent = 'Community';
  btnCommunity.onclick = async () => {
    const text = (ta.value || '').trim();
    if (!text) return setStatus('Empty draft.', 'err');

    if (!window.COMMUNITY_URL) {
      setStatus('Set X_COMMUNITY_URL in your environment to use Community.', 'err');
      return;
    }

    try { await navigator.clipboard.writeText(text); } catch {}

    await fetch('/api/post', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, method: 'community' })
    });

    window.open(window.COMMUNITY_URL, '_blank');
    setStatus('Copied (if permitted). Paste into the Community composer.', 'ok');
    setTimeout(() => setStatus('', ''), 1800);
  };

  actions.appendChild(btnCopy);
  actions.appendChild(btnPost);
  actions.appendChild(btnIntent);
  actions.appendChild(btnCommunity);

  card.appendChild(top);
  card.appendChild(ta);
  card.appendChild(actions);
  return { card, getText: () => (ta.value || '').trim() };
}

function getAllOptionTexts() {
  const cards = Array.from(document.querySelectorAll('.card textarea'));
  return cards.map(t => (t.value || '').trim()).filter(Boolean);
}

function wireUI() {
  el('generate').onclick = async () => {
    const today_context = el('today_context').value;
    const current_mood = el('current_mood').value;
    const optional_angle = el('optional_angle').value;

    const max_options = parseInt(el('max_options').value || '3', 10);
    const max_chars = parseInt(el('max_chars').value || '280', 10);

    setStatus('Generating…');

    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ today_context, current_mood, optional_angle, max_options, max_chars })
    });

    if (!res.ok) {
      let err = {};
      try { err = await res.json(); } catch {}
      setStatus(`Generate failed: ${err.detail || res.statusText}`, 'err');
      return;
    }

    const data = await res.json();

    const mode = data.mode || '';
    const pill = el('modePill');
    if (mode) {
      pill.style.display = '';
      pill.textContent = `Mode: ${mode}`;
    } else {
      pill.style.display = 'none';
    }

    const container = el('options');
    container.innerHTML = '';

    (data.options || []).forEach((o, idx) => {
      const { card } = optionCard(o, idx);
      container.appendChild(card);
    });

    fetchConfig();

    const remaining = (data.remaining_writes ?? null);
    if (remaining !== null && remaining !== undefined) {
      setStatus(`Generated ${data.options?.length || 0} option(s). Remaining API writes: ${remaining}`, 'ok');
    } else {
      setStatus(`Generated ${data.options?.length || 0} option(s).`, 'ok');
    }

    if (Array.isArray(data.warnings) && data.warnings.length) {
      setStatus(data.warnings.slice(0, 2).join(' '), 'err');
    }
  };

  el('copyAll').onclick = async () => {
    const all = getAllOptionTexts();
    if (!all.length) return setStatus('No options to copy.', 'err');

    const body = all.map((t, i) => `Option ${i + 1}\n${t}`).join('\n\n---\n\n');
    try {
      await navigator.clipboard.writeText(body);
      setStatus('Copied all options.', 'ok');
      setTimeout(() => setStatus('', ''), 1200);
    } catch {
      setStatus('Clipboard failed. Copy manually.', 'err');
    }
  };

  el('emailAll').onclick = async () => {
    const options = getAllOptionTexts();
    if (!options.length) return setStatus('No options to email.', 'err');

    const subject = (el('email_subject').value || 'Banger drafts').trim();

    setStatus('Sending email…');
    const res = await fetch('/api/email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject, options })
    });

    if (!res.ok) {
      let err = {};
      try { err = await res.json(); } catch {}
      setStatus(`Email failed: ${err.detail || res.statusText}`, 'err');
      return;
    }
    setStatus('Email sent.', 'ok');
    setTimeout(() => setStatus('', ''), 1400);
  };

  el('clear').onclick = () => {
    el('today_context').value = '';
    el('current_mood').value = '';
    el('optional_angle').value = '';
    el('options').innerHTML = '';
    el('modePill').style.display = 'none';
    setStatus('', '');
  };
}

document.addEventListener('DOMContentLoaded', () => {
  wireUI();
  fetchConfig();
});
