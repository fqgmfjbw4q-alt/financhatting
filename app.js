// ---------------------------
// Global state
// ---------------------------
let lightweightChart = null;
let candlestickSeries = null;

let currentSymbol = null;
let currentSymbolName = null;
let currentPeriod = 'daily';

let currentUser = null;
let currentPostId = null;

// API base (same-origin)
const API_BASE = window.location.origin;

// ---------------------------
// Helpers
// ---------------------------
async function apiCall(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;

  const opts = {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    }
  };

  const res = await fetch(url, opts);

  // 204 -> no content
  if (res.status === 204) return {};

  // Try parse JSON safely
  let data = {};
  try {
    data = await res.json();
  } catch (e) {
    data = {};
  }

  // Let caller handle 401/404 gracefully sometimes
  if (!res.ok && res.status !== 401 && res.status !== 404) {
    throw new Error(`HTTP ${res.status}`);
  }
  return data;
}

function escHtml(str) {
  return (str || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function showSection(section) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-links span').forEach(l => l.classList.remove('active'));

  const secEl = document.getElementById(section + '-section');
  if (secEl) secEl.classList.add('active');

  // set nav active
  const navLinks = document.querySelectorAll('.nav-links span');
  if (navLinks.length) {
    if (section === 'market') navLinks[0].classList.add('active');
    if (section === 'feed') navLinks[1].classList.add('active');
    if (section === 'profile') navLinks[2].classList.add('active');
  }

  if (section === 'feed') fetchFeed();
  if (section === 'profile') loadProfile();
}

function ensureLoggedIn(actionName = 'Bu işlem') {
  if (!currentUser) {
    alert(`${actionName} için giriş yapmalısınız.`);
    return false;
  }
  return true;
}

// ---------------------------
// Auth UI
// ---------------------------
function closeAuthModal() {
  document.getElementById('auth-modal').style.display = 'none';
}

function openAuth(mode) {
  const modal = document.getElementById('auth-modal');
  modal.style.display = 'flex';

  const title = document.getElementById('auth-title');
  const btn = document.getElementById('af-btn');

  const fn = document.getElementById('af-fn');
  fn.style.display = (mode === 'reg') ? 'block' : 'none';

  title.innerText = (mode === 'reg') ? '🎯 Yeni Hesap' : '🔐 Giriş Yap';
  btn.innerText = (mode === 'reg') ? 'Kaydol' : 'Giriş Yap';

  btn.onclick = async () => {
    const payload = {
      full_name: document.getElementById('af-fn').value,
      username: document.getElementById('af-un').value,
      password: document.getElementById('af-ps').value
    };

    try {
      const data = await apiCall('/api/' + (mode === 'reg' ? 'register' : 'login'), {
        method: 'POST',
        body: JSON.stringify(payload)
      });

      if (data && data.error) {
        alert('❌ ' + data.error);
        return;
      }

      // reload to re-init session UI
      location.reload();
    } catch (err) {
      alert('Bağlantı hatası!');
    }
  };
}

async function logout() {
  try {
    await apiCall('/api/logout', { method: 'POST' });
    location.reload();
  } catch (e) {
    alert('Çıkış yapılamadı!');
  }
}

// ---------------------------
// Market + Economic Calendar
// ---------------------------
async function fetchEconomicCalendar() {
  const box = document.getElementById('economic-calendar');
  try {
    const data = await apiCall('/api/economic-calendar');
    let html = '';
    for (const k in data) {
      const item = data[k];
      html += `
        <div class="card" style="cursor:default;">
          <div style="font-size:28px;">${item.icon || '📌'}</div>
          <div style="color:#94a3b8;font-weight:700;margin-top:6px;">${escHtml(item.name || '')}</div>
          <div style="font-size:18px;font-weight:900;margin-top:8px;color:${item.color || '#3b82f6'};">
            ${escHtml(item.current || '')}
          </div>
          <div style="margin-top:8px;color:#94a3b8;font-size:12px;">
            📅 ${escHtml(item.next_meeting || item.next_release || '')}
          </div>
          <div style="margin-top:8px;color:#94a3b8;font-size:12px;">
            ${escHtml(item.description || '')}
          </div>
        </div>
      `;
    }
    box.innerHTML = html || '<p class="muted center">Veri yok</p>';
  } catch (e) {
    box.innerHTML = '<p class="muted center">Veri yüklenemedi</p>';
  }
}

async function fetchMarket() {
  const box = document.getElementById('market-list');
  try {
    const data = await apiCall('/api/market-data');
    if (data.error) throw new Error('market');

    let html = '';
    for (const key in data) {
      const item = data[key];
      html += `
        <div class="card" onclick="openAsset('${key}', '${escHtml(item.name)}')">
          <div style="font-size:34px">${item.logo || '📈'}</div>
          <div style="color:#94a3b8;font-weight:700;margin-top:6px;">${escHtml(item.name)}</div>
          <div class="price">${escHtml(item.value)}</div>
        </div>
      `;
    }
    box.innerHTML = html || '<p class="muted center">Veri yok</p>';
  } catch (e) {
    box.innerHTML = '<p class="muted center">Veri yüklenemedi</p>';
  }
}

// ---------------------------
// Asset modal + chart
// ---------------------------
function openAsset(symbol, name) {
  currentSymbol = symbol;
  currentSymbolName = name;

  document.getElementById('asset-modal').style.display = 'flex';
  document.getElementById('modal-title').innerText = `${name} - Mum Grafiği`;

  loadCandlestickChart(symbol, currentPeriod);
  loadComments(symbol);
}

function closeAssetModal() {
  document.getElementById('asset-modal').style.display = 'none';
}

async function loadCandlestickChart(symbol, period) {
  const container = document.getElementById('candlestick-chart-container');
  container.innerHTML = '';

  try {
    const data = await apiCall(`/api/candlestick/${symbol}?period=${period}`);
    if (data.error) {
      alert(data.error);
      return;
    }

    // reset chart
    if (lightweightChart) {
      try { lightweightChart.remove(); } catch (_) {}
      lightweightChart = null;
      candlestickSeries = null;
    }

    lightweightChart = LightweightCharts.createChart(container, {
      width: container.clientWidth,
      height: 420,
      layout: {
        background: { color: '#1c2128' },
        textColor: '#94a3b8'
      },
      grid: {
        vertLines: { color: '#30363d' },
        horzLines: { color: '#30363d' }
      },
      rightPriceScale: { borderColor: '#30363d' },
      timeScale: { borderColor: '#30363d', timeVisible: true }
    });

    candlestickSeries = lightweightChart.addCandlestickSeries();

    const chartData = (data.data || []).map(d => ({
      time: d.time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close
    }));

    candlestickSeries.setData(chartData);
    lightweightChart.timeScale().fitContent();

    // handle resize
    window.addEventListener('resize', () => {
      if (!lightweightChart) return;
      lightweightChart.applyOptions({ width: container.clientWidth });
    });

  } catch (e) {
    console.error('Chart error:', e);
    alert('Grafik yüklenemedi!');
  }
}

// ---------------------------
// Asset comments
// ---------------------------
async function loadComments(symbol) {
  const box = document.getElementById('comments-list');
  try {
    const data = await apiCall(`/api/asset-comments/${symbol}`);
    let html = '';

    (data || []).forEach(c => {
      const isOwner = currentUser && c.username === currentUser;
      html += `
        <div class="post" style="cursor:default;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <b style="color:#3b82f6">@${escHtml(c.username)}</b>
              <span class="muted" style="font-size:12px;margin-left:8px;">${escHtml(c.timestamp)}</span>
            </div>
            ${isOwner ? `<button class="btn secondary" style="padding:6px 10px;border-color:#ef4444;color:#ef4444"
              onclick="deleteAssetComment(${c.id})">Sil</button>` : ''}
          </div>
          <div style="margin-top:10px;">${escHtml(c.content)}</div>
        </div>
      `;
    });

    box.innerHTML = html || '<p class="muted center">Henüz yorum yok.</p>';

    // show comment box only if logged in
    document.getElementById('comment-box').style.display = currentUser ? 'block' : 'none';

  } catch (e) {
    box.innerHTML = '<p class="muted center">Yorumlar yüklenemedi.</p>';
  }
}

async function submitComment() {
  if (!ensureLoggedIn('Yorum yapmak')) return;

  const el = document.getElementById('comment-input');
  const content = (el.value || '').trim();
  if (!content) return alert('Lütfen bir yorum yazın!');

  try {
    const data = await apiCall('/api/asset-comment', {
      method: 'POST',
      body: JSON.stringify({ symbol: currentSymbol, content })
    });

    if (data.error) return alert(data.error);

    el.value = '';
    loadComments(currentSymbol);
  } catch (e) {
    alert('Yorum paylaşılamadı!');
  }
}

async function deleteAssetComment(commentId) {
  if (!ensureLoggedIn('Silme')) return;
  if (!confirm('Bu yorumu silmek istediğinize emin misiniz?')) return;

  try {
    const data = await apiCall(`/api/asset-comment/${commentId}`, { method: 'DELETE' });
    if (data.error) return alert(data.error);
    loadComments(currentSymbol);
  } catch (e) {
    alert('Yorum silinemedi!');
  }
}

// ---------------------------
// Feed / Posts
// ---------------------------
async function fetchFeed() {
  const box = document.getElementById('global-feed');

  try {
    const data = await apiCall('/api/feed');

    let html = '';
    (data || []).forEach(p => {
      const isOwner = currentUser && p.user === currentUser;

      html += `
        <div class="post" onclick="openPostDetail(${p.id})">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <b style="color:#3b82f6">@${escHtml(p.user)}</b>
              <span class="muted" style="font-size:12px;margin-left:8px;">${escHtml(p.timestamp)}</span>
            </div>
            ${isOwner ? `
              <div>
                <button class="btn secondary" style="padding:6px 10px" onclick="event.stopPropagation(); editPost(${p.id}, '${escHtml(p.content).replaceAll("&#039;","\\'")}')">Düzenle</button>
                <button class="btn secondary" style="padding:6px 10px;border-color:#ef4444;color:#ef4444"
                  onclick="event.stopPropagation(); deletePost(${p.id})">Sil</button>
              </div>
            ` : ''}
          </div>
          <div style="margin-top:10px;">${escHtml(p.content)}</div>
          <div class="muted" style="margin-top:10px;font-size:12px;">💬 ${p.comment_count} yorum</div>
        </div>
      `;
    });

    box.innerHTML = html || '<p class="muted center">Henüz gönderi yok. İlk sen ol! 🚀</p>';

    // post box only for logged-in
    document.getElementById('post-box').style.display = currentUser ? 'block' : 'none';

  } catch (e) {
    box.innerHTML = '<p class="muted center">Feed yüklenemedi</p>';
  }
}

async function submitPost() {
  if (!ensureLoggedIn('Gönderi paylaşmak')) return;

  const el = document.getElementById('post-input');
  const content = (el.value || '').trim();
  if (!content) return alert('Lütfen bir içerik yazın!');

  try {
    const data = await apiCall('/api/post', {
      method: 'POST',
      body: JSON.stringify({ content })
    });
    if (data.error) return alert(data.error);

    el.value = '';
    fetchFeed();
    loadProfile(); // profile posts might change
  } catch (e) {
    alert('Gönderi paylaşılamadı!');
  }
}

async function deletePost(postId) {
  if (!ensureLoggedIn('Silme')) return;
  if (!confirm('Bu gönderiyi silmek istediğinize emin misiniz?')) return;

  try {
    const data = await apiCall(`/api/post/${postId}`, { method: 'DELETE' });
    if (data.error) return alert(data.error);

    fetchFeed();
    loadProfile();
  } catch (e) {
    alert('Gönderi silinemedi!');
  }
}

async function editPost(postId, currentContent) {
  if (!ensureLoggedIn('Düzenleme')) return;

  const newContent = prompt('Gönderiyi düzenle:', currentContent);
  if (!newContent || !newContent.trim()) return;

  try {
    const data = await apiCall(`/api/post/${postId}`, {
      method: 'PUT',
      body: JSON.stringify({ content: newContent })
    });
    if (data.error) return alert(data.error);

    fetchFeed();
    loadProfile();
  } catch (e) {
    alert('Gönderi düzenlenemedi!');
  }
}

// ---------------------------
// Post detail (simple: open modal not in HTML)
// For this minimal HTML we just scroll; if you want modal, söyle.
// ---------------------------
function openPostDetail(postId) {
  // Minimal sürüm: yorumlar için ayrı modal yok.
  // İstersen bir sonraki adımda post modal + post yorum UI ekleriz.
  currentPostId = postId;
  alert('Bu basit sürümde post detay modalı yok. İstersen ekleyeyim (post yorum sistemi UI ile).');
}

// ---------------------------
// Profile
// ---------------------------
async function loadProfile() {
  if (!currentUser) return;

  try {
    const data = await apiCall(`/api/profile/${currentUser}`);
    if (data.error) return;

    const avatarEl = document.getElementById('profile-avatar');
    if (data.profile_image) {
      avatarEl.innerHTML = `<img src="${data.profile_image}" style="width:96px;height:96px;border-radius:50%;object-fit:cover;border:2px solid #30363d">`;
    } else {
      avatarEl.innerText = data.avatar || '👤';
    }

    document.getElementById('profile-username').innerText = '@' + data.username;
    document.getElementById('profile-fullname').innerText = data.full_name || '';
    document.getElementById('profile-bio').innerText = data.bio || '';

    document.getElementById('profile-posts').innerText = data.total_posts ?? 0;
    document.getElementById('profile-comments').innerText = data.total_comments ?? 0;

    // posts list
    const list = document.getElementById('profile-posts-list');
    let html = '';
    (data.posts || []).forEach(p => {
      html += `
        <div class="post" style="cursor:default;">
          <div class="muted" style="font-size:12px;">${escHtml(p.timestamp)}</div>
          <div style="margin-top:8px;">${escHtml(p.content)}</div>
        </div>
      `;
    });
    list.innerHTML = html || '<p class="muted center">Henüz gönderi yok.</p>';

  } catch (e) {
    console.error('Profile error:', e);
  }
}

// Minimal profile edit placeholder (UI yok bu HTML’de)
function openProfileEdit() {
  alert('Bu minimal HTML sürümünde profil düzenleme modalı yok. İstersen ekleyeyim (bio + avatar + foto).');
}

// ---------------------------
// Init
// ---------------------------
async function initApp() {
  try {
    const s = await apiCall('/api/check-session');
    if (s.logged_in) {
      currentUser = s.username;

      document.getElementById('auth-ui').style.display = 'none';
      document.getElementById('user-ui').style.display = 'block';
      document.getElementById('nav-links').style.display = 'block';

      document.getElementById('user-name').innerText = '@' + (s.username || '');
      document.getElementById('user-avatar').innerText = s.avatar || '👤';

      // allow writing
      document.getElementById('post-box').style.display = 'block';
      document.getElementById('comment-box').style.display = 'block';
    }
  } catch (e) {
    console.error('Session check error:', e);
  }

  await fetchEconomicCalendar();
  await fetchMarket();
  await fetchFeed();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}