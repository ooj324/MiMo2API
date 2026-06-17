var _lang=localStorage.getItem('mimo_lang')||'zh';
var _I={zh:{
    "xiaomi":"小米账号","mimo":"MiMo 会话","curl":"cURL","cookie":"Cookie","login":"账号登录","apikey":"系统设置","usage":"用量统计",
    "parseCurl":"解析 cURL","parseFill":"解析填充","saveAcct":"保存为 MiMo 会话","verifyBtn":"验证中...",
    "saved":"已保存","saveFail":"保存失败","reqFail":"请求失败","refresh":"刷新","testAll":"测试全部","cleanupSessions":"清空远端会话",
    "noAccts":"暂无 MiMo 会话","valid":"有效","notVerified":"未验证","test":"测试","delete":"删除",
    "loadFail":"加载失败","testing":"测试中...","testFail":"测试失败","noAcctTest":"无会话可测试",
    "allTestDone":"有效","cleanup":"清理中...","cleanupFail":"清理失败: ","unknown":"未知",
    "deleteConfirm":"确定删除？","deleted":"已删除","deleteFail":"删除失败",
    "usageNoData":"暂无用量数据","usageModel":"模型","usageReqs":"请求","usageInput":"输入","usageOutput":"输出",
    "usageTotal":"总计","usageSum":"合计","usageLoadFail":"加载失败: ",
    "periodAll":"全部","periodWeek":"本周","periodToday":"今日",
    "clearConfirm":"确定清空全部用量数据？此操作不可撤销。","cleared":"已清空","clearFail":"清空失败",
    "configSaved":"配置已保存","saveConfigFail":"保存失败",
    "parseFail":"解析失败，请检查 cURL 格式","parsing":"解析中...","parseOk":"解析成功",
    "testConn":"测试连接","addAcct":"添加账号","connOk":"连接成功: ","connFail":"连接失败: ",
    "acctAdded":"账号已添加","pasteCurl":"请粘贴 cURL 命令","pasteCookie":"请粘贴 Cookie 字符串",
    "fieldsRequired":"请填写所有字段","noValidFields":"未识别到有效字段",
    "apiKeysLabel":"API Keys (多个以逗号分隔)","saveConfig":"保存配置",
    "mimoDesc":"小米 MiMo 模型 OpenAI 兼容接口配置中心","keysSaved":"配置已保存","saving":"保存中...",
    "passthroughLabel":"工具透传模式 (Tool Passthrough)",
    "passthroughHint":"开启后将直接向 MiMo 模型嵌入原始 JSON Schema 工具定义，跳过通用格式指导说明书。适合 Roo Code / Cline 等对格式要求严格的智能体。",
    "sessionReuseLabel":"开启长连接会话复用 (Session Reuse)",
    "sessionReuseHint":"开启后将复用与模型服务器的 HTTP 长连接，有效提升请求速度。",
    "adminPwdLabel":"后台管理员密码",
    "noXiaomiAccts":"暂无小米账号，请在上方添加",
    "tblAccount":"账号","tblUid":"UID","tblToken":"Token","tblDevice":"设备 ID","tblCreated":"创建时间","tblActions":"操作","tblStatus":"状态","tblSource":"来源账号","tblSessions":"会话数量","tblHasPwd":"有密码","btnExchange":"兑换 MiMo","btnTest":"连通性测试","btnDelete":"移除"
},
en:{
    "xiaomi":"Xiaomi Accounts","mimo":"MiMo Sessions","curl":"cURL","cookie":"Cookie","login":"Login","apikey":"Settings","usage":"Usage",
    "parseCurl":"Parse cURL","parseFill":"Parse & Fill","saveAcct":"Save as MiMo Session","verifyBtn":"Verifying...",
    "saved":"Saved","saveFail":"Save Failed","reqFail":"Request Failed","refresh":"Refresh","testAll":"Test All","cleanupSessions":"Cleanup Sessions",
    "noAccts":"No MiMo sessions","valid":"Active","notVerified":"Not Verified","test":"Test","delete":"Delete",
    "loadFail":"Load Failed","testing":"Testing...","testFail":"Test Failed","noAcctTest":"No sessions to test",
    "allTestDone":"valid","cleanup":"Cleaning...","cleanupFail":"Cleanup failed: ","unknown":"unknown",
    "deleteConfirm":"Delete this?","deleted":"Deleted","deleteFail":"Delete Failed",
    "usageNoData":"No usage data","usageModel":"Model","usageReqs":"Requests","usageInput":"Input","usageOutput":"Output",
    "usageTotal":"Total","usageSum":"Total","usageLoadFail":"Load failed: ",
    "periodAll":"All","periodWeek":"This Week","periodToday":"Today",
    "clearConfirm":"Clear all usage data? This cannot be undone.","cleared":"Cleared","clearFail":"Clear failed",
    "configSaved":"Config saved","saveConfigFail":"Save failed",
    "parseFail":"Parse failed, check cURL format","parsing":"Parsing...","parseOk":"Parsed",
    "testConn":"Test Connection","addAcct":"Add Account","connOk":"Connected: ","connFail":"Connection failed: ",
    "acctAdded":"Account added","pasteCurl":"Please paste cURL command","pasteCookie":"Please paste Cookie string",
    "fieldsRequired":"Please fill all fields","noValidFields":"No valid fields found",
    "apiKeysLabel":"API Keys (comma separated)","saveConfig":"Save Config",
    "mimoDesc":"Xiaomi MiMo OpenAI-compatible API Dashboard","keysSaved":"Config saved","saving":"Saving...",
    "passthroughLabel":"Tool Passthrough Mode",
    "passthroughHint":"Bypass format instructions and embed raw JSON Schema tool definitions directly. Ideal for agents like Roo Code / Cline.",
    "sessionReuseLabel":"Enable HTTP Session Reuse",
    "sessionReuseHint":"Reuse persistent HTTP connections with model servers to significantly improve response times.",
    "adminPwdLabel":"Admin Password",
    "noXiaomiAccts":"No Xiaomi accounts, please add above",
    "tblAccount":"Account","tblUid":"UID","tblToken":"Token","tblDevice":"Device ID","tblCreated":"Created At","tblActions":"Actions","tblStatus":"Status","tblSource":"Source Account","tblSessions":"Sessions","tblHasPwd":"Has Password","btnExchange":"Exchange MiMo","btnTest":"Test Connection","btnDelete":"Remove"
}};
function _(k){return (_I[_lang]||_I.zh)[k]||k}
function toggleLang(){_lang=_lang==='zh'?'en':'zh';localStorage.setItem('mimo_lang',_lang);$id('langBtn').textContent=_lang==='zh'?'EN':'中文';applyI18n()}
function applyI18n(){
    document.querySelectorAll('[data-i18n]').forEach(function(el){var k=el.getAttribute('data-i18n');if(k)el.textContent=_(k)});
    document.querySelectorAll('[data-i18n-ph]').forEach(function(el){var k=el.getAttribute('data-i18n-ph');if(k)el.placeholder=_(k)});
    document.querySelector('.header p').textContent=_('mimoDesc');
    var tabs=document.querySelectorAll('.tab');
    var tkeys=['xiaomi','mimo','login','curl','cookie','apikey','usage'];
    for(var i=0;i<tkeys.length&&i<tabs.length;i++)tabs[i].textContent=_(tkeys[i])
}
document.addEventListener('DOMContentLoaded',function(){$id('langBtn').textContent=_lang==='zh'?'EN':'中文';applyI18n()});

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
    const tkeys = ['xiaomi','mimo','login','curl','cookie','apikey','usage'];
    document.querySelectorAll('.tab').forEach((el, i) => {
        el.className = 'tab' + (tkeys[i] === t ? ' active' : '');
    });
    document.querySelectorAll('.tab-panel').forEach(p => p.className = 'tab-panel');
    $id('panel-' + t).className = 'tab-panel active';
    if (t === 'xiaomi') loadXiaomiAccounts();
    if (t === 'mimo') loadMimoAccounts();
    if (t === 'usage') loadUsage();
}

// ═══════════════════════════════════════════════════════════
// 配置加载/保存
// ═══════════════════════════════════════════════════════════

async function loadConfig() {
    try {
        const r = await fetch('/api/config');
        cfg = await r.json();
        $id('apiKeys').value = cfg.api_keys || '';
        $id('passthroughToggle').checked = !!cfg.tools_passthrough;
        $id('noParsingToggle').checked = !!cfg.tools_no_parsing;
        $id('sessionReuseToggle').checked = cfg.session_reuse !== false;
        $id('debugModeToggle').checked = !!cfg.debug_mode;
        $id('adminPassword').value = cfg.admin_password || '';
        $id('sessionLimit').value = cfg.session_limit_per_account || 10;
        $id('resinUrl').value = cfg.resin_url || '';
        $id('resinPlatformName').value = cfg.resin_platform_name || 'Default';
    } catch (e) {}
}

async function saveKeys() {
    cfg.api_keys = $id('apiKeys').value;
    cfg.tools_passthrough = $id('passthroughToggle').checked;
    cfg.tools_no_parsing = $id('noParsingToggle').checked;
    cfg.session_reuse = $id('sessionReuseToggle').checked;
    cfg.debug_mode = $id('debugModeToggle').checked;
    cfg.admin_password = $id('adminPassword').value || 'admin';
    cfg.session_limit_per_account = parseInt($id('sessionLimit').value) || 10;
    cfg.resin_url = $id('resinUrl').value.trim();
    cfg.resin_platform_name = $id('resinPlatformName').value.trim() || 'Default';
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

// ═══════════════════════════════════════════════════════════
// 小米 Passport 账号管理
// ═══════════════════════════════════════════════════════════

async function loadXiaomiAccounts() {
    try {
        const r = await fetch('/api/xiaomi-accounts');
        const d = await r.json();
        const el = $id('xiaomiAccounts');
        if (!d.accounts || !d.accounts.length) {
            el.innerHTML = `<div class="empty">${_('noXiaomiAccts')}</div>`;
            return;
        }
        let html = `
            <div class="datagrid-scroll">
                <table class="datagrid">
                    <thead>
                        <tr>
                            <th>${_('tblAccount')}</th>
                            <th>${_('tblUid')}</th>
                            <th>${_('tblToken')}</th>
                            <th>${_('tblDevice')}</th>
                            <th>${_('tblCreated')}</th>
                            <th>${_('tblActions')}</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        html += d.accounts.map((a, i) => `
            <tr>
                <td>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span>${a.email || 'UID: ' + a.user_id}</span>
                        ${a.has_password ? `<span class="badge badge-valid" style="background:rgba(129,140,248,0.15);color:#a5b4fc;border-color:rgba(129,140,248,0.3)">${_('tblHasPwd')}</span>` : ''}
                    </div>
                </td>
                <td>${a.user_id}</td>
                <td><code>${a.pass_token_masked}</code></td>
                <td><span style="opacity:0.7">${a.device_id || '-'}</span></td>
                <td><span style="opacity:0.5; font-size:12px;">${a.created_at || '-'}</span></td>
                <td>
                    <div class="actions">
                        <button class="btn-success" style="padding:6px 12px; font-size:12px" onclick="exchangeXiaomi(${i})">${_('btnExchange')}</button>
                        <button class="btn-danger" style="padding:6px 12px; font-size:12px; background:transparent; color:#fb7185; border:1px solid rgba(251, 113, 133, 0.3);" onclick="delXiaomi(${i})">${_('btnDelete')}</button>
                    </div>
                </td>
            </tr>
        `).join('');
        html += `
                    </tbody>
                </table>
            </div>
        `;
        el.innerHTML = html;
    } catch (e) {
        $id('xiaomiAccounts').innerHTML = `<div class="empty" style="color:#fb7185">${_('loadFail')}</div>`;
    }
}

async function addXiaomiAccount() {
    const uid = $id('xi-uid').value.trim();
    const token = $id('xi-token').value.trim();
    const email = $id('xi-email').value.trim();
    const device = $id('xi-device').value.trim();
    if (!uid || !token) { toast('请填写 userId 和 passToken', true); return; }
    try {
        const r = await fetch('/api/xiaomi-account/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ userId: uid, passToken: token, email: email, deviceId: device })
        });
        const d = await r.json();
        if (d.ok) {
            toast(d.message || '添加成功');
            $id('xi-uid').value = ''; $id('xi-token').value = ''; $id('xi-email').value = ''; $id('xi-device').value = '';
            loadXiaomiAccounts();
        } else {
            toast(d.error || '添加失败', true);
        }
    } catch (e) { toast('请求失败', true); }
}

async function delXiaomi(i) {
    if (!confirm('确定移除此小米账号？')) return;
    try {
        await fetch('/api/xiaomi-accounts/' + i, { method: 'DELETE' });
        toast('已移除');
        loadXiaomiAccounts();
    } catch (e) { toast('删除失败', true); }
}

async function exchangeXiaomi(i) {
    const btn = event.target;
    btn.disabled = true; btn.textContent = _lang === 'zh' ? '兑换中...' : 'Exchanging...';
    try {
        const r = await fetch('/api/xiaomi-accounts/' + i + '/exchange', { method: 'POST' });
        const d = await r.json();
        if (d.ok) {
            toast(_lang === 'zh' ? '兑换成功！' : 'Exchanged successfully!');
            loadXiaomiAccounts();
        } else {
            toast(d.error || (_lang === 'zh' ? '兑换失败' : 'Exchange failed'), true);
        }
    } catch (e) { toast('请求失败', true); }
    btn.disabled = false; btn.textContent = _('btnExchange');
}

async function exchangeAllXiaomi() {
    const btn = event.target;
    btn.disabled = true; btn.textContent = '批量兑换中...';
    try {
        const r = await fetch('/api/xiaomi-accounts/exchange-all', { method: 'POST' });
        const d = await r.json();
        if (d.ok) {
            toast(d.message || '兑换完成');
            if (d.errors && d.errors.length) {
                console.warn('兑换错误:', d.errors);
            }
            loadXiaomiAccounts();
        } else {
            toast('批量兑换失败', true);
        }
    } catch (e) { toast('请求失败', true); }
    btn.disabled = false; btn.textContent = '批量兑换 MiMo';
}

function exportXiaomiJson() {
    window.open('/api/xiaomi-account/export-json', '_blank');
}

async function importXiaomiJson(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (e) => {
        try {
            const data = JSON.parse(e.target.result);
            if (!Array.isArray(data)) { toast('JSON 格式错误: 必须是数组', true); return; }
            const r = await fetch('/api/xiaomi-account/import-json', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const res = await r.json();
            if (res.ok) { toast(`导入了 ${res.added} 个账号`); loadXiaomiAccounts(); }
            else toast('导入失败: ' + res.error, true);
        } catch (err) { toast('解析 JSON 失败: ' + err.message, true); }
        finally { event.target.value = ''; }
    };
    reader.readAsText(file);
}

// ═══════════════════════════════════════════════════════════
// MiMo 会话管理
// ═══════════════════════════════════════════════════════════

async function loadMimoAccounts() {
    try {
        const r = await fetch('/api/accounts');
        const d = await r.json();
        const el = $id('mimoAccounts');
        if (!d.accounts || !d.accounts.length) {
            el.innerHTML = `<div class="empty">${_('noAccts')}</div>`;
            return;
        }
        const limit = parseInt($id('sessionLimit').value) || 10;
        let html = `
            <div class="datagrid-scroll">
                <table class="datagrid">
                    <thead>
                        <tr>
                            <th>${_('tblStatus')}</th>
                            <th>${_('tblAccount')}</th>
                            <th>${_('tblUid')}</th>
                            <th>${_('tblToken')}</th>
                            <th>${_('tblSource')}</th>
                            <th>${_('tblSessions')}</th>
                            <th>${_('tblActions')}</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        html += d.accounts.map((a, i) => {
            const isOverload = (a.active_sessions || 0) >= limit;
            return `
                <tr>
                    <td>
                        <div style="display:flex; align-items:center; gap:6px;">
                            <span class="status-dot" style="background-color:${a.is_valid ? '#4ade80' : '#fb7185'}; width:8px; height:8px; border-radius:50%; display:inline-block; box-shadow:0 0 8px ${a.is_valid ? '#4ade80' : '#fb7185'}"></span>
                            <span class="badge ${a.is_valid ? 'badge-valid' : 'badge-invalid'}" style="font-size:11px;">${a.is_valid ? 'Active' : 'Error'}</span>
                        </div>
                    </td>
                    <td><b>${a.email || 'UID: ' + a.user_id}</b></td>
                    <td>${a.user_id || '-'}</td>
                    <td><code>${a.token_masked}</code></td>
                    <td><span style="opacity:0.7">${a.source_account || '-'}</span></td>
                    <td>
                        <span style="color: ${isOverload ? '#fb7185' : '#e2e8f0'}; font-weight: bold;">${a.active_sessions || 0}</span> / ${limit}
                    </td>
                    <td>
                        <div class="actions">
                            <button class="btn-outline" style="padding:6px 12px; font-size:12px" onclick="testMimo(${i})">${_('btnTest')}</button>
                            <button class="btn-danger" style="padding:6px 12px; font-size:12px; background:transparent; color:#fb7185; border:1px solid rgba(251, 113, 133, 0.3);" onclick="delMimo(${i})">${_('btnDelete')}</button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
        html += `
                    </tbody>
                </table>
            </div>
        `;
        el.innerHTML = html;
    } catch (e) {
        $id('mimoAccounts').innerHTML = `<div class="empty" style="color:#fb7185">${_('loadFail')}</div>`;
    }
}

async function testMimo(i) {
    const btn = event.target;
    btn.disabled = true; btn.textContent = _lang === 'zh' ? '测试中...' : 'Testing...';
    try {
        const r = await fetch('/api/accounts/' + i + '/test', { method: 'POST' });
        const d = await r.json();
        if (d.ok) { toast(_lang === 'zh' ? '连接成功' : 'Connection successful'); loadMimoAccounts(); }
        else toast((_lang === 'zh' ? '连接失败: ' : 'Connection failed: ') + d.error, true);
    } catch (e) { toast(_('testFail'), true); }
    btn.disabled = false; btn.textContent = _('btnTest');
}

async function testAllMimo() {
    const btn = event.target;
    btn.disabled = true; btn.textContent = _lang === 'zh' ? '测试中...' : 'Testing...';
    try {
        const r = await fetch('/api/accounts');
        const d = await r.json();
        if (!d.accounts || !d.accounts.length) { toast(_('noAcctTest'), true); btn.disabled = false; btn.textContent = _lang === 'zh' ? '测试全部有效性' : 'Test All Status'; return; }
        let ok = 0;
        for (let i = 0; i < d.accounts.length; i++) {
            btn.textContent = (_lang === 'zh' ? '测试 (' : 'Testing (') + (i + 1) + '/' + d.accounts.length + ')';
            try {
                const r2 = await fetch('/api/accounts/' + i + '/test', { method: 'POST' });
                const d2 = await r2.json();
                if (d2.ok) ok++;
            } catch (e) {}
        }
        toast(ok + '/' + d.accounts.length + (_lang === 'zh' ? ' 会话测试有效' : ' sessions are valid'));
        loadMimoAccounts();
    } catch (e) { toast(_('reqFail'), true); }
    btn.disabled = false; btn.textContent = _lang === 'zh' ? '测试全部有效性' : 'Test All Status';
}

async function delMimo(i) {
    if (!confirm('确定要移除该 MiMo 会话？')) return;
    try {
        await fetch('/api/accounts/' + i, { method: 'DELETE' });
        toast('会话已移除');
        loadMimoAccounts();
    } catch (e) { toast(_('deleteFail'), true); }
}

async function syncMimoSessions() {
    try {
        const r = await fetch('/api/account/sync-json', { method: 'POST' });
        const d = await r.json();
        if (d.ok) { toast('同步完成'); loadMimoAccounts(); }
        else toast('同步失败: ' + d.error, true);
    } catch (e) { toast('请求失败', true); }
}

async function cleanupSessions() {
    const btn = event.target;
    btn.disabled = true; btn.textContent = '清理中...';
    try {
        const r = await fetch('/api/cleanup', { method: 'POST' });
        const d = await r.json();
        if (d.ok) { toast(d.msg); loadMimoAccounts(); }
        else toast('清理失败: ' + (d.msg || '未知'), true);
    } catch (e) { toast('清理失败: ' + e.message, true); }
    btn.disabled = false; btn.textContent = '清理过期会话';
}

function exportMimoJson() {
    window.open('/api/account/export-json', '_blank');
}

async function importMimoJson(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (e) => {
        try {
            const data = JSON.parse(e.target.result);
            if (!Array.isArray(data)) { toast('JSON 格式错误: 必须是数组', true); return; }
            const r = await fetch('/api/account/import-json', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const res = await r.json();
            if (res.ok) { toast(`导入了 ${res.added} 个会话`); loadMimoAccounts(); }
            else toast('导入失败: ' + res.error, true);
        } catch (err) { toast('解析 JSON 失败: ' + err.message, true); }
        finally { event.target.value = ''; }
    };
    reader.readAsText(file);
}

// ═══════════════════════════════════════════════════════════
// cURL / Cookie 导入
// ═══════════════════════════════════════════════════════════

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
                <button class="btn-success" onclick="saveParsed()">保存为 MiMo 会话</button>
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
        const r = await fetch('/api/account/import-cookie', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                serviceToken: parsed.service_token,
                userId: parsed.user_id,
                xiaomichatbot_ph: parsed.xiaomichatbot_ph
            })
        });
        const d = await r.json();
        if (d.ok) {
            parsed = null;
            $id('curl').value = '';
            $id('curlResult').innerHTML = '';
            toast('MiMo 会话已保存');
            switchTab('mimo');
        } else {
            toast(d.error || '保存失败', true);
        }
    } catch (e) { toast(_('saveFail'), true); }
    finally { btn.disabled = false; btn.textContent = '保存为 MiMo 会话'; }
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
    if (map.userId) $id('c-uid').value = map.userId;
    if (map.xiaomichatbot_ph) $id('c-ph').value = map.xiaomichatbot_ph;

    const filled = [map.serviceToken, map.userId, map.xiaomichatbot_ph].filter(Boolean).length;
    if (filled > 0) toast('已填充 ' + filled + ' 个字段');
    else toast('未识别到有效字段', true);
}

async function saveCookie() {
    const st = $id('c-st').value.trim();
    const uid = $id('c-uid').value.trim();
    const ph = $id('c-ph').value.trim();
    if (!st || !uid) { toast('请填写 serviceToken 和 userId', true); return; }

    const btn = $id('btn-save-cookie');
    btn.disabled = true; btn.textContent = _('verifyBtn');
    try {
        const r = await fetch('/api/account/import-cookie', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ serviceToken: st, userId: uid, xiaomichatbot_ph: ph })
        });
        const d = await r.json();
        if (d.ok) {
            toast('MiMo 会话已保存');
            $id('c-st').value = ''; $id('c-uid').value = ''; $id('c-ph').value = ''; $id('c-raw').value = '';
            switchTab('mimo');
        } else {
            toast(d.error || '保存失败', true);
        }
    } catch (e) { toast(_('reqFail'), true); }
    finally { btn.disabled = false; btn.textContent = _('saveAcct'); }
}

// ═══════════════════════════════════════════════════════════
// 登录 (密码 / Passport Token)
// ═══════════════════════════════════════════════════════════

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
            switchTab('mimo');
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
            switchTab('mimo');
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
        switchTab('mimo');
    } catch (e) {
        toast('请求异常: ' + e.message, true);
    } finally {
        btn.disabled = false; btn.textContent = '验证并导入';
    }
}

// ═══════════════════════════════════════════════════════════
// 用量统计
// ═══════════════════════════════════════════════════════════

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
            $id('usageContent').innerHTML = `<div class="empty">${_('usageNoData')}</div>`;
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
    switchTab('xiaomi');
});