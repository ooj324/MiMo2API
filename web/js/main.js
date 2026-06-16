var _lang=localStorage.getItem('mimo_lang')||'zh';
var _I={zh:{"curl":"cURL","cookie":"Cookie","accounts":"账号","apikey":"API Key","usage":"用量统计","parseCurl":"解析 cURL","parseFill":"解析填充 ↓","saveAcct":"保存账号","verifyBtn":"验证中...","saved":"已保存","saveFail":"保存失败","reqFail":"请求失败","refresh":"刷新","testAll":"测试全部","cleanupSessions":"清理过期会话","noAccts":"暂无配置账号","valid":"✅ 有效","notVerified":"⚪ 未验证","test":"测试","delete":"删除","loadFail":"加载失败","testing":"测试中...","testFail":"测试失败","noAcctTest":"无账号可测试","allTestDone":"有效","cleanup":"清理中...","cleanupFail":"清理失败: ","unknown":"未知","deleteConfirm":"确定删除此账号？","deleted":"已删除","deleteFail":"删除失败","usageNoData":"暂无用量数据","usageModel":"模型","usageReqs":"请求","usageInput":"输入","usageOutput":"输出","usageTotal":"总计","usageSum":"合计","usageLoadFail":"加载失败: ","periodAll":"全部","periodWeek":"本周","periodToday":"今日","clearConfirm":"确定清空全部用量数据？此操作不可撤销。","cleared":"已清空","clearFail":"清空失败","configSaved":"配置已保存","saveConfigFail":"保存失败","parseFail":"解析失败，请检查 cURL 格式","parsing":"解析中...","parseOk":"解析成功","testConn":"测试连接","addAcct":"添加账号","connOk":"连接成功: ","connFail":"连接失败: ","acctAdded":"账号已添加","pasteCurl":"请粘贴 cURL 命令","pasteCookie":"请粘贴 Cookie 字符串","fieldsRequired":"请填写所有字段","filledFields":"已填充","filledFields2":"个字段","filledFields3":"缺少","filledFields4":"个","noValidFields":"未识别到有效字段","apiKeysLabel":"API Keys (多个以逗号分隔)","apiKeysPH":"sk-key1, sk-key2","saveConfig":"保存配置","mimoDesc":"小米 MiMo 模型 OpenAI 兼容接口配置中心","keysSaved":"配置已保存","saving":"保存中...","passthroughLabel":"工具透传模式 (Tool Passthrough)","passthroughHint":"开启后将直接向 MiMo 模型嵌入原始 JSON Schema 工具定义，跳过通用格式指导说明书。适合 Roo Code / Cline 等对格式要求严格的智能体。","adminPwdLabel":"后台管理员密码","adminPwdPH":"修改后需重新登录","login":"账号登录"},
en:{"curl":"cURL","cookie":"Cookie","accounts":"Accounts","apikey":"Settings","usage":"Usage","parseCurl":"Parse cURL","parseFill":"Parse & Fill ↓","saveAcct":"Save Account","verifyBtn":"Verifying...","saved":"Saved","saveFail":"Save Failed","reqFail":"Request Failed","refresh":"Refresh","testAll":"Test All","cleanupSessions":"Cleanup Sessions","noAccts":"No accounts configured","valid":"✅ Active","notVerified":"⚪ Not Verified","test":"Test","delete":"Delete","loadFail":"Load Failed","testing":"Testing...","testFail":"Test Failed","noAcctTest":"No accounts to test","allTestDone":"valid","cleanup":"Cleaning...","cleanupFail":"Cleanup failed: ","unknown":"unknown","deleteConfirm":"Delete this account?","deleted":"Deleted","deleteFail":"Delete Failed","usageNoData":"No usage data","usageModel":"Model","usageReqs":"Requests","usageInput":"Input","usageOutput":"Output","usageTotal":"Total","usageSum":"Total","usageLoadFail":"Load failed: ","periodAll":"All","periodWeek":"This Week","periodToday":"Today","clearConfirm":"Clear all usage data? This cannot be undone.","cleared":"Cleared","clearFail":"Clear failed","configSaved":"Config saved","saveConfigFail":"Save failed","parseFail":"Parse failed, check cURL format","parsing":"Parsing...","parseOk":"Parsed","testConn":"Test Connection","addAcct":"Add Account","connOk":"Connected: ","connFail":"Connection failed: ","acctAdded":"Account added","pasteCurl":"Please paste cURL command","pasteCookie":"Please paste Cookie string","fieldsRequired":"Please fill all fields","filledFields":"Filled","filledFields2":"field(s)","filledFields3":"missing","filledFields4":"","noValidFields":"No valid fields found","apiKeysLabel":"API Keys (comma separated)","apiKeysPH":"sk-key1, sk-key2","saveConfig":"Save Config","mimoDesc":"Xiaomi MiMo OpenAI-compatible API Dashboard","keysSaved":"Config saved","saving":"Saving...","passthroughLabel":"Tool Passthrough Mode","passthroughHint":"Bypass format instructions and embed raw JSON Schema tool definitions directly. Ideal for agents like Roo Code / Cline.","adminPwdLabel":"Admin Password","adminPwdPH":"Re-login required after change","login":"Login"}};
function _(k){return (_I[_lang]||_I.zh)[k]||k}
function toggleLang(){_lang=_lang==='zh'?'en':'zh';localStorage.setItem('mimo_lang',_lang);$id('langBtn').textContent=_lang==='zh'?'🌐 EN':'🌐 中';applyI18n()}
function applyI18n(){
    document.querySelectorAll('[data-i18n]').forEach(function(el){var k=el.getAttribute('data-i18n');if(k)el.textContent=_(k)});
    document.querySelectorAll('[data-i18n-ph]').forEach(function(el){var k=el.getAttribute('data-i18n-ph');if(k)el.placeholder=_(k)});
    document.querySelector('.header p').textContent=_('mimoDesc');
    var tabs=document.querySelectorAll('.tab');
    var tkeys=['accounts','login','curl','cookie','apikey','usage'];
    for(var i=0;i<6&&i<tabs.length;i++)tabs[i].textContent=_(tkeys[i])
}
document.addEventListener('DOMContentLoaded',function(){$id('langBtn').textContent=_lang==='zh'?'🌐 EN':'🌐 中';applyI18n()});

        let cfg = { api_keys: '', mimo_accounts: [], session_limit_per_account: 10 }, parsed = null;

        function $id(id) { return document.getElementById(id); }
        function toast(msg, err) {
            const t = $id('toast');
            t.textContent = msg; t.className = 'toast show ' + (err ? 'toast-err' : 'toast-ok');
            clearTimeout(t._t); t._t = setTimeout(() => { t.className = 'toast'; }, 3000);
        }
        function showStatus(id, type, msg) {
            $id(id).innerHTML = `<div class="status ${type}">${msg}</div>`;
        }
        function switchTab(t) {
            document.querySelectorAll('.tab').forEach((el, i) => {
                el.className = 'tab' + (['accounts','login','curl','cookie','apikey','usage'][i] === t ? ' active' : '');
            });
            document.querySelectorAll('.tab-panel').forEach(p => p.className = 'tab-panel');
            $id('panel-' + t).className = 'tab-panel active';
            if (t === 'accounts') loadAccounts();
            if (t === 'usage') loadUsage();
        }

        async function loadConfig() {
            try {
                const r = await fetch('/api/config');
                cfg = await r.json();
                $id('apiKeys').value = cfg.api_keys || '';
                $id('passthroughToggle').checked = !!cfg.tools_passthrough;
                $id('adminPassword').value = cfg.admin_password || '';
                $id('sessionLimit').value = cfg.session_limit_per_account || 10;
            } catch (e) {}
        }

        async function saveKeys() {
            cfg.api_keys = $id('apiKeys').value;
            cfg.tools_passthrough = $id('passthroughToggle').checked;
            cfg.admin_password = $id('adminPassword').value || 'admin';
            cfg.session_limit_per_account = parseInt($id('sessionLimit').value) || 10;
            try {
                await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(cfg)
                });
                showStatus('keysResult', 'ok', _('configSaved'));
                setTimeout(() => $id('keysResult').innerHTML = '', 2000);
                toast('设置已保存并生效');
            } catch (e) {
                showStatus('keysResult', 'err', _('saveConfigFail'));
            }
        }

        async function parseCurl() {
            const curl = $id('curl').value.trim();
            if (!curl) { toast(_('pasteCurl'), true); return; }
            showStatus('curlResult', 'info', _('parsing'));
            try {
                const r = await fetch('/api/parse-curl', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ curl })
                });
                if (!r.ok) { showStatus('curlResult', 'err', '解析失败，请检查 cURL 格式'); return; }
                parsed = await r.json();
                $id('curlResult').innerHTML = `
                    <div class="status ok">解析成功 — userId: <b>${parsed.user_id}</b></div>
                    <div class="btn-group">
                        <button class="btn-outline" onclick="testParsed()">验证连接</button>
                        <button class="btn-success" onclick="saveParsed()">保存账号</button>
                    </div>
                    <div id="testResult"></div>
                `;
            } catch (e) { showStatus('curlResult', 'err', '请求失败: ' + e.message); }
        }

        async function testParsed() {
            if (!parsed) return;
            showStatus('testResult', 'info', _('testing'));
            try {
                const r = await fetch('/api/test-account', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(parsed)
                });
                const d = await r.json();
                if (d.success) showStatus('testResult', 'ok', '连接成功: ' + d.response.slice(0, 60) + '...');
                else showStatus('testResult', 'err', '连接失败: ' + d.error);
            } catch (e) { showStatus('testResult', 'err', '请求失败'); }
        }

        async function saveParsed() {
            if (!parsed) return;
            const btn = event.target;
            btn.disabled = true; btn.textContent = _('saving');
            try {
                cfg.mimo_accounts = cfg.mimo_accounts || [];
                cfg.mimo_accounts.push(parsed);
                await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(cfg)
                });
                parsed = null;
                $id('curl').value = '';
                $id('curlResult').innerHTML = '';
                toast(_('acctAdded'));
                loadConfig();
                switchTab('accounts');
            } catch (e) { toast(_('saveFail'), true); }
            finally { btn.disabled = false; btn.textContent = '保存账号'; }
        }

        function parseCookieStr() {
            const raw = $id('c-raw').value.trim();
            if (!raw) { toast(_('pasteCookie'), true); return; }
            const parts = raw.split(';');
            const map = {};
            for (let p of parts) {
                p = p.trim(); if (!p) continue;
                const eq = p.indexOf('='); if (eq === -1) continue;
                let key = p.substring(0, eq).trim();
                let val = p.substring(eq + 1).trim();
                if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) { val = val.slice(1, -1); }
                map[key] = val;
            }
            if (map.serviceToken) $id('c-st').value = map.serviceToken;
            else if (map.passToken) $id('c-st').value = map.passToken;
            
            if (map.userId) $id('c-uid').value = map.userId;
            if (map.xiaomichatbot_ph) $id('c-ph').value = map.xiaomichatbot_ph;
            
            const isPassport = (map.passToken || "").startsWith('V1:') || (map.passToken || "").startsWith('V2:');
            const filled = [map.serviceToken || map.passToken, map.userId, isPassport ? 'pass' : map.xiaomichatbot_ph].filter(Boolean).length;
            if (filled >= 3) { toast('已填充 ' + filled + ' 个字段'); }
            else if (filled > 0) { toast('已填充 ' + filled + ' 个字段', true); }
            else { toast('未识别到有效字段', true); }
        }

        async function saveCookie() {
            const st = $id('c-st').value.trim();
            const uid = $id('c-uid').value.trim();
            const ph = $id('c-ph').value.trim();
            const isPassport = st.startsWith('V1:') || st.startsWith('V2:');
            
            if (!st || !uid) { toast('请填写必填字段', true); return; }
            if (!isPassport && !ph) { toast('请填写 xiaomichatbot_ph', true); return; }
            
            const btn = $id('btn-save-cookie');
            btn.disabled = true; btn.textContent = _('verifyBtn');
            try {
                const body = isPassport 
                    ? { passToken: st, userId: uid }
                    : { serviceToken: st, userId: uid, xiaomichatbot_ph: ph };
                const r = await fetch('/api/account/import-cookie', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                const d = await r.json();
                if (d.ok) {
                    toast(_('saved'));
                    $id('c-st').value = ''; $id('c-uid').value = ''; $id('c-ph').value = ''; $id('c-raw').value = '';
                    loadConfig();
                    switchTab('accounts');
                } else {
                    toast(d.error || '保存失败', true);
                }
            } catch (e) { toast(_('reqFail'), true); }
            finally { btn.disabled = false; btn.textContent = _('saveAcct'); }
        }

        // ─── 账号登录 / SSO 兑换 ──────────────────────────────────
        
        function switchLoginMethod(method) {
            $id('btn-login-method-pwd').className = 'period-btn' + (method === 'pwd' ? ' active' : '');
            $id('btn-login-method-passport').className = 'period-btn' + (method === 'passport' ? ' active' : '');
            $id('login-method-pwd').style.display = method === 'pwd' ? 'block' : 'none';
            $id('login-method-passport').style.display = method === 'passport' ? 'block' : 'none';
        }

        let currentSessionId = null;

        async function doLoginPwd() {
            const user = $id('l-user').value.trim();
            const pwd = $id('l-pwd').value.trim();
            if (!user || !pwd) { toast('请填写账号和密码', true); return; }
            
            const btn = $id('btn-do-login-pwd');
            btn.disabled = true; btn.textContent = '登录中...';
            
            try {
                const r = await fetch('/api/account/login-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: user, password: pwd })
                });
                
                if (!r.ok) {
                    const errorData = await r.json();
                    toast(errorData.detail || '登录失败', true);
                    return;
                }
                
                const d = await r.json();
                if (d.ok) {
                    toast('登录并自动兑换成功！');
                    $id('l-user').value = ''; $id('l-pwd').value = '';
                    loadConfig();
                    switchTab('accounts');
                } else if (d.code === 'need_2fa') {
                    currentSessionId = d.session_id;
                    $id('l-2fa-link').href = d.notification_url;
                    $id('login-method-pwd').style.display = 'none';
                    $id('login-2fa-status').style.display = 'block';
                    toast('安全机制拦截，需要二步验证', true);
                }
            } catch (e) {
                toast('登录接口异常: ' + e.message, true);
            } finally {
                btn.disabled = false; btn.textContent = '开始登录';
            }
        }

        async function confirm2fa() {
            if (!currentSessionId) return;
            const btn = $id('btn-confirm-2fa');
            btn.disabled = true; btn.textContent = '校验中...';
            
            try {
                const r = await fetch('/api/account/login-2fa-verify', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: currentSessionId })
                });
                
                const d = await r.json();
                if (r.ok && d.ok) {
                    toast('两步验证登录成功！');
                    $id('l-user').value = ''; $id('l-pwd').value = '';
                    $id('login-2fa-status').style.display = 'none';
                    $id('login-method-pwd').style.display = 'block';
                    currentSessionId = null;
                    loadConfig();
                    switchTab('accounts');
                } else {
                    toast(d.message || d.detail || '验证似乎尚未完成，请通过浏览器验证后重试', true);
                }
            } catch (e) {
                toast('验证校验失败: ' + e.message, true);
            } finally {
                btn.disabled = false; btn.textContent = '我已完成验证';
            }
        }

        function cancel2fa() {
            currentSessionId = null;
            $id('login-2fa-status').style.display = 'none';
            $id('login-method-pwd').style.display = 'block';
        }

        async function doLoginPassport() {
            const passToken = $id('l-pass-token').value.trim();
            const userId = $id('l-passport-uid').value.trim();
            const deviceId = $id('l-passport-device').value.trim();
            
            if (!passToken || !userId) {
                toast('请填写 passToken 和 userId', true);
                return;
            }
            
            const btn = $id('btn-do-login-passport');
            btn.disabled = true; btn.textContent = '兑换中...';
            
            try {
                const r = await fetch('/api/account/login-passport', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ passToken, userId, deviceId: deviceId || null })
                });
                
                if (!r.ok) {
                    const errorData = await r.json();
                    toast(errorData.detail || '验证/兑换失败', true);
                    return;
                }
                
                toast('小米凭证自动兑换成功！');
                $id('l-pass-token').value = ''; $id('l-passport-uid').value = ''; $id('l-passport-device').value = '';
                loadConfig();
                switchTab('accounts');
            } catch (e) {
                toast('请求异常: ' + e.message, true);
            } finally {
                btn.disabled = false; btn.textContent = '验证并导入';
            }
        }

        async function loadAccounts() {
            try {
                const r = await fetch('/api/accounts');
                const d = await r.json();
                const el = $id('accounts');
                if (!d.accounts || !d.accounts.length) {
                    el.innerHTML = '<div class="empty"><div style="font-size:40px;margin-bottom:10px;opacity:0.5">👤</div>暂无配置账号，请在其它标签页导入</div>';
                    return;
                }
                const limit = parseInt($id('sessionLimit').value) || 10;
                el.innerHTML = d.accounts.map((a, i) => {
                    const sessionPct = Math.min(100, Math.round((a.active_sessions || 0) / limit * 100));
                    const isOverload = (a.active_sessions || 0) >= limit;
                    return `
                    <div class="account">
                        <div style="display:flex; justify-content:space-between; margin-bottom: 12px;">
                            <div class="info-line" style="margin-bottom:0;">
                                <span class="status-dot" style="color:${a.is_valid ? '#4ade80' : '#fb7185'}"></span>
                                <b>${a.email || 'UID: ' + a.user_id}</b>
                                <span class="badge ${a.is_valid ? 'badge-valid' : 'badge-invalid'}">${a.is_valid ? 'Active' : 'Error'}</span>
                            </div>
                            <div style="font-size: 11px; color: var(--text-muted); background: rgba(0,0,0,0.2); padding: 2px 8px; border-radius: 10px;">
                                会话: <span style="color: ${isOverload ? '#fb7185' : '#e2e8f0'}; font-weight: bold;">${a.active_sessions || 0}</span> / ${limit}
                            </div>
                        </div>
                        <div class="info-line" style="font-size:12px;"><b>Token</b> <code>${a.token_masked}</code></div>
                        ${a.email ? `<div class="info-line" style="font-size:12px;opacity:0.7"><b>UID</b> ${a.user_id}</div>` : ''}
                        <div class="actions">
                            <button class="btn-outline" style="padding:6px 14px; font-size:12px" onclick="testAcct(${i})">连通性测试</button>
                            <button class="btn-danger" style="margin-left:auto; background:transparent; color:#fb7185; border:1px solid rgba(251, 113, 133, 0.3);" onclick="delAcct(${i})">移除</button>
                        </div>
                    </div>
                `}).join('');
            } catch (e) {
                $id('accounts').innerHTML = '<div class="empty" style="color:#fb7185">数据加载失败，请检查网络连接或刷新页面</div>';
            }
        }

        async function syncAccountsJson() {
            try {
                const r = await fetch('/api/account/sync-json', { method: 'POST' });
                const d = await r.json();
                if (d.ok) {
                    if (d.added > 0) toast(`成功同步了 ${d.added} 个新账号！`);
                    else toast(`同步完成，未发现新账号。`);
                    loadAccounts();
                    loadConfig();
                } else {
                    toast('同步失败: ' + d.error, true);
                }
            } catch (e) { toast('请求失败', true); }
        }

        async function testAcct(i) {
            const btn = event.target;
            btn.disabled = true; btn.textContent = '测试中...';
            try {
                const r = await fetch('/api/accounts/' + i + '/test', { method: 'POST' });
                const d = await r.json();
                if (d.ok) { toast('✅ 连接成功'); loadAccounts(); }
                else toast('❌ ' + d.error, true);
            } catch (e) { toast(_('testFail'), true); }
            btn.disabled = false; btn.textContent = '连通性测试';
        }

        async function testAll() {
            const btn = event.target;
            btn.disabled = true; btn.textContent = '测试中...';
            try {
                const r = await fetch('/api/accounts');
                const d = await r.json();
                if (!d.accounts || !d.accounts.length) { toast(_('noAcctTest'), true); btn.disabled = false; btn.textContent = '测试全部有效性'; return; }
                let ok = 0;
                for (let i = 0; i < d.accounts.length; i++) {
                    btn.textContent = '测试 (' + (i + 1) + '/' + d.accounts.length + ')';
                    try {
                        const r2 = await fetch('/api/accounts/' + i + '/test', { method: 'POST' });
                        const d2 = await r2.json();
                        if (d2.ok) ok++;
                    } catch (e) {}
                }
                toast(ok + '/' + d.accounts.length + ' 账号测试有效');
                loadAccounts();
            } catch (e) { toast(_('reqFail'), true); }
            btn.disabled = false; btn.textContent = '测试全部有效性';
        }

        async function cleanupSessions() {
            const btn = event.target;
            btn.disabled = true; btn.textContent = '清理中...';
            try {
                const r = await fetch('/api/cleanup', { method: 'POST' });
                const d = await r.json();
                if (d.ok) { toast('✨ ' + d.msg); loadAccounts(); }
                else toast('清理失败: ' + (d.msg || '未知'), true);
            } catch (e) { toast('清理失败: ' + e.message, true); }
            btn.disabled = false; btn.textContent = '清理过期会话';
        }

        async function delAcct(i) {
            if (!confirm('确定要移除该账号吗？')) return;
            try {
                await fetch('/api/accounts/' + i, { method: 'DELETE' });
                toast('账号已移除');
                loadAccounts();
                loadConfig();
            } catch (e) { toast(_('deleteFail'), true); }
        }

        let usagePeriod = 'total';
        function fmt(n) { return n.toLocaleString(); }
        async function loadUsage() {
            try {
                const r = await fetch('/api/usage');
                const data = await r.json();
                const period = data[usagePeriod] || data.total || {};
                const models = period.models || {};
                const total = period.total || {};
                let entries = Object.entries(models).sort((a, b) => b[1].total_tokens - a[1].total_tokens);

                if (!entries.length && !total.requests) {
                    $id('usageContent').innerHTML = '<div class="empty"><div style="font-size:40px;margin-bottom:10px;opacity:0.5">📊</div>暂无用量数据</div>';
                    return;
                }

                let html = '<div class="usage-scroll"><table class="usage-tbl"><thead><tr><th class="model-cell">'+_('usageModel')+'</th><th>'+_('usageReqs')+'</th><th>'+_('usageInput')+'</th><th>'+_('usageOutput')+'</th><th>'+_('usageTotal')+'</th></tr></thead><tbody>';
                for (const [model, m] of entries) {
                    html += `<tr>
                        <td class="model-cell"><span style="background:rgba(129, 140, 248, 0.15);color:#a5b4fc;padding:2px 8px;border-radius:6px;font-size:12px">${model}</span></td>
                        <td>${fmt(m.requests)}</td>
                        <td>${fmt(m.prompt_tokens)}</td>
                        <td>${fmt(m.completion_tokens)}</td>
                        <td style="font-weight:600;color:#e2e8f0">${fmt(m.total_tokens)}</td>
                    </tr>`;
                }
                if (entries.length) {
                    html += `<tr class="total-row">
                        <td class="model-cell">${_('usageSum')}</td>
                        <td>${fmt(total.requests)}</td>
                        <td>${fmt(total.prompt_tokens)}</td>
                        <td>${fmt(total.completion_tokens)}</td>
                        <td>${fmt(total.total_tokens)}</td>
                    </tr>`;
                }
                html += '</tbody></table></div>';
                $id('usageContent').innerHTML = html;
            } catch (e) {
                $id('usageContent').innerHTML = '<div class="empty" style="color:#fb7185">加载失败: ' + e.message + '</div>';
            }
        }
        function switchPeriod(p) {
            usagePeriod = p;
            document.querySelectorAll('#panel-usage .period-btn[data-p]').forEach(b => b.className = 'period-btn');
            document.querySelector('#panel-usage .period-btn[data-p="'+p+'"]').className = 'period-btn active';
            loadUsage();
        }
        async function clearUsage() {
            if (!confirm(_('clearConfirm'))) return;
            try {
                const r = await fetch('/api/usage', { method: 'DELETE' });
                const d = await r.json();
                if (d.ok) { toast(_('cleared')); loadUsage(); }
                else toast(_('clearFail'), true);
            } catch (e) { toast('清空失败: ' + e.message, true); }
        }

        // INIT
        loadConfig().then(() => {
            switchTab('accounts');
        });