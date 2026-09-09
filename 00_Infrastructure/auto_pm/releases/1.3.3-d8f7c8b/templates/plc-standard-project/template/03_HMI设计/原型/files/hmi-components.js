/**
 * STD-910 工业人机界面标准 Web Components 图形部件库 (hmi-components.js)
 * 遵循 Web Components 标准规范，零外部依赖，即插即用。
 */

// 1. <hmi-dro>: 工业数显表盘
class HmiDro extends HTMLElement {
  static get observedAttributes() { return ['label', 'value', 'unit', 'tag', 'color']; }
  connectedCallback() { this.render(); }
  attributeChangedCallback() { this.render(); }
  render() {
    const label = this.getAttribute('label') || '';
    const val = this.getAttribute('value') || '--';
    const unit = this.getAttribute('unit') || '';
    const tag = this.getAttribute('tag') ? ` (${this.getAttribute('tag')})` : '';
    const color = this.getAttribute('color') || 'var(--cyan)';

    this.innerHTML = `
      <div class="dro-box">
        <span class="dro-label">${label}<span style="font-size:10px; color:var(--text-dim);">${tag}</span></span>
        <span class="dro-value" style="color:${color};">${val} ${unit}</span>
      </div>
    `;
  }
}
customElements.define('hmi-dro', HmiDro);

// 2. <hmi-led>: 发光状态指示灯
class HmiLed extends HTMLElement {
  static get observedAttributes() { return ['color', 'state', 'label']; }
  connectedCallback() { this.render(); }
  attributeChangedCallback() { this.render(); }
  render() {
    const color = this.getAttribute('color') || 'green';
    const state = this.getAttribute('state') || 'on';
    const label = this.getAttribute('label') || '';
    const activeClass = (state === 'on' || state === 'true') ? color : '';

    this.innerHTML = `
      <span style="display:inline-flex; align-items:center; gap:6px; font-size:12px;">
        <span class="led ${activeClass}"></span>
        ${label ? `<span>${label}</span>` : ''}
      </span>
    `;
  }
}
customElements.define('hmi-led', HmiLed);

// 3. <hmi-btn>: 工业触感按钮
class HmiBtn extends HTMLElement {
  connectedCallback() {
    const type = this.getAttribute('type') || '';
    const size = this.getAttribute('size') || '';
    const content = this.innerHTML;
    this.innerHTML = `<button class="btn ${type} ${size}">${content}</button>`;
  }
}
customElements.define('hmi-btn', HmiBtn);

// 4. <hmi-axis-dro>: 伺服轴黄金信号综合卡片
class HmiAxisDro extends HTMLElement {
  static get observedAttributes() { return ['axis-name', 'pos', 'vel', 'torque', 'in-pos', 'alarm', 'son']; }
  connectedCallback() { this.render(); }
  attributeChangedCallback() { this.render(); }
  render() {
    const name = this.getAttribute('axis-name') || '伺服轴';
    const pos = this.getAttribute('pos') || '0.00 mm';
    const vel = this.getAttribute('vel') || '0.0 mm/s';
    const torque = this.getAttribute('torque') || '0 %';
    const son = this.getAttribute('son') === 'true';
    const inPos = this.getAttribute('in-pos') === 'true';
    const alarm = this.getAttribute('alarm') === 'true';

    this.innerHTML = `
      <div class="panel" style="background:var(--bg-card); padding:10px;">
        <div class="panel-header" style="margin-bottom:6px; padding-bottom:4px;">
          <span style="font-size:13px; font-weight:bold; color:#fff;">${name}</span>
          <span style="display:flex; gap:6px;">
            <span class="badge" style="background:${son ? 'var(--success)' : '#4a5568'};">SON</span>
            <span class="badge" style="background:${inPos ? 'var(--cyan)' : '#4a5568'};">InPos</span>
            ${alarm ? '<span class="badge" style="background:var(--danger);">ALM</span>' : ''}
          </span>
        </div>
        <div style="display:flex; flex-direction:column; gap:4px; font-size:12px;">
          <div class="dro-box"><span class="dro-label">实际坐标</span><span class="dro-value">${pos}</span></div>
          <div class="dro-box"><span class="dro-label">运行速度</span><span class="dro-value" style="color:var(--text-main);">${vel}</span></div>
          <div class="dro-box"><span class="dro-label">负载转矩</span><span class="dro-value" style="color:var(--warning);">${torque}</span></div>
        </div>
      </div>
    `;
  }
}
customElements.define('hmi-axis-dro', HmiAxisDro);

// 5. <hmi-conveyor-unit>: 单层输送机控制单元
class HmiConveyorUnit extends HTMLElement {
  connectedCallback() {
    const layer = this.getAttribute('layer') || '1';
    const speed = this.getAttribute('speed') || '15.0 m/min';
    const status = this.getAttribute('status') || '正转运行';

    this.innerHTML = `
      <div style="display:flex; align-items:center; justify-content:space-between; background:var(--bg-input); padding:8px 12px; border-radius:4px; border:1px solid var(--border-color);">
        <div>
          <div style="font-size:13px; font-weight:bold; color:#fff;">L${layer} 层分料输送机</div>
          <div style="font-size:11px; color:var(--text-muted);">设定速度: ${speed} · <span style="color:var(--success);">${status}</span></div>
        </div>
        <div style="display:flex; gap:6px;">
          <button class="btn sm" onclick="jogConveyor(${layer}, 'fwd')">正转</button>
          <button class="btn sm" onclick="jogConveyor(${layer}, 'rev')">反转</button>
          <button class="btn sm" onclick="toggleStopper(${layer})">阻挡气缸</button>
          <button class="btn sm" onclick="toggleSeparator(${layer})">分料气缸</button>
        </div>
      </div>
    `;
  }
}
customElements.define('hmi-conveyor-unit', HmiConveyorUnit);

// 6. <hmi-handshake>: STD-820 握手波形组件
class HmiHandshake extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `
      <div style="background:var(--bg-input); padding:10px; border-radius:4px; border:1px solid var(--border-color);">
        <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
          <span style="font-size:12px; font-weight:bold; color:var(--cyan);">STD-820 信号交互矩阵</span>
          <span style="font-size:11px; color:var(--success);">● 4.0s 持续心跳正常</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:6px; font-size:11px; text-align:center;">
          <div class="dro-box" style="flex-direction:column; gap:4px;"><span class="dro-label">允许送料 (X76)</span><span class="led green"></span></div>
          <div class="dro-box" style="flex-direction:column; gap:4px;"><span class="dro-label">允许抓料 (Y44)</span><span class="led green"></span></div>
          <div class="dro-box" style="flex-direction:column; gap:4px;"><span class="dro-label">取料完成 (X102)</span><span class="led"></span></div>
          <div class="dro-box" style="flex-direction:column; gap:4px;"><span class="dro-label">安全区隔离 (Y47)</span><span class="led red"></span></div>
        </div>
      </div>
    `;
  }
}
customElements.define('hmi-handshake', HmiHandshake);
