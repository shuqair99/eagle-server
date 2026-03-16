window.EAGLE_APP_CONFIG = {
  defaultUserAgent: "Mozilla/5.0 (Linux; Android 12; SmartTV; AFTMM Build/PS7655.3516N; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.0.0 Safari/537.36 EagleIPTV/2.0",
  appVersion: "1.0.0" // <-- ضفنا رقم الإصدار هنا
};

// ==========================================
// 1. THE EAGLE - Server & App Logic
// ==========================================
(function () {
  var KEY = 'active_server_data';
  var FULL_KEY = 'active_server_full_data';
  var cfg = window.EAGLE_APP_CONFIG || {};

  function safeGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function safeSet(key, value) { try { localStorage.setItem(key, value); } catch (e) {} }
  function safeRemove(key) { try { localStorage.removeItem(key); } catch (e) {} }
  function parseJson(raw) { if (!raw) return null; try { return JSON.parse(raw); } catch (e) { return null; } }

  function getQueryParam(name) {
    var search, parts, i, pair, key, val;
    try {
      search = window.location.search || '';
      if (!search || search.length < 2) return '';
      parts = search.substring(1).split('&');
      for (i = 0; i < parts.length; i++) {
        pair = parts[i].split('=');
        key = decodeURIComponent(pair[0] || '');
        if (key === name) {
          val = decodeURIComponent(pair[1] || '');
          return val;
        }
      }
    } catch (e) {}
    return '';
  }

  function bridgeAvailable() { return !!(window.EagleBridge && typeof window.EagleBridge.getProvidersData === 'function'); }
  function bridgeGetProvidersData() { if (!bridgeAvailable()) return null; try { return parseJson(window.EagleBridge.getProvidersData()); } catch (e) { return null; } }
  function bridgeGetActiveServer() { if (!window.EagleBridge) return null; try { if (typeof window.EagleBridge.getActiveServer === 'function') { return parseJson(window.EagleBridge.getActiveServer()); } } catch (e) {} return null; }
  function bridgePersistServer(server) { if (!window.EagleBridge) return; try { if (typeof window.EagleBridge.persistServer === 'function') { window.EagleBridge.persistServer(JSON.stringify(server)); } } catch (e) {} }

  function normalizeServer(server) {
    var host, username, password, title, key, subtitle, liveExt, userAgent;
    if (!server || typeof server !== 'object') return null;
    host = server.host || server.current_host || '';
    username = server.username || server.user || server.current_user || '';
    password = server.password || server.pass || server.current_pass || '';
    if (!host || !username || !password) return null;
    key = server.key || server.active_server_key || '';
    title = server.title || server.name || key || '';
    subtitle = server.subtitle || '';
    liveExt = server.live_ext || server.current_live_ext || 'm3u8';
    userAgent = server.user_agent || safeGet('eagle_user_agent') || cfg.defaultUserAgent || '';
    return { key: key, title: title, subtitle: subtitle, host: host, username: username, password: password, live_ext: liveExt, user_agent: userAgent };
  }

  function persistServer(server) {
    var normalized = normalizeServer(server);
    if (!normalized) return null;
    bridgePersistServer(normalized);
    safeSet(KEY, JSON.stringify(normalized));
    safeSet(FULL_KEY, JSON.stringify(normalized));
    safeSet('active_server_title', normalized.title || normalized.key || '');
    safeSet('current_host', normalized.host);
    safeSet('current_user', normalized.username);
    safeSet('current_pass', normalized.password);
    if (normalized.key) safeSet('active_server_key', normalized.key);
    if (normalized.live_ext) safeSet('current_live_ext', normalized.live_ext);
    else safeRemove('current_live_ext');
    if (normalized.user_agent) safeSet('eagle_user_agent', normalized.user_agent);
    return normalized;
  }

  function getPersistedServer() {
    var bridgeServer = normalizeServer(bridgeGetActiveServer());
    var stored;
    if (bridgeServer) return bridgeServer;
    stored = parseJson(safeGet(KEY)) || parseJson(safeGet(FULL_KEY));
    return normalizeServer(stored);
  }

  function getLegacyCurrentServer() {
    return normalizeServer({
      key: safeGet('active_server_key') || '',
      title: safeGet('active_server_title') || '',
      host: safeGet('current_host') || '',
      username: safeGet('current_user') || '',
      password: safeGet('current_pass') || '',
      live_ext: safeGet('current_live_ext') || 'm3u8',
      user_agent: safeGet('eagle_user_agent') || cfg.defaultUserAgent || ''
    });
  }

  function getProvidersData() {
    var bridgeData = bridgeGetProvidersData();
    if (bridgeData && bridgeData.providers) return bridgeData;
    return parseJson(safeGet('eagle_providers'));
  }

  function getProviderServerByKey(key, providersData) {
    var providers, provider;
    if (!key) return null;
    providers = (providersData || getProvidersData() || {}).providers || {};
    provider = providers[key];
    if (!provider) return null;
    return normalizeServer({ key: key, title: provider.title, subtitle: provider.subtitle, host: provider.host, username: provider.username, password: provider.password, live_ext: provider.live_ext, user_agent: provider.user_agent });
  }

  function resolveCurrentServer(fallback, providersData) {
    var queryKey = getQueryParam('server');
    var activeKey = safeGet('active_server_key') || '';
    var persisted = getPersistedServer();
    var legacy = getLegacyCurrentServer();
    var fallbackNormalized = normalizeServer(fallback);
    var fromProviders;
    providersData = providersData || getProvidersData();

    if (queryKey) { fromProviders = getProviderServerByKey(queryKey, providersData); if (fromProviders) return persistServer(fromProviders); }
    if (activeKey) { fromProviders = getProviderServerByKey(activeKey, providersData); if (fromProviders) return persistServer(fromProviders); }
    if (persisted) { if (persisted.key) { fromProviders = getProviderServerByKey(persisted.key, providersData); if (fromProviders) return persistServer(fromProviders); } return persistServer(persisted); }
    if (legacy) { if (legacy.key) { fromProviders = getProviderServerByKey(legacy.key, providersData); if (fromProviders) return persistServer(fromProviders); } return persistServer(legacy); }
    if (fallbackNormalized && fallbackNormalized.key) { fromProviders = getProviderServerByKey(fallbackNormalized.key, providersData); if (fromProviders) return persistServer(fromProviders); }
    if (fallbackNormalized) return persistServer(fallbackNormalized);
    return null;
  }

  function getServerOrFallback(fallback) { return resolveCurrentServer(fallback, getProvidersData()); }
  function navigateWithServer(url) {
    var s = resolveCurrentServer(null, getProvidersData()) || getPersistedServer();
    if (s && s.key) { url += (url.indexOf('?') === -1 ? '?' : '&') + 'server=' + encodeURIComponent(s.key); }
    window.location.href = url;
  }

  window.EagleServer = { normalizeServer: normalizeServer, persistServer: persistServer, getPersistedServer: getPersistedServer, getLegacyCurrentServer: getLegacyCurrentServer, getProvidersData: getProvidersData, getProviderServerByKey: getProviderServerByKey, resolveCurrentServer: resolveCurrentServer, getServerOrFallback: getServerOrFallback, navigateWithServer: navigateWithServer };
})();

// ==========================================
// 2. THE EAGLE - Unified Strict DRM & Activation System
// ==========================================
(function () {
  var adminApiUrl = 'https://eagle-server-1.onrender.com/api';
  var isAppUnlocked = false; 
  var heartbeatTimer = null;
  var failedAttempts = 0; // <-- متغير لعد مرات فشل الاتصال

  // الدالة الأساسية لتوليد وتثبيت الـ ID مع حماية ضد التلاعب
  function getEagleDeviceID() {
    var id = localStorage.getItem('eagle_hardware_id');
    if (!id) id = localStorage.getItem('device_id'); 
    
    // التحقق من صحة الـ ID (Anti-Tampering)
    if (id && (!id.startsWith('EAGLE-') || id.length < 10)) {
        id = null; // مسح الـ ID لو ملعوب فيه
    }

    if (!id) { 
      id = 'EAGLE-' + Math.floor(Math.random() * 1000000000).toString(16).toUpperCase(); 
      localStorage.setItem('eagle_hardware_id', id); 
      localStorage.setItem('device_id', id); 
    } else {
      localStorage.setItem('eagle_hardware_id', id); 
      localStorage.setItem('device_id', id); 
    }
    return id;
  }

  function validText(value) { return !!(value && value !== 'None' && value !== 'null' && value !== 'undefined'); }

  function getActiveServerName() {
    var helper = window.EagleServer;
    var current, raw, obj, name;
    if (helper && helper.getPersistedServer) {
      current = helper.getPersistedServer();
      if (current) { name = current.title || current.key || current.name || ''; if (validText(name)) return name; }
    }
    raw = localStorage.getItem('active_server_data') || localStorage.getItem('active_server_full_data');
    if (raw) { try { obj = JSON.parse(raw); if (obj) { name = obj.title || obj.key || obj.name || ''; if (validText(name)) return name; } } catch (e) {} }
    name = localStorage.getItem('active_server_title') || localStorage.getItem('active_server_key');
    if (validText(name)) return name;
    return 'Unknown';
  }

  function getDeviceType() {
    var stored = localStorage.getItem('device_model');
    var raw = '';
    try {
      if (validText(stored)) raw = String(stored).toLowerCase();
      else if (window.EAGLE_REAL_DEVICE) raw = String(window.EAGLE_REAL_DEVICE).toLowerCase();
      else if (navigator && navigator.userAgent) raw = String(navigator.userAgent).toLowerCase();
    } catch (e) {}

    if (!raw) return 'جهاز غير معروف';
    if (raw.indexOf('smarttv') !== -1 || raw.indexOf('smart-tv') !== -1 || raw.indexOf('hbbtv') !== -1 || raw.indexOf('webos') !== -1 || raw.indexOf('tizen') !== -1 || raw.indexOf('appletv') !== -1) return 'شاشة سمارت';
    if (raw.indexOf('tv box') !== -1 || raw.indexOf('tvbox') !== -1 || raw.indexOf('androidtv') !== -1 || raw.indexOf('android tv') !== -1 || raw.indexOf('aft') !== -1 || raw.indexOf('fire tv') !== -1 || raw.indexOf('mibox') !== -1 || raw.indexOf('box') !== -1) return 'تي في بوكس';
    if (raw.indexOf('iphone') !== -1 || raw.indexOf('ipad') !== -1 || raw.indexOf('ipod') !== -1) return 'موبايل iOS';
    if (raw.indexOf('android') !== -1) { if (raw.indexOf('mobile') !== -1) return 'موبايل أندرويد'; return 'تي في بوكس'; }
    if (raw.indexOf('windows') !== -1 || raw.indexOf('macintosh') !== -1 || raw.indexOf('linux') !== -1 || raw.indexOf('cros') !== -1) return 'كمبيوتر';
    return 'جهاز غير معروف';
  }

  function handleSecurityScreen(type, deviceId) {
    var overlay = document.getElementById('eagle-security-lock');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'eagle-security-lock';
      overlay.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;background:#050505;z-index:999999;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;font-family:Arial,sans-serif; text-align:center;';
      document.body.appendChild(overlay);
    }
    
    if (type === 'checking') {
      overlay.innerHTML = '<h1 style="color:#f3d27a; font-size:3rem; margin-bottom:15px;">جاري الاتصال بالسيرفر والتحقق من الاشتراك...</h1><p>يرجى الانتظار...</p>';
      overlay.style.display = 'flex';
    } else if (type === 'pending') {
      overlay.innerHTML = '<h1 style="color:#d4af37; font-size:3.5rem; margin-bottom:15px; font-weight:900;">التطبيق بانتظار التفعيل</h1><h3 style="color:#aaa; font-size:1.5rem; margin-bottom:30px;">يرجى تزويد الإدارة برقم الجهاز التالي لتفعيل اشتراكك:</h3><div style="background:#111; border:3px dashed #d4af37; padding:20px 40px; border-radius:15px; font-size:3rem; font-weight:bold; letter-spacing:4px; color:#00ff88; box-shadow: 0 0 20px rgba(212,175,55,0.2);">' + deviceId + '</div><p style="color:#555; margin-top:30px; font-size:1.2rem;">Powered by THE EAGLE ©</p>';
      overlay.style.display = 'flex';
    } else if (type === 'blocked') {
      overlay.innerHTML = '<h1 style="color:#ff4b4b; font-size:4rem; margin-bottom:20px; font-weight:900;">تم إيقاف الخدمة</h1><h3 style="color:#ccc; font-size:1.5rem;">هذا الجهاز محظور من قبل الإدارة.</h3><p style="color:#555; margin-top:20px;">Device ID: ' + deviceId + '</p>';
      overlay.style.display = 'flex';
    } else if (type === 'expired') {
      overlay.innerHTML = '<h1 style="color:#ff8c00; font-size:4rem; margin-bottom:20px; font-weight:900;">انتهى الاشتراك</h1><h3 style="color:#ccc; font-size:1.5rem;">يرجى التواصل مع الإدارة لتجديد اشتراكك.</h3><p style="color:#555; margin-top:20px;">Device ID: ' + deviceId + '</p>';
      overlay.style.display = 'flex';
    } else if (type === 'error') {
      overlay.innerHTML = '<h1 style="color:#ff4b4b; font-size:3.5rem; margin-bottom:15px;">خطأ في الاتصال بلوحة التحكم</h1><h3 style="color:#aaa; font-size:1.5rem;">التطبيق لا يستطيع الوصول لسيرفر التفعيل. تأكد من اتصالك بالانترنت.</h3><p style="color:#555; margin-top:30px;">Device ID: ' + deviceId + '</p><button onclick="window.location.reload()" style="margin-top:20px; padding:10px 20px; font-size:1.2rem; background:#d4af37; border:none; border-radius:5px; cursor:pointer;">إعادة المحاولة</button>';
      overlay.style.display = 'flex';
    } else if (type === 'active') {
      overlay.style.display = 'none';
      isAppUnlocked = true;
      failedAttempts = 0; // تصفير العداد عند النجاح
    }
  }

  function safeWipeData() {
    var savedId = getEagleDeviceID(); 
    try { localStorage.clear(); } catch(e) {}
    localStorage.setItem('eagle_hardware_id', savedId); 
    localStorage.setItem('device_id', savedId);
  }

  var deviceId = getEagleDeviceID();
  handleSecurityScreen('checking', deviceId); 

  // دالة لمعالجة أخطاء الاتصال (Retry Logic)
  function handleConnectionError() {
      failedAttempts++;
      if (failedAttempts < 3 && !isAppUnlocked) {
          // لو فشل أقل من 3 مرات، جرب تاني بعد ثانيتين في صمت
          setTimeout(sendEagleHeartbeat, 2000);
      } else if (!isAppUnlocked) {
          // لو فشل 3 مرات والتطبيق مقفول، أظهر رسالة الخطأ
          handleSecurityScreen('error', deviceId);
      }
      // لو التطبيق كان مفتوح وشغال والنت قطع، مش هنعمل حاجة وهنسيبه يكمل الفرجة، وهنجرب تاني في النبضة اللي جاية
  }

  function sendEagleHeartbeat() {
    var serverName = getActiveServerName();
    var nowPlaying = localStorage.getItem('eagle_now_playing') || localStorage.getItem('now_playing') || 'يتصفح القوائم...';
    // إضافة رقم الإصدار للموديل عشان يظهر في لوحة التحكم
    var deviceModel = getDeviceType() + " (v" + (window.EAGLE_APP_CONFIG.appVersion || "1.0") + ")";

    var xhr = new XMLHttpRequest();
    var url = adminApiUrl + '?device=' + encodeURIComponent(deviceId) +
              '&server=' + encodeURIComponent(serverName) +
              '&playing=' + encodeURIComponent(nowPlaying) +
              '&model=' + encodeURIComponent(deviceModel);

    xhr.onreadystatechange = function() {
      if (xhr.readyState === 4) {
        if (xhr.status === 200) {
          try {
            var response = JSON.parse(xhr.responseText);
            
            if (response.status === 'blocked' || response.action === 'wipe_data') {
              safeWipeData();
              handleSecurityScreen('blocked', deviceId);
              isAppUnlocked = false;
            } else if (response.status === 'pending') {
              handleSecurityScreen('pending', deviceId);
              isAppUnlocked = false;
            } else if (response.status === 'expired') {
              handleSecurityScreen('expired', deviceId);
              isAppUnlocked = false;
            } else if (response.status === 'active') {
              handleSecurityScreen('active', deviceId);
            }
          } catch(e) {
            handleConnectionError();
          }
        } else {
          handleConnectionError();
        }
      }
    };
    xhr.onerror = function() { handleConnectionError(); };
    try { xhr.open('GET', url, true); xhr.send(); } catch(e) { handleConnectionError(); }
  }

  setTimeout(sendEagleHeartbeat, 100);
  heartbeatTimer = setInterval(sendEagleHeartbeat, 15000); 

  window.EagleProtection = {
    sendHeartbeat: sendEagleHeartbeat,
    getDeviceId: getEagleDeviceID,
    getServerName: getActiveServerName,
    getDeviceType: getDeviceType
  };
})();

// ==========================================
// 3. THE EAGLE - Security & Control System
// ==========================================
window.EagleControl = {
    getPin: function() { return localStorage.getItem('eagle_pin') || ''; },
    setPin: function(pin) { localStorage.setItem('eagle_pin', pin); },
    getHiddenCats: function() { return JSON.parse(localStorage.getItem('eagle_hidden_cats') || '[]'); },
    toggleHideCat: function(catId) {
        var hidden = this.getHiddenCats();
        var idx = hidden.indexOf(catId);
        if(idx > -1) hidden.splice(idx, 1);
        else hidden.push(catId);
        localStorage.setItem('eagle_hidden_cats', JSON.stringify(hidden));
    },
    getLockedCats: function() { return JSON.parse(localStorage.getItem('eagle_locked_cats') || '[]'); },
    toggleLockCat: function(catId) {
        var locked = this.getLockedCats();
        var idx = locked.indexOf(catId);
        if(idx > -1) locked.splice(idx, 1);
        else locked.push(catId);
        localStorage.setItem('eagle_locked_cats', JSON.stringify(locked));
    },
    clearCache: function() {
        var keysToKeep = ['eagle_hardware_id', 'device_id', 'eagle_providers', 'active_server_key', 'active_server_full_data', 'active_server_title', 'eagle_lang', 'eagle_pin', 'eagle_hidden_cats', 'eagle_locked_cats', 'eagle_update_info'];
        var dataToKeep = {};
        keysToKeep.forEach(function(k) { dataToKeep[k] = localStorage.getItem(k); });
        localStorage.clear();
        keysToKeep.forEach(function(k) { if(dataToKeep[k]) localStorage.setItem(k, dataToKeep[k]); });
    }
};
