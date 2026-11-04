/* ============================================================
 * 工业自动化 HMI 原型标准交互引擎 (STD-910 / CP-301)
 * 标准 11 页 SCADA 导航、点动调试、配方管理与报警模拟
 * ============================================================ */

// 标准 11 页画面清单 (CP-301)
const pages = [
  { id: 'login',    name: '01 登录' },
  { id: 'main',     name: '02 总览' },
  { id: 'process',  name: '03 自动流程' },
  { id: 'manual',   name: '04 手动控制' },
  { id: 'axis',     name: '05 伺服点动' },
  { id: 'io',       name: '06 IO 监控' },
  { id: 'recipe',   name: '07 配方参数' },
  { id: 'alarm',    name: '08 报警管理' },
  { id: 'comm',     name: '09 外部交握' },
  { id: 'trend',    name: '10 趋势诊断' },
  { id: 'settings', name: '11 系统设置' },
];

let currentStep = 0;
const sfcSteps = [0, 10, 20, 30, 40, 50, 60, 70];

let axisPos = { X: 1250.5, Z: 420.0, A: 180.0 };

function renderNavTabs() {
  const navTabs = document.getElementById('navTabs');
  if (!navTabs) return;
  navTabs.innerHTML = '';
  pages.forEach(p => {
    const btn = document.createElement('button');
    btn.className = 'nav-tab' + (p.id === 'login' ? ' active' : '');
    btn.textContent = p.name;
    btn.onclick = () => goPage(p.id);
    navTabs.appendChild(btn);
  });
}

function goPage(id) {
  document.querySelectorAll('.page').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach((el, i) => {
    el.classList.toggle('active', pages[i] && pages[i].id === id);
  });
  const target = document.getElementById('page-' + id);
  if (target) {
    target.classList.add('active');
  } else {
    console.warn(`Target page not found: page-${id}`);
  }
}

function doLogin() {
  const user = document.getElementById('loginUser').value || 'operator';
  const badge = document.getElementById('currentUserBadge');
  if (badge) badge.textContent = `${user} (已登录)`;
  goPage('main');
}

function jogAxis(axis, delta) {
  if (axisPos[axis] !== undefined) {
    axisPos[axis] = Math.round((axisPos[axis] + delta) * 10) / 10;
    const disp = document.getElementById(`axis${axis}Display`);
    if (disp) disp.textContent = `${axisPos[axis].toFixed(2)} mm`;
    const mainDisp = document.getElementById(`posAxis${axis}`);
    if (mainDisp) mainDisp.textContent = `${axisPos[axis].toFixed(1)} mm`;
  }
}

function toggleCylinder(btnId) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  const isAlt = btn.classList.toggle('active');
  if (isAlt) {
    btn.style.background = '#22c55e';
    btn.style.color = '#fff';
  } else {
    btn.style.background = '';
    btn.style.color = '';
  }
}

function toggleIO(ioId) {
  const el = document.getElementById(`io-${ioId}`);
  if (!el) return;
  el.classList.toggle('active');
}

function stepProcess() {
  currentStep = (currentStep + 1) % sfcSteps.length;
  sfcSteps.forEach((step, idx) => {
    const el = document.getElementById(`sfc-${step}`);
    if (el) {
      el.classList.toggle('active', idx === currentStep);
    }
  });
  const kpiStep = document.getElementById('kpiStep');
  if (kpiStep) {
    kpiStep.textContent = `${sfcSteps[currentStep]}_工位动作执行`;
  }
}

function resetProcess() {
  currentStep = 0;
  stepProcess();
}

function triggerAlarm() {
  const tbody = document.getElementById('alarmTbody');
  if (!tbody) return;
  const tr = document.createElement('tr');
  const now = new Date().toLocaleTimeString();
  tr.innerHTML = `<td>E-9999</td><td>${now}</td><td>系统总线</td><td>[模拟测试] 急停回路断开或通信超时</td><td><span class="badge red">紧急</span></td>`;
  tbody.prepend(tr);
  const badge = document.getElementById('alarmStatusBadge');
  if (badge) badge.innerHTML = '<span class="led red"></span>活动报警: 1 项';
  alert('⚠ 模拟报警已触发: E-9999 [模拟测试] 急停回路断开或通信超时');
}

function resetAlarm() {
  const tbody = document.getElementById('alarmTbody');
  if (tbody) tbody.innerHTML = '';
  const badge = document.getElementById('alarmStatusBadge');
  if (badge) badge.innerHTML = '<span class="led green"></span>无活动报警';
  alert('✅ 所有活动报警已复位。');
}

function saveRecipe() {
  alert('💾 配方参数已成功保存并同步下发至 PLC 保持寄存器 (DB_Recipe)！');
}

function reloadRecipe() {
  alert('🔄 已从 PLC 重新读取最新配方参数。');
}

function tick() {
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const time = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  const full = `${date} ${time}`;

  const el = document.getElementById('clockMain');
  if (el) el.textContent = full;
}

function fitToScreen() {
  const DESIGN_W = 1280;
  const DESIGN_H = 800;
  const inner = document.getElementById('appScaleInner');
  if (!inner) return;
  const sw = window.innerWidth / DESIGN_W;
  const sh = window.innerHeight / DESIGN_H;
  const scale = Math.min(sw, sh, 1);
  inner.style.transform = `scale(${scale})`;
}

window.addEventListener('resize', fitToScreen);
window.addEventListener('load', () => {
  renderNavTabs();
  fitToScreen();
  setInterval(tick, 1000);
  tick();
});
