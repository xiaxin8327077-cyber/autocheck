import assert from 'node:assert/strict';
import { FakeElement } from './frontend_workbench_dom.mjs';
import { createCandidateOptionsPanel } from './components/candidate_options.mjs';

// The browser animation boundary is instrumented; the panel and its updates are real.
const calls = [];
FakeElement.prototype.animate = function (frames, options) {
  const animation = { cancelled: false, cancel() { this.cancelled = true; } };
  calls.push({ target: this, frames, options, animation });
  return animation;
};
globalThis.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} });
document.documentElement = new FakeElement('html');
document.documentElement.dataset.animations = 'off';
document.body = new FakeElement('body');
document.body.classList.add('animations-disabled');

const panel = createCandidateOptionsPanel({ listen: (node, type, handler) => node.addEventListener(type, handler) });
const payload = { candidate_options: [
  { id: 'a', label: '方案 A', candidate: {} },
  { id: 'b', label: '方案 B', candidate: {} },
] };
const detail = new FakeElement('div');
detail.style = {};
function mount(id) {
  panel.update(payload, { activeId: id });
  if (id) panel.getSlotEl(id).append(detail);
  panel.animateExpanded(id);
}

assert.equal(typeof panel.animateExpanded, 'function', '展开时应提供动画入口');
mount('a');
assert.equal(calls.length, 1, '即使关闭系统动画也应播放展开动画');
assert.equal(calls[0].target, detail);
assert.ok(calls[0].options.duration > 0 && calls[0].options.duration <= 300, '展开动画应短暂');
assert.equal(calls[0].frames.at(-1).opacity, 1);
assert.ok(!detail.style.transform, '动画不应留下行内 transform');
mount('a');
assert.equal(calls.length, 1, '普通更新和替换 slot 不应重播');
mount('b');
assert.equal(calls.length, 2, '切换方案应播放动画');
assert.equal(calls[0].animation.cancelled, true, '切换时取消上一次动画');
mount('');
assert.equal(calls[1].animation.cancelled, true, '收起时取消动画');
mount('b');
assert.equal(calls.length, 3, '收起后重新展开应播放动画');
delete FakeElement.prototype.animate;
assert.doesNotThrow(() => { mount(''); mount('a'); }, '缺少动画 API 时仍可展开');
console.log(JSON.stringify({ ok: true }));
