const assert = require('node:assert/strict');
let page = 'home', click, frameId = 0;
const ops = [], queries = [], observers = [], frames = new Map();
let settingsPageLoadScope = null;
function escapeHtml(value) { return String(value); }
function matches(el, selector) {
  return selector.split(',').some(part => {
    part = part.trim();
    const not = part.match(/:not\(([^)]+)\)/);
    if (not && matches(el, not[1])) return false;
    part = part.replace(/:not\([^)]+\)/g, '');
    const tag = part.match(/^[a-z]+/i);
    if (tag && el.tagName !== tag[0].toUpperCase()) return false;
    const id = part.match(/#([\w-]+)/);
    if (id && el.id !== id[1]) return false;
    if ([...part.matchAll(/\.([\w-]+)/g)].some(m => !el.classes.has(m[1]))) return false;
    if (part.includes('[hidden]') && !el.hidden) return false;
    return true;
  });
}
class El {
  constructor(tag, id = '') {
    this.nodeType = 1; this.tagName = tag.toUpperCase(); this.id = id;
    this.dataset = {}; this.children = []; this.classes = new Set(); this.attributes = new Map();
    this._hidden = false; this.type = 'text'; this.options = []; this.selectedIndex = 0;
    this.listeners = new Map();
    this.classList = {
      contains: c => this.classes.has(c),
      add: c => { this.classes.add(c); this.write('class'); },
      remove: c => { this.classes.delete(c); this.write('class'); },
      toggle: (c, on) => { on ? this.classes.add(c) : this.classes.delete(c); this.write('class'); },
    };
    this.style = { values: new Map(), setProperty: (name, value) => { this.style.values.set(name, value); this.write('style'); } };
  }
  get isConnected() { return this === body || !!this.parentNode?.isConnected; }
  write(name) { if (this.isConnected) ops.push(`write:${name}:${this.id}`); }
  get className() { return [...this.classes].join(' '); }
  set className(value) { this.classes = new Set(value.split(/\s+/).filter(Boolean)); this.write('class'); }
  get hidden() { return this._hidden; }
  set hidden(value) { this._hidden = value; this.write('hidden'); }
  set innerHTML(value) { this._html = value; this.children.forEach(c => { c.parentNode = null; }); this.children = []; this.write('html'); }
  get innerHTML() { return this._html || ''; }
  set textContent(value) { this._text = value; this.write('text'); }
  get textContent() { return this._text || ''; }
  get parentElement() { return this.parentNode; }
  getAttribute(name) { return name === 'type' ? this.type : this.attributes.get(name) ?? null; }
  setAttribute(name, value) { this.attributes.set(name, value); this.write('attribute'); }
  matches(selector) { return matches(this, selector); }
  closest(selector) { return this.matches(selector) ? this : this.parentNode?.closest(selector) || null; }
  contains(el) { return el === this || this.children.some(c => c.contains(el)); }
  querySelectorAll(selector) {
    queries.push([this.id, selector]);
    const found = [];
    const visit = el => { el.children.forEach(c => { if (c.matches(selector)) found.push(c); visit(c); }); };
    visit(this); return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  appendChild(el) { el.remove(); el.parentNode = this; this.children.push(el); this.write('append'); return el; }
  insertBefore(el, before) { el.remove(); el.parentNode = this; this.children.splice(this.children.indexOf(before), 0, el); this.write('insert'); }
  getBoundingClientRect() { ops.push(`read:rect:${this.id}`); return { width: 120, height: 32, top: 100, bottom: 132, left: 20 }; }
  addEventListener(type, listener) { this.listeners.set(type, listener); }
  dispatchEvent(event) { this.listeners.get(event.type)?.(event); }
  focus(options) { document.activeElement = this; this.focusOptions = options; this.write('focus'); }
  setSelectionRange(start, end, direction) { this.selectionStart = start; this.selectionEnd = end; this.selectionDirection = direction; this.write('selection'); }
  remove() {
    if (this.parentNode) {
      if (document.activeElement === this) {
        document.activeElement = body;
        this.selectionStart = 0; this.selectionEnd = 0; this.selectionDirection = 'none';
        this.listeners.get('blur')?.();
      }
      const parent = this.parentNode; parent.write('remove'); parent.children.splice(parent.children.indexOf(this), 1); this.parentNode = null;
    }
  }
}
function element(tag, id) { return new El(tag, id); }
const body = element('body', 'body');
const root = { getAttribute: () => page };
const document = {
  body, activeElement: body, documentElement: root, createElement: element,
  querySelectorAll: selector => { queries.push(['document', selector]); return body.querySelectorAll(selector); },
  getElementById: id => body.querySelectorAll('section').find(el => el.id === id),
  addEventListener: (type, fn, capture) => { if (type === 'click') { click = fn; assert.equal(capture, true); } },
};
const window = { innerHeight: 800, innerWidth: 1200, addEventListener() {}, clearTimeout() {},
  getComputedStyle: el => { ops.push(`read:computed:${el.id}`); return { width: '120px', height: '32px', fontSize: '13px', fontWeight: '400' }; },
};
const requestAnimationFrame = fn => { frames.set(++frameId, fn); return frameId; };
const cancelAnimationFrame = id => frames.delete(id);
class MutationObserver {
  constructor(callback) { this.callback = callback; observers.push(this); }
  observe(target, config) { this.target = target; this.config = config; }
}
function control(tag, id, parent = body) {
  const el = element(tag, id);
  if (tag === 'select') el.options = [{ textContent: 'Example', value: 'example' }];
  parent.appendChild(el); return el;
}
function enhanced(controls) { return controls.filter(el => el.classes.has('custom-select-native') || el.classes.has('custom-input-native')); }
function nextFrame() { const work = [...frames.values()]; frames.clear(); ops.length = 0; work.forEach(fn => fn()); }
function assertReadPhaseBeforeWritePhase() {
  const firstWrite = ops.findIndex(op => op.startsWith('write:'));
  assert.ok(!ops.slice(firstWrite).some(op => op.startsWith('read:')), 'layout reads must precede connected DOM writes within each frame: ' + ops.join(', '));
}
function drainFrames(checkOrder = false) {
  for (let i = 0; frames.size; i++) {
    assert.ok(i < 100, 'frame queue must settle'); nextFrame();
    if (checkOrder) assertReadPhaseBeforeWritePhase();
  }
}
function bodyObserver() { return observers.find(o => o.target === body); }
function pageObserver() { return observers.find(o => o.target === root); }
__SOURCE__
__SCENARIO__
