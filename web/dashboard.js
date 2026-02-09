// ============================================
// DASHBOARD CONTROLLER
// ============================================

const el = (id) => document.getElementById(id);

// State
let currentUser = null;
let pendingTweetData = null;
let xConnected = false;

// ============================================
// UTILITY FUNCTIONS
// ============================================

function showNotification(message, type = 'ok') {
    setStatus(message, type === 'error' ? 'err' : type);
    if (type !== 'error') {
        setTimeout(() => setStatus('', ''), 3000);
    }
}

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

function getAuthHeaders() {
    const token = localStorage.getItem('access_token');
    const headers = { 'Content-Type': 'application/json' };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
}

// ============================================
// NAVIGATION
// ============================================

function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item[data-section]');
    const sections = document.querySelectorAll('.content-section');
    const pageTitle = el('pageTitle');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const sectionId = item.dataset.section;
            
            // Update active nav
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            
            // Show section
            sections.forEach(section => section.classList.remove('active'));
            const targetSection = el(`section-${sectionId}`);
            if (targetSection) {
                targetSection.classList.add('active');
            }
            
            // Update title
            if (pageTitle) {
                pageTitle.textContent = item.querySelector('.nav-label')?.textContent || 'Dashboard';
            }

            // Close mobile sidebar
            closeMobileSidebar();
            
            // Update URL hash
            window.location.hash = sectionId;
        });
    });

    // Handle initial hash
    const hash = window.location.hash.slice(1);
    if (hash) {
        const targetNav = document.querySelector(`.nav-item[data-section="${hash}"]`);
        if (targetNav) {
            targetNav.click();
        }
    }

    // Go to connections button
    const goToConnections = el('goToConnections');
    if (goToConnections) {
        goToConnections.addEventListener('click', () => {
            const connectionsNav = document.querySelector('.nav-item[data-section="connections"]');
            if (connectionsNav) connectionsNav.click();
        });
    }
}

// ============================================
// SIDEBAR TOGGLE
// ============================================

function initSidebar() {
    const sidebar = el('sidebar');
    const toggle = el('sidebarToggle');
    const mobileBtn = el('mobileMenuBtn');

    // Desktop toggle
    if (toggle) {
        toggle.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
            localStorage.setItem('sidebar_collapsed', sidebar.classList.contains('collapsed'));
        });

        // Restore state
        if (localStorage.getItem('sidebar_collapsed') === 'true') {
            sidebar.classList.add('collapsed');
        }
    }

    // Mobile toggle
    if (mobileBtn) {
        mobileBtn.addEventListener('click', () => {
            sidebar.classList.add('open');
            showOverlay();
        });
    }
}

function showOverlay() {
    let overlay = document.querySelector('.sidebar-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        document.body.appendChild(overlay);
    }
    overlay.classList.add('visible');
    overlay.addEventListener('click', closeMobileSidebar);
}

function closeMobileSidebar() {
    const sidebar = el('sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('visible');
}

// ============================================
// USAGE & USER INFO
// ============================================

function updateUsageDisplay(used, limit, isPro) {
    const usageDisplay = el('usageDisplay');
    const usageIcon = el('usageIcon');
    const usagePill = el('usagePill');

    if (usageDisplay && usageIcon && usagePill) {
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

    // Update settings page
    updateSettingsUsage(used, limit, isPro);
}

function updateSettingsUsage(used, limit, isPro) {
    const usageBar = el('settingsUsageBar');
    const usageText = el('settingsUsage');
    const usageCard = el('usageCard');

    if (isPro && usageCard) {
        usageCard.style.display = 'none';
    } else if (usageCard) {
        usageCard.style.display = 'block';
        const percentage = Math.min(100, (used / limit) * 100);
        
        if (usageBar) {
            usageBar.style.width = `${percentage}%`;
            if (percentage >= 100) {
                usageBar.style.background = 'var(--danger)';
            } else if (percentage >= 66) {
                usageBar.style.background = '#f59e0b';
            } else {
                usageBar.style.background = 'var(--accent)';
            }
        }
        
        if (usageText) {
            usageText.textContent = `${used} / ${limit} generations today`;
        }
    }
}

function updateUserUI(user) {
    currentUser = user;
    const isPro = user.plan === 'pro' || user.is_pro;
    const used = user.daily_usage ?? 0;
    const limit = user.daily_limit ?? 3;

    // Sidebar user card
    const userEmail = el('userEmail');
    const userAvatar = el('userAvatar');
    const userPlan = el('userPlan');

    if (userEmail) userEmail.textContent = user.email || 'Unknown';
    if (userAvatar) userAvatar.textContent = (user.email || '?')[0].toUpperCase();
    if (userPlan) userPlan.textContent = isPro ? 'Pro' : 'Free';

    // Settings
    const settingsEmail = el('settingsEmail');
    const settingsPlan = el('settingsPlan');

    if (settingsEmail) settingsEmail.textContent = user.email || 'Unknown';
    if (settingsPlan) {
        settingsPlan.textContent = isPro ? 'Pro' : 'Free';
        settingsPlan.className = 'plan-badge ' + (isPro ? 'pro' : 'free');
    }

    // Hide upgrade nav for pro users
    const upgradeNavItem = el('upgradeNavItem');
    if (upgradeNavItem) {
        upgradeNavItem.style.display = isPro ? 'none' : 'flex';
    }

    // Update usage
    updateUsageDisplay(used, limit, isPro);
}

async function fetchUserInfo() {
    const token = localStorage.getItem('access_token');
    if (!token) return null;

    try {
        const res = await fetch('/api/auth/me', {
            headers: { Authorization: `Bearer ${token}` },
        });

        if (!res.ok) return null;

        const user = await res.json();
        updateUserUI(user);
        return user;
    } catch (e) {
        console.error('Failed to fetch user info:', e);
        return null;
    }
}

// ============================================
// AUTH
// ============================================

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
            window.location.href = './auth.html';
            return false;
        }

        return true;
    } catch (_) {
        window.location.href = './auth.html';
        return false;
    }
}

function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_email');
    window.location.href = './auth.html';
}

// ============================================
// GENERATE FUNCTIONALITY
// ============================================

function updateGenerateEnabled() {
    const btn = el('generate');
    const ctx = el('today_context');
    if (!btn || !ctx) return;

    const hasContext = normalize(ctx.value).length > 0;
    btn.disabled = !hasContext;
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
    btnCopy.textContent = '📋 Copy';
    btnCopy.onclick = async () => {
        try {
            await navigator.clipboard.writeText(ta.value);
            showNotification('Copied to clipboard!', 'ok');
        } catch {
            showNotification('Clipboard failed.', 'error');
        }
    };

    // Post via API button
    const btnPost = document.createElement('button');
    btnPost.className = 'btn primary';
    btnPost.textContent = '🚀 Post via API';
    btnPost.onclick = async () => {
        const text = (ta.value || '').trim();
        if (!text) return showNotification('Empty draft.', 'error');

        setStatus('Posting via API…');
        try {
            const res = await fetch('/api/post', {
                method: 'POST',
                headers: { ...getAuthHeaders(), 'X-Use-X-Api': '1' },
                body: JSON.stringify({ text, method: 'api' })
            });
            const data = await res.json();
            if (data.success) {
                showNotification(`Posted! Tweet ID: ${data.tweet_id}`, 'ok');
            } else {
                showNotification(`API failed: ${data.error || 'Unknown error'}`, 'error');
            }
        } catch (e) {
            showNotification('Network error posting', 'error');
        }
    };

    // Open in X button
    const btnIntent = document.createElement('button');
    btnIntent.className = 'btn';
    btnIntent.textContent = '↗ Open in X';
    btnIntent.onclick = async () => {
        const text = (ta.value || '').trim();
        if (!text) return showNotification('Empty draft.', 'error');

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
            showNotification('Opened X composer.', 'ok');

            setTimeout(() => {
                showTweetUrlModal(text, 'manual');
            }, 1000);
        } catch (e) {
            showNotification('Failed to open X', 'error');
        }
    };

    actions.appendChild(btnCopy);
    actions.appendChild(btnPost);
    actions.appendChild(btnIntent);

    card.appendChild(top);
    card.appendChild(ta);
    card.appendChild(actions);
    return { card, getText: () => (ta.value || '').trim() };
}

function getAllOptionTexts() {
    const cards = Array.from(document.querySelectorAll('.card textarea'));
    return cards.map(t => (t.value || '').trim()).filter(Boolean);
}

// ============================================
// MODALS
// ============================================

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
            showNotification('Tweet tracked successfully!', 'ok');
        } catch (e) {
            showNotification('Failed to save tweet URL', 'error');
        }
    }

    hideTweetUrlModal();
}

function showScreenshotCard(rawInput, polishedOutput) {
    const modal = el('screenshotModal');
    const before = el('screenshotBefore');
    const after = el('screenshotAfter');
    if (before) before.textContent = rawInput.slice(0, 300);
    if (after) after.textContent = polishedOutput.slice(0, 300);
    if (modal) modal.style.display = 'flex';
}

function hideScreenshotCard() {
    const modal = el('screenshotModal');
    if (modal) modal.style.display = 'none';
}

async function downloadScreenshot() {
    const inner = el('screenshotInner');
    if (!inner || typeof html2canvas === 'undefined') return;

    try {
        const canvas = await html2canvas(inner.parentElement, {
            backgroundColor: '#13151c',
            scale: 2,
        });
        const link = document.createElement('a');
        link.download = `banger-${Date.now()}.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();
        showNotification('Screenshot downloaded!', 'ok');
    } catch (e) {
        showNotification('Screenshot failed.', 'error');
    }
}

// ============================================
// X CONNECTION
// ============================================

async function checkXConnectionStatus() {
    const token = localStorage.getItem('access_token');
    if (!token) return { connected: false };

    try {
        const response = await fetch('/api/x/status', {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            return await response.json();
        }
    } catch (error) {
        console.error('Failed to check X connection:', error);
    }

    return { connected: false };
}

async function connectXAccount() {
    const token = localStorage.getItem('access_token');
    if (!token) {
        showNotification('Please log in first', 'error');
        return;
    }

    try {
        const response = await fetch('/api/x/auth-url', {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) {
            throw new Error('Failed to get auth URL');
        }

        const data = await response.json();

        const width = 600;
        const height = 700;
        const left = (window.innerWidth - width) / 2;
        const top = (window.innerHeight - height) / 2;

        window.open(
            data.url,
            'Connect X Account',
            `width=${width},height=${height},left=${left},top=${top}`
        );

        window.addEventListener('message', async function handler(event) {
            if (event.data.type === 'X_CONNECTED') {
                window.removeEventListener('message', handler);
                showNotification(`Connected as @${event.data.username}!`, 'ok');
                updateXConnectionUI(true, event.data.username);
            } else if (event.data.type === 'X_AUTH_ERROR') {
                window.removeEventListener('message', handler);
                showNotification('Failed to connect X account', 'error');
            }
        });

    } catch (error) {
        showNotification(error.message || 'Failed to connect X account', 'error');
    }
}

async function disconnectXAccount() {
    const token = localStorage.getItem('access_token');
    if (!token) return;

    if (!confirm('Are you sure you want to disconnect your X account?')) {
        return;
    }

    try {
        const response = await fetch('/api/x/disconnect', {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            showNotification('X account disconnected', 'ok');
            updateXConnectionUI(false);
        } else {
            throw new Error('Failed to disconnect');
        }
    } catch (error) {
        showNotification('Failed to disconnect X account', 'error');
    }
}

function updateXConnectionUI(connected, username = null) {
    xConnected = connected;

    // Connection card
    const connectBtn = el('connect-x-btn');
    const disconnectBtn = el('disconnect-x-btn');
    const xConnectionStatus = el('xConnectionStatus');
    const xStatusIndicator = el('xStatusIndicator');

    if (connectBtn) connectBtn.style.display = connected ? 'none' : 'inline-flex';
    if (disconnectBtn) disconnectBtn.style.display = connected ? 'inline-flex' : 'none';
    if (xConnectionStatus) {
        xConnectionStatus.textContent = connected ? `Connected as @${username}` : 'Not connected';
    }
    if (xStatusIndicator) {
        xStatusIndicator.classList.toggle('connected', connected);
    }

    // Sidebar status dot
    const xStatusDot = el('xStatusDot');
    if (xStatusDot) {
        xStatusDot.classList.toggle('connected', connected);
    }

    // Analytics section
    const analyticsLock = el('analyticsLock');
    const analyticsRequiresConnection = el('analyticsRequiresConnection');
    const analyticsContainer = el('analyticsContainer');

    if (analyticsLock) analyticsLock.style.display = connected ? 'none' : 'inline';
    if (analyticsRequiresConnection) analyticsRequiresConnection.style.display = connected ? 'none' : 'block';
    if (analyticsContainer) analyticsContainer.style.display = connected ? 'block' : 'none';
}

async function initXConnection() {
    const status = await checkXConnectionStatus();
    updateXConnectionUI(status.connected, status.x_username);
}

// ============================================
// ANALYTICS
// ============================================

async function analyzeTweet(tweetUrl) {
    const token = localStorage.getItem('access_token');
    if (!token) {
        showNotification('Please log in first', 'error');
        return null;
    }

    const analyzeBtn = el('analyze-btn');
    const resultsDiv = el('analytics-results');

    if (analyzeBtn) {
        analyzeBtn.disabled = true;
        analyzeBtn.innerHTML = '<span class="spinner-small"></span> Analyzing...';
    }

    try {
        const response = await fetch('/api/analytics/tweet', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ tweet_url: tweetUrl })
        });

        const data = await response.json();

        if (response.status === 429) {
            if (resultsDiv) {
                resultsDiv.innerHTML = `
                    <div class="analytics-error rate-limited">
                        <p>⏳ Rate Limited</p>
                        <p class="error-hint">X API free tier allows 1 request per 15 minutes.</p>
                    </div>
                `;
            }
            return null;
        }

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to analyze tweet');
        }

        displayAnalyticsResults(data);
        return data;

    } catch (error) {
        showNotification(error.message, 'error');
        if (resultsDiv) {
            resultsDiv.innerHTML = `
                <div class="analytics-error">
                    <p>❌ ${error.message}</p>
                    <p class="error-hint">Make sure the tweet URL is valid.</p>
                </div>
            `;
        }
        return null;
    } finally {
        if (analyzeBtn) {
            analyzeBtn.disabled = false;
            analyzeBtn.innerHTML = '📊 Analyze';
        }
    }
}

function displayAnalyticsResults(data) {
    const resultsDiv = el('analytics-results');
    if (!resultsDiv) return;

    const { metrics, analysis, text, created_at } = data;

    const formattedDate = created_at
        ? new Date(created_at).toLocaleDateString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        })
        : 'Unknown date';

    resultsDiv.innerHTML = `
        <div class="analytics-card">
            <div class="tweet-preview">
                <p class="tweet-text">${escapeHtml(text)}</p>
                <span class="tweet-date">${formattedDate}</span>
            </div>
            
            <div class="performance-badge ${getPerformanceClass(analysis.engagement_rate)}">
                ${analysis.performance_level}
            </div>
            
            <div class="metrics-grid">
                <div class="metric-item">
                    <span class="metric-icon">👁️</span>
                    <span class="metric-value">${formatNumber(metrics.impressions)}</span>
                    <span class="metric-label">Impressions</span>
                </div>
                <div class="metric-item">
                    <span class="metric-icon">❤️</span>
                    <span class="metric-value">${formatNumber(metrics.likes)}</span>
                    <span class="metric-label">Likes</span>
                </div>
                <div class="metric-item">
                    <span class="metric-icon">🔁</span>
                    <span class="metric-value">${formatNumber(metrics.retweets)}</span>
                    <span class="metric-label">Retweets</span>
                </div>
                <div class="metric-item">
                    <span class="metric-icon">💬</span>
                    <span class="metric-value">${formatNumber(metrics.replies)}</span>
                    <span class="metric-label">Replies</span>
                </div>
                <div class="metric-item">
                    <span class="metric-icon">🔖</span>
                    <span class="metric-value">${formatNumber(metrics.bookmarks)}</span>
                    <span class="metric-label">Bookmarks</span>
                </div>
                <div class="metric-item">
                    <span class="metric-icon">💭</span>
                    <span class="metric-value">${formatNumber(metrics.quotes)}</span>
                    <span class="metric-label">Quotes</span>
                </div>
            </div>
            
            <div class="engagement-stats">
                <div class="stat-row">
                    <span>Engagement Rate</span>
                    <span class="stat-value">${analysis.engagement_rate}%</span>
                </div>
                <div class="stat-row">
                    <span>Viral Score</span>
                    <span class="stat-value">${analysis.viral_score}%</span>
                </div>
            </div>
            
            <div class="analytics-tip">
                <span class="tip-icon">💡</span>
                <p>${analysis.tip}</p>
            </div>
        </div>
    `;
}

function getPerformanceClass(engagementRate) {
    if (engagementRate >= 5) return 'performance-viral';
    if (engagementRate >= 3) return 'performance-excellent';
    if (engagementRate >= 1.5) return 'performance-good';
    if (engagementRate >= 0.5) return 'performance-average';
    return 'performance-low';
}

function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

// ============================================
// WIRE ALL UI
// ============================================

function wireUI() {
    // Generate button
    const todayContext = el('today_context');
    if (todayContext) {
        todayContext.addEventListener('input', updateGenerateEnabled);
        updateGenerateEnabled();
    }

    // Generate
    const generateBtn = el('generate');
    if (generateBtn) {
        generateBtn.onclick = async () => {
            const today_context = normalize(el('today_context')?.value || '');
            const current_mood = normalize(el('current_mood')?.value || '');
            const optional_angle = normalize(el('optional_angle')?.value || '');

            if (!today_context) {
                showNotification("Today's context is required.", 'error');
                return;
            }

            const max_options = parseInt(el('max_options')?.value || '3', 10);
            const max_chars = parseInt(el('max_chars')?.value || '280', 10);

            setStatus('Generating…');
            generateBtn.disabled = true;

            try {
                const res = await fetch('/api/generate', {
                    method: 'POST',
                    headers: getAuthHeaders(),
                    body: JSON.stringify({ today_context, current_mood, optional_angle, max_options, max_chars })
                });

                generateBtn.disabled = false;

                if (res.status === 429) {
                    showPaywallModal();
                    setStatus('Daily limit reached.', 'err');
                    return;
                }

                if (!res.ok) {
                    let err = {};
                    try { err = await res.json(); } catch { }
                    showNotification(`Generate failed: ${err.detail || res.statusText}`, 'error');
                    return;
                }

                const data = await res.json();
                await fetchUserInfo();

                // Render options
                const container = el('options');
                if (container) {
                    container.innerHTML = '';
                    (data.options || []).forEach((o, idx) => {
                        const { card } = optionCard(o, idx);
                        container.appendChild(card);
                    });
                }

                if (data.options && data.options.length > 0) {
                    showScreenshotCard(today_context, data.options[0]);
                }

                showNotification(`Generated ${data.options?.length || 0} option(s).`, 'ok');

            } catch (e) {
                generateBtn.disabled = false;
                showNotification('Network error.', 'error');
            }
        };
    }

    // Clear
    const clearBtn = el('clear');
    if (clearBtn) {
        clearBtn.onclick = () => {
            if (el('today_context')) el('today_context').value = '';
            if (el('current_mood')) el('current_mood').value = '';
            if (el('optional_angle')) el('optional_angle').value = '';
            if (el('options')) el('options').innerHTML = `
                <div class="options-empty">
                    <span class="empty-icon">💡</span>
                    <p>Your generated posts will appear here</p>
                </div>
            `;
            setStatus('', '');
            hideScreenshotCard();
        };
    }

    // Copy all
    const copyAllBtn = el('copyAll');
    if (copyAllBtn) {
        copyAllBtn.onclick = async () => {
            const all = getAllOptionTexts();
            if (!all.length) return showNotification('No options to copy.', 'error');

            const body = all.map((t, i) => `Option ${i + 1}\n${t}`).join('\n\n---\n\n');
            try {
                await navigator.clipboard.writeText(body);
                showNotification('Copied all options.', 'ok');
            } catch {
                showNotification('Clipboard failed.', 'error');
            }
        };
    }

    // Email all
    const emailAllBtn = el('emailAll');
    if (emailAllBtn) {
        emailAllBtn.onclick = async () => {
            const options = getAllOptionTexts();
            if (!options.length) return showNotification('No options to email.', 'error');

            const subject = (el('email_subject')?.value || 'Banger drafts').trim();

            setStatus('Sending email…');
            try {
                const res = await fetch('/api/email', {
                    method: 'POST',
                    headers: getAuthHeaders(),
                    body: JSON.stringify({ subject, options })
                });

                if (!res.ok) {
                    showNotification('Email failed.', 'error');
                    return;
                }
                showNotification('Email sent.', 'ok');
            } catch (e) {
                showNotification('Email failed.', 'error');
            }
        };
    }

    // Screenshot modal
    const closeScreenshot = el('closeScreenshot');
    const closeScreenshotBtn = el('closeScreenshotBtn');
    const screenshotModal = el('screenshotModal');
    const downloadBtn = el('downloadScreenshot');

    if (closeScreenshot) closeScreenshot.addEventListener('click', hideScreenshotCard);
    if (closeScreenshotBtn) closeScreenshotBtn.addEventListener('click', hideScreenshotCard);
    if (screenshotModal) {
        screenshotModal.addEventListener('click', (e) => {
            if (e.target === screenshotModal) hideScreenshotCard();
        });
    }
    if (downloadBtn) downloadBtn.onclick = downloadScreenshot;

    // Paywall modal
    const closePaywall = el('closePaywall');
    const paywallModal = el('paywallModal');
    const continueFreeTomorrow = el('continueFreeTomorrow');

    if (closePaywall) closePaywall.onclick = hidePaywallModal;
    if (continueFreeTomorrow) {
        continueFreeTomorrow.onclick = (e) => {
            e.preventDefault();
            hidePaywallModal();
        };
    }
    if (paywallModal) {
        paywallModal.onclick = (e) => {
            if (e.target === paywallModal) hidePaywallModal();
        };
    }

    // Tweet URL modal
    const closeTweetUrl = el('closeTweetUrl');
    const tweetUrlModal = el('tweetUrlModal');
    const skipTweetUrl = el('skipTweetUrl');
    const saveTweetUrlBtn = el('saveTweetUrl');

    if (closeTweetUrl) closeTweetUrl.onclick = hideTweetUrlModal;
    if (skipTweetUrl) skipTweetUrl.onclick = hideTweetUrlModal;
    if (saveTweetUrlBtn) saveTweetUrlBtn.onclick = saveTweetUrl;
    if (tweetUrlModal) {
        tweetUrlModal.onclick = (e) => {
            if (e.target === tweetUrlModal) hideTweetUrlModal();
        };
    }

    // Logout buttons
    const logoutBtn = el('logoutBtn');
    const settingsLogout = el('settingsLogout');
    if (logoutBtn) logoutBtn.onclick = logout;
    if (settingsLogout) settingsLogout.onclick = logout;

    // Upgrade buttons
    const upgradeBtn = el('upgradeBtn');
    const upgradeBtnMain = el('upgradeBtnMain');
    if (upgradeBtn) {
        upgradeBtn.onclick = () => showNotification('Payment integration coming soon!', 'ok');
    }
    if (upgradeBtnMain) {
        upgradeBtnMain.onclick = () => showNotification('Payment integration coming soon!', 'ok');
    }

    // X connection
    const connectXBtn = el('connect-x-btn');
    const disconnectXBtn = el('disconnect-x-btn');
    if (connectXBtn) connectXBtn.addEventListener('click', connectXAccount);
    if (disconnectXBtn) disconnectXBtn.addEventListener('click', disconnectXAccount);

    // Analytics form
    const analyzeForm = el('analyze-tweet-form');
    if (analyzeForm) {
        analyzeForm.addEventListener('submit', async function (e) {
            e.preventDefault();
            const tweetUrl = el('tweet-url-input')?.value.trim();
            if (tweetUrl) {
                await analyzeTweet(tweetUrl);
            }
        });
    }
}

// ============================================
// INITIALIZE
// ============================================

document.addEventListener('DOMContentLoaded', async () => {
    const ok = await ensureAuthed();
    if (!ok) return;

    initNavigation();
    initSidebar();
    wireUI();
    await fetchUserInfo();
    await initXConnection();
});