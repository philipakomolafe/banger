const el = (id) => document.getElementById(id);

// User state
let currentUser = null;
let pendingTweetData = null; // Store data for tweet URL modal

function setStatus(msg, kind) {
  const s = el('status');
  if (s) {
    s.textContent = msg || '';
    s.className = 'status' + (kind ? ` ${kind}` : '');
  }
}

function normalize(s) {
  return (s || '').trim();
}

function updateGenerateEnabled() {
  const btn = el('generate');
  const ctx = el('today_context');
  if (!btn || !ctx) return;
  
  const hasContext = normalize(ctx.value).length > 0;
  btn.disabled = !hasContext;
  if (!hasContext) {
    setStatus("Add today's context to generate.", '');
  } else if (el('status')?.textContent === "Add today's context to generate.") {
    setStatus('', '');
  }
}

function updateUsageDisplay(used, limit, isPro) {
  const usageDisplay = el('usageDisplay');
  const usageIcon = el('usageIcon');
  const usagePill = el('usagePill');
  
  console.log('updateUsageDisplay:', { used, limit, isPro });
  console.log('Elements:', { usageDisplay: !!usageDisplay, usageIcon: !!usageIcon, usagePill: !!usagePill });
  
  if (!usageDisplay || !usageIcon || !usagePill) {
    console.warn('Usage display elements not found');
    return;
  }
  
  if (isPro) {
    usageDisplay.textContent = 'Pro (Unlimited)';
    usageIcon.textContent = '⚡';
    usagePill.classList.add('pro');
    usagePill.classList.remove('exhausted');
  } else {
    const remaining = Math.max(0, limit - used);
    usageDisplay.textContent = `${remaining}/${limit} left`;
    usageIcon.textContent = remaining > 0 ? '⚡' : '🔒';
    usagePill.classList.remove('pro');
    
    if (remaining === 0) {
      usagePill.classList.add('exhausted');
    } else {
      usagePill.classList.remove('exhausted');
    }
  }
}

function updateAccountModal(user) {
  console.log('updateAccountModal:', user);
  
  // Email
  const emailEl = el('accountEmail');
  if (emailEl) {
    emailEl.textContent = user.email || 'Unknown';
  }
  
  // Plan
  const planBadge = el('accountPlan');
  const isPro = user.plan === 'pro' || user.is_pro;
  if (planBadge) {
    planBadge.textContent = isPro ? 'Pro' : 'Free';
    planBadge.className = 'plan-badge ' + (isPro ? 'pro' : 'free');
  }
  
  // Usage section (hide for pro users)
  const usageSection = el('usageSection');
  if (usageSection) {
    if (isPro) {
      usageSection.style.display = 'none';
    } else {
      usageSection.style.display = 'block';
      const used = user.daily_usage || 0;
      const limit = user.daily_limit || 3;
      const percentage = Math.min(100, (used / limit) * 100);
      
      const usageBar = el('usageBar');
      const accountUsage = el('accountUsage');
      
      if (usageBar) {
        usageBar.style.width = `${percentage}%`;
        // Color the bar based on usage
        if (percentage >= 100) {
          usageBar.style.background = 'var(--danger, #ff5c7a)';
        } else if (percentage >= 66) {
          usageBar.style.background = '#f59e0b';
        } else {
          usageBar.style.background = 'var(--accent, #6366f1)';
        }
      }
      
      if (accountUsage) {
        accountUsage.textContent = `${used} / ${limit} generations`;
      }
    }
  }
  
  // Buttons
  const upgradeBtn = el('accountUpgradeBtn');
  const manageBtn = el('manageSubscription');
  if (upgradeBtn) upgradeBtn.style.display = isPro ? 'none' : 'block';
  if (manageBtn) manageBtn.style.display = isPro ? 'block' : 'none';
}

async function fetchUserInfo() {
  const token = localStorage.getItem('access_token');
  if (!token) {
    console.warn('No access token found');
    return null;
  }
  
  try {
    console.log('Fetching user info...');
    const res = await fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    });
    
    if (!res.ok) {
      console.error('Failed to fetch user info:', res.status);
      const text = await res.text();
      console.error('Response:', text);
      return null;
    }
    
    const user = await res.json();
    console.log('User info received:', user);
    currentUser = user;
    
    // Parse values - handle both flat and nested structures
    const isPro = user.plan === 'pro' || user.is_pro === true;
    const used = user.daily_usage ?? 0;
    const limit = user.daily_limit ?? 3;
    
    console.log('Parsed values:', { isPro, used, limit });
    
    // Update both displays
    updateUsageDisplay(used, limit, isPro);
    updateAccountModal({
      ...user,
      daily_usage: used,
      daily_limit: limit,
      is_pro: isPro
    });
    
    return user;
  } catch (e) {
    console.error('Failed to fetch user info:', e);
    return null;
  }
}

async function fetchConfig() {
  try {
    const res = await fetch('/api/config');
    const cfg = await res.json();

    const quotaEl = el('quota');
    if (quotaEl) quotaEl.textContent = `API writes: ${cfg.remaining_writes ?? 0}`;
    window.COMMUNITY_URL = cfg.community_url || null;
  } catch (e) {
    console.error('fetchConfig error:', e);
    const quotaEl = el('quota');
    if (quotaEl) quotaEl.textContent = 'Quota unavailable';
  }
}

async function ensureAuthed() {
  const token = localStorage.getItem('access_token');
  if (!token) {
    window.location.href = './auth.html';
    return false;
  }

  try {
    const res = await fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!res.ok) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user_email');
      window.location.href = './auth.html';
      return false;
    }

    return true;
  } catch (_) {
    window.location.href = './auth.html';
    return false;
  }
}

// Modal functions
function showPaywallModal() {
  const modal = el('paywallModal');
  if (modal) {
    modal.classList.add('visible');
    document.body.style.overflow = 'hidden';
  }
}

function hidePaywallModal() {
  const modal = el('paywallModal');
  if (modal) {
    modal.classList.remove('visible');
    document.body.style.overflow = '';
  }
}

function showAccountModal() {
  console.log('Opening account modal...');
  fetchUserInfo(); // Refresh user info
  const modal = el('accountModal');
  if (modal) {
    modal.classList.add('visible');
    document.body.style.overflow = 'hidden';
  }
}

function hideAccountModal() {
  const modal = el('accountModal');
  if (modal) {
    modal.classList.remove('visible');
    document.body.style.overflow = '';
  }
}

function showTweetUrlModal(text, method) {
  pendingTweetData = { text, method };
  const modal = el('tweetUrlModal');
  const input = el('tweetUrlInput');
  if (input) input.value = '';
  if (modal) {
    modal.classList.add('visible');
    document.body.style.overflow = 'hidden';
    if (input) input.focus();
  }
}

function hideTweetUrlModal() {
  const modal = el('tweetUrlModal');
  if (modal) {
    modal.classList.remove('visible');
    document.body.style.overflow = '';
  }
  pendingTweetData = null;
}

async function saveTweetUrl() {
  if (!pendingTweetData) return;
  
  const input = el('tweetUrlInput');
  const tweetUrl = (input?.value || '').trim();
  
  if (tweetUrl) {
    try {
      await fetch('/api/record', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          text: pendingTweetData.text,
          method: pendingTweetData.method,
          tweet_url: tweetUrl
        })
      });
      setStatus('Tweet tracked successfully!', 'ok');
      setTimeout(() => setStatus('', ''), 2000);
    } catch (e) {
      console.error('Failed to save tweet URL:', e);
      setStatus('Failed to save tweet URL', 'err');
    }
  }
  
  hideTweetUrlModal();
}

function logout() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user_email');
  window.location.href = './auth.html';
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
    const maxCharsEl = el('max_chars');
    const max = parseInt(maxCharsEl?.value || '280', 10);
    const n = (ta.value || '').length;
    count.textContent = `${n}${Number.isFinite(max) ? ` / ${max}` : ''}`;
    count.style.color = (Number.isFinite(max) && n > max) ? 'rgba(255,92,122,.95)' : 'var(--muted)';
  };
  ta.addEventListener('input', updateCount);
  updateCount();

  const actions = document.createElement('div');
  actions.className = 'cardActions';

  // Copy button
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

  // Post via API button
  const btnPost = document.createElement('button');
  btnPost.className = 'btn primary';
  btnPost.textContent = 'Post via API';
  btnPost.onclick = async () => {
    const text = (ta.value || '').trim();
    if (!text) return setStatus('Empty draft.', 'err');

    setStatus('Posting via API…');
    try {
      const res = await fetch('/api/post', {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'X-Use-X-Api': '1' },
        body: JSON.stringify({ text, method: 'api' })
      });
      const data = await res.json();
      if (data.success) {
        setStatus(`Posted! Tweet ID: ${data.tweet_id}`, 'ok');
        fetchConfig();
      } else {
        if (data.intent_url) {
          const go = confirm(`API failed: ${data.error}\nOpen in X composer instead?`);
          if (go) window.open(data.intent_url, '_blank');
        }
        setStatus(`API failed: ${data.error || 'Unknown error'}`, 'err');
      }
    } catch (e) {
      setStatus('Network error posting', 'err');
    }
  };

  // Open in X button
  const btnIntent = document.createElement('button');
  btnIntent.className = 'btn';
  btnIntent.textContent = 'Open in X';
  btnIntent.onclick = async () => {
    const text = (ta.value || '').trim();
    if (!text) return setStatus('Empty draft.', 'err');

    setStatus('Opening X composer…');
    try {
      const res = await fetch('/api/post', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ text, method: 'manual' })
      });

      const data = await res.json();
      if (data.intent_url) {
        window.open(data.intent_url, '_blank');
      }
      setStatus('Opened X composer.', 'ok');
      
      // Show modal to capture tweet URL
      setTimeout(() => {
        showTweetUrlModal(text, 'manual');
      }, 1000);
    } catch (e) {
      setStatus('Failed to open X', 'err');
    }
  };

  // Community button
  const btnCommunity = document.createElement('button');
  btnCommunity.className = 'btn';
  btnCommunity.textContent = 'Community';
  btnCommunity.onclick = async () => {
    const text = (ta.value || '').trim();
    if (!text) return setStatus('Empty draft.', 'err');

    if (!window.COMMUNITY_URL) {
      setStatus('Community URL not configured.', 'err');
      return;
    }

    try {
      await fetch('/api/post', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ text, method: 'community' })
      });

      window.open(window.COMMUNITY_URL, '_blank');
      setStatus('Opening Community. Paste your draft there!', 'ok');
      
      // Show modal to capture tweet URL
      setTimeout(() => {
        showTweetUrlModal(text, 'community');
      }, 1000);
    } catch (e) {
      setStatus('Failed to record post', 'err');
    }
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

function showScreenshotCard(rawInput, polishedOutput) {
  const card = el('screenshotCard');
  const before = el('screenshotBefore');
  const after = el('screenshotAfter');
  if (before) before.textContent = rawInput.slice(0, 300);
  if (after) after.textContent = polishedOutput.slice(0, 300);
  if (card) card.classList.add('visible');
}

function hideScreenshotCard() {
  const card = el('screenshotCard');
  if (card) card.classList.remove('visible');
}

async function downloadScreenshot() {
  const inner = el('screenshotInner');
  if (!inner) return;

  try {
    const canvas = await html2canvas(inner.parentElement, {
      backgroundColor: '#13151c',
      scale: 2,
    });
    const link = document.createElement('a');
    link.download = `banger-${Date.now()}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
    setStatus('Screenshot downloaded!', 'ok');
  } catch (e) {
    setStatus('Screenshot failed.', 'err');
  }
}

function wireUI() {
  console.log('Wiring UI...');
  
  // Generate button enable/disable
  const todayContext = el('today_context');
  if (todayContext) {
    todayContext.addEventListener('input', updateGenerateEnabled);
    updateGenerateEnabled();
  }

  // Screenshot download
  const downloadBtn = el('downloadScreenshot');
  if (downloadBtn) downloadBtn.onclick = downloadScreenshot;

  // Account button & usage pill -> open account modal
  const accountBtn = el('accountBtn');
  const usagePill = el('usagePill');
  
  if (accountBtn) {
    accountBtn.onclick = showAccountModal;
  }
  
  if (usagePill) {
    usagePill.onclick = showAccountModal;
    usagePill.style.cursor = 'pointer';
  }
  
  // Close modal buttons
  const closeAccount = el('closeAccount');
  const closePaywall = el('closePaywall');
  const closeTweetUrl = el('closeTweetUrl');
  const continueFreeTomorrow = el('continueFreeTomorrow');
  
  if (closeAccount) closeAccount.onclick = hideAccountModal;
  if (closePaywall) closePaywall.onclick = hidePaywallModal;
  if (closeTweetUrl) closeTweetUrl.onclick = hideTweetUrlModal;
  if (continueFreeTomorrow) {
    continueFreeTomorrow.onclick = (e) => {
      e.preventDefault();
      hidePaywallModal();
    };
  }
  
  // Tweet URL modal buttons
  const skipTweetUrl = el('skipTweetUrl');
  const saveTweetUrlBtn = el('saveTweetUrl');
  
  if (skipTweetUrl) skipTweetUrl.onclick = hideTweetUrlModal;
  if (saveTweetUrlBtn) saveTweetUrlBtn.onclick = saveTweetUrl;
  
  // Click outside modal to close
  const accountModal = el('accountModal');
  const paywallModal = el('paywallModal');
  const tweetUrlModal = el('tweetUrlModal');
  
  if (accountModal) {
    accountModal.onclick = (e) => {
      if (e.target === accountModal) hideAccountModal();
    };
  }
  if (paywallModal) {
    paywallModal.onclick = (e) => {
      if (e.target === paywallModal) hidePaywallModal();
    };
  }
  if (tweetUrlModal) {
    tweetUrlModal.onclick = (e) => {
      if (e.target === tweetUrlModal) hideTweetUrlModal();
    };
  }
  
  // Logout
  const logoutBtn = el('logoutBtn');
  if (logoutBtn) logoutBtn.onclick = logout;
  
  // Upgrade buttons
  const upgradeBtn = el('upgradeBtn');
  const accountUpgradeBtn = el('accountUpgradeBtn');
  const manageSubscription = el('manageSubscription');
  
  if (upgradeBtn) {
    upgradeBtn.onclick = () => {
      setStatus('Payment integration coming soon!', 'ok');
    };
  }
  if (accountUpgradeBtn) {
    accountUpgradeBtn.onclick = () => {
      hideAccountModal();
      showPaywallModal();
    };
  }
  if (manageSubscription) {
    manageSubscription.onclick = () => {
      setStatus('Subscription management coming soon!', 'ok');
    };
  }

  // Generate button
  const generateBtn = el('generate');
  if (generateBtn) {
    generateBtn.onclick = async () => {
      const today_context = normalize(el('today_context')?.value || '');
      const current_mood = normalize(el('current_mood')?.value || '');
      const optional_angle = normalize(el('optional_angle')?.value || '');

      if (!today_context) {
        setStatus("Today's context is required.", 'err');
        updateGenerateEnabled();
        return;
      }

      const max_options = parseInt(el('max_options')?.value || '3', 10);
      const max_chars = parseInt(el('max_chars')?.value || '280', 10);

      setStatus('Generating…');
      generateBtn.disabled = true;

      let res;
      try {
        res = await fetch('/api/generate', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ today_context, current_mood, optional_angle, max_options, max_chars })
        });
      } catch (e) {
        generateBtn.disabled = false;
        setStatus('Network error. Is the server running?', 'err');
        return;
      }

      generateBtn.disabled = false;

      // Check for rate limit / paywall
      if (res.status === 429) {
        showPaywallModal();
        setStatus('Daily limit reached. Upgrade for unlimited.', 'err');
        return;
      }

      if (!res.ok) {
        let err = {};
        try { err = await res.json(); } catch {}
        setStatus(`Generate failed: ${err.detail || res.statusText}`, 'err');
        return;
      }

      const data = await res.json();

      // Update usage after generation
      await fetchUserInfo();

      // Mode pill
      const mode = data.mode || '';
      const pill = el('modePill');
      if (pill) {
        if (mode) {
          pill.style.display = '';
          pill.textContent = `Mode: ${mode}`;
        } else {
          pill.style.display = 'none';
        }
      }

      // Render option cards
      const container = el('options');
      if (container) {
        container.innerHTML = '';
        (data.options || []).forEach((o, idx) => {
          const { card } = optionCard(o, idx);
          container.appendChild(card);
        });
      }

      // Screenshot card
      if (data.options && data.options.length > 0) {
        showScreenshotCard(today_context, data.options[0]);
      }

      fetchConfig();

      const remaining = data.remaining_writes ?? null;
      if (remaining !== null && remaining !== undefined) {
        setStatus(`Generated ${data.options?.length || 0} option(s). API writes: ${remaining}`, 'ok');
      } else {
        setStatus(`Generated ${data.options?.length || 0} option(s).`, 'ok');
      }

      if (Array.isArray(data.warnings) && data.warnings.length) {
        setStatus(data.warnings.slice(0, 2).join(' '), 'err');
      }
    };
  }

  // Copy all button
  const copyAllBtn = el('copyAll');
  if (copyAllBtn) {
    copyAllBtn.onclick = async () => {
      const all = getAllOptionTexts();
      if (!all.length) return setStatus('No options to copy.', 'err');

      const body = all.map((t, i) => `Option ${i + 1}\n${t}`).join('\n\n---\n\n');
      try {
        await navigator.clipboard.writeText(body);
        setStatus('Copied all options.', 'ok');
        setTimeout(() => setStatus('', ''), 1200);
      } catch {
        setStatus('Clipboard failed.', 'err');
      }
    };
  }

  // Email all button
  const emailAllBtn = el('emailAll');
  if (emailAllBtn) {
    emailAllBtn.onclick = async () => {
      const options = getAllOptionTexts();
      if (!options.length) return setStatus('No options to email.', 'err');

      const subject = (el('email_subject')?.value || 'Banger drafts').trim();

      setStatus('Sending email…');
      try {
        const res = await fetch('/api/email', {
          method: 'POST',
          headers: getAuthHeaders(),
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
      } catch (e) {
        setStatus('Email failed.', 'err');
      }
    };
  }

  // Clear button
  const clearBtn = el('clear');
  if (clearBtn) {
    clearBtn.onclick = () => {
      const ctx = el('today_context');
      const mood = el('current_mood');
      const angle = el('optional_angle');
      const options = el('options');
      const modePill = el('modePill');
      
      if (ctx) ctx.value = '';
      if (mood) mood.value = '';
      if (angle) angle.value = '';
      if (options) options.innerHTML = '';
      if (modePill) modePill.style.display = 'none';
      setStatus('', '');
      updateGenerateEnabled();
      hideScreenshotCard();
    };
  }
  
  console.log('UI wired successfully');
}

function getAuthHeaders() {
  const token = localStorage.getItem('access_token');
  const headers = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', async () => {
  console.log('DOM loaded, checking auth...');
  const ok = await ensureAuthed();
  if (!ok) return;

  console.log('Auth OK, initializing...');
  wireUI();
  await fetchConfig();
  await fetchUserInfo();
  console.log('Initialization complete');
});
