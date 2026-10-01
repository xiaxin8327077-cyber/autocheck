"""Run real public-control functions with instrumented DOM reads and frame scheduling.

Synthetic DOM checks ordering and bounded work, not browser or production timing.
"""

from pathlib import Path
import re
import subprocess


APP_JS = Path(__file__).resolve().parents[1] / "src/auto_check/web/app.js"
HARNESS = Path(__file__).with_name("custom_control_render_harness.cjs")


def run_scenario(scenario):
    source = APP_JS.read_text(encoding="utf-8")
    controls = source[source.index("const customSelectStates ="):source.index("/* ===== Filtering ===== */")]
    cancel = re.search(r"function cancelSettingsPageLoad\(\) \{.*?\n\}", source, re.S).group()
    script = HARNESS.read_text(encoding="utf-8")
    script = script.replace("__SOURCE__", controls + "\n" + cancel).replace("__SCENARIO__", scenario)
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr


def test_enhancement_yields_and_reads_each_batch_before_connected_writes():
    run_scenario("""
const controls = Array.from({ length: 35 }, (_, i) => control(i % 2 ? 'input' : 'select', 'field' + i));
initializeCustomSelects();
assert.equal(enhanced(controls).length, 0, 'initialization must yield to navigation');
assert.ok(frames.size);
nextFrame();
const first = enhanced(controls).length;
assert.ok(first > 0 && first < controls.length, 'one frame must not enhance the entire form');
assertReadPhaseBeforeWritePhase();
assert.ok(frames.size, 'remaining controls need a later frame');
drainFrames(true);
assert.equal(enhanced(controls).length, controls.length);
for (const el of controls) {
  const shell = el.parentNode;
  assert.equal(shell.style.values.get(el.tagName === 'SELECT' ? '--select-width' : '--input-width'), '120px');
  assert.equal(shell.style.values.get(el.tagName === 'SELECT' ? '--select-height' : '--input-height'), '32px');
}
""")


def test_hidden_and_collapsed_fields_wait_for_expansion_without_layout_reads():
    run_scenario("""
const hiddenGroup = element('div', 'hidden-fields'); hiddenGroup.hidden = true; body.appendChild(hiddenGroup);
const collapsedGroup = element('div', 'collapsed-fields'); collapsedGroup.className = 'collapsible-body collapsed'; body.appendChild(collapsedGroup);
const hidden = control('input', 'hidden', hiddenGroup);
const collapsed = control('select', 'collapsed', collapsedGroup);
initializeCustomSelects(); drainFrames();
assert.equal(enhanced([hidden, collapsed]).length, 0);
assert.equal(ops.filter(op => op.startsWith('read:')).length, 0);
hiddenGroup.hidden = false;
collapsedGroup.classList.remove('collapsed');
bodyObserver().callback([
 { type: 'attributes', target: hiddenGroup, attributeName: 'hidden', oldValue: '' },
 { type: 'attributes', target: collapsedGroup, attributeName: 'class', oldValue: 'collapsible-body collapsed' },
]);
drainFrames();
assert.equal(enhanced([hidden, collapsed]).length, 2);
""")


def test_settings_sized_form_does_not_measure_its_81_folded_fields():
    run_scenario("""
const hiddenGroup = element('div', 'fields'); hiddenGroup.hidden = true; body.appendChild(hiddenGroup);
const selects = Array.from({ length: 20 }, (_, i) => control('select', 'source' + i));
const visible = Array.from({ length: 40 }, (_, i) => control('input', 'table' + i));
const folded = Array.from({ length: 81 }, (_, i) => control('input', 'field' + i, hiddenGroup));
initializeCustomSelects();
let reads = 0, frameCount = 0;
while (frames.size) {
  nextFrame(); assertReadPhaseBeforeWritePhase();
  reads += ops.filter(op => op.startsWith('read:')).length;
  assert.ok(++frameCount < 100);
}
assert.equal(enhanced([...selects, ...visible]).length, 60);
assert.equal(enhanced(folded).length, 0);
assert.equal(reads, 120, 'only 60 visible controls need one rect and style read');
assert.ok(frameCount > 1, 'the settings-sized form must yield between batches');
""")


def test_navigation_cancels_unstarted_settings_controls_and_return_requeues_them():
    run_scenario("""
page = 'settings';
const settings = element('section', 'page-settings'); settings.className = 'page'; body.appendChild(settings);
const controls = Array.from({ length: 35 }, (_, i) => control('input', 'setting' + i, settings));
initializeCustomSelects(); nextFrame();
const before = enhanced(controls).length;
assert.ok(before < controls.length);
cancelSettingsPageLoad();
// A module's deactivate may await while the old data-page remains visible.
drainFrames();
assert.equal(enhanced(controls).length, before, 'cancel immediately, before data-page changes');
page = 'users';
pageObserver().callback([]); drainFrames();
assert.equal(enhanced(controls).length, before);
page = 'settings';
pageObserver().callback([]); drainFrames();
assert.equal(enhanced(controls).length, controls.length);
""")


def test_cancel_before_first_frame_skips_settings_but_keeps_other_pending_controls():
    run_scenario("""
page = 'settings';
const settings = element('section', 'page-settings'); settings.className = 'page'; body.appendChild(settings);
const setting = control('input', 'setting', settings);
const global = control('input', 'global');
initializeCustomSelects();
cancelSettingsPageLoad();
drainFrames();
assert.equal(enhanced([setting]).length, 0);
assert.equal(enhanced([global]).length, 1);
""")


def test_removing_an_enhanced_control_cleans_its_detached_popup():
    run_scenario("""
const select = control('select', 'choice');
initializeCustomSelects(); drainFrames();
const state = customSelectStates.get(select);
openCustomSelect(select);
select.remove();
bodyObserver().callback([{ type: 'childList', target: state.shell, addedNodes: [], removedNodes: [select] }]);
drainFrames();
assert.equal(state.dropdown.isConnected, false);
assert.equal(customSelectStates.has(select), false);
ops.length = 0; click({ target: body });
assert.equal(ops.length, 0);
""")


def test_closed_controls_do_not_write_and_open_controls_close_normally():
    run_scenario("""
const select = control('select', 'choice');
const date = control('input', 'date'); date.type = 'date';
initializeCustomSelects(); drainFrames();
ops.length = 0;
click({ target: body });
closeCustomSelect(select); closeCustomDatePicker(date);
assert.equal(ops.length, 0, 'closed controls must not be rewritten on menu clicks');
openCustomSelect(select);
assert.equal(customSelectStates.get(select).dropdown.hidden, false);
click({ target: body });
assert.equal(customSelectStates.get(select).dropdown.hidden, true);
assert.equal(customSelectStates.get(select).trigger.attributes.get('aria-expanded'), 'false');
openCustomDatePicker(date);
assert.equal(customDateStates.get(date).dropdown.hidden, false);
click({ target: body });
assert.equal(customDateStates.get(date).dropdown.hidden, true);
ops.length = 0; click({ target: body });
assert.equal(ops.length, 0);
""")


def test_mutations_scan_added_controls_without_rescanning_unrelated_or_own_dom():
    run_scenario("""
const select = control('select', 'choice');
initializeCustomSelects(); drainFrames();
queries.length = 0; ops.length = 0;
bodyObserver().callback([{ type: 'childList', target: customSelectStates.get(select).dropdown,
  addedNodes: [element('button')], removedNodes: [] }]);
bodyObserver().callback([{ type: 'childList', target: body,
  addedNodes: [element('span', 'status')], removedNodes: [] }]);
drainFrames();
assert.equal(ops.length, 0);
assert.ok(!queries.some(([root]) => root === 'document'), 'unrelated updates must not rescan document');
const region = element('div', 'new-region'); body.appendChild(region);
const added = control('input', 'added', region);
bodyObserver().callback([{ type: 'childList', target: body, addedNodes: [region], removedNodes: [] }]);
drainFrames();
assert.equal(enhanced([added]).length, 1);
select.options.push({ textContent: 'New option', value: 'new' });
observers.find(o => o.target === select).callback([]);
assert.equal(customSelectStates.get(select).dropdown.children.length, 2);
""")


def test_inactive_legacy_page_and_hidden_module_enhance_only_when_activated():
    run_scenario("""
const users = element('section', 'page-users'); users.className = 'page'; body.appendChild(users);
const userSelect = control('select', 'user-role', users);
const module = element('section', 'module'); module.className = 'auto-check-module'; module.hidden = true; body.appendChild(module);
const moduleInput = control('input', 'module-search', module);
initializeCustomSelects(); drainFrames();
assert.equal(enhanced([userSelect, moduleInput]).length, 0);
assert.equal(ops.filter(op => op.startsWith('read:')).length, 0);
page = 'users'; pageObserver().callback([]); drainFrames();
assert.equal(enhanced([userSelect]).length, 1);
module.hidden = false;
bodyObserver().callback([{ type: 'attributes', target: module, attributeName: 'hidden', oldValue: '' }]);
drainFrames(); assert.equal(enhanced([moduleInput]).length, 1);
""")


def test_enhanced_select_and_date_keep_selection_and_change_events():
    run_scenario("""
const select = control('select', 'choice');
select.options.push({ textContent: 'Second', value: 'second' });
const date = control('input', 'date'); date.type = 'date';
initializeCustomSelects(); drainFrames();
const changes = [];
select.addEventListener('change', () => changes.push('select'));
date.addEventListener('change', () => changes.push('date'));
openCustomSelect(select);
customSelectStates.get(select).dropdown.children[1].listeners.get('click')();
assert.equal(select.selectedIndex, 1);
assert.equal(customSelectStates.get(select).trigger.textContent, 'Second');
assert.equal(customSelectStates.get(select).dropdown.hidden, true);
openCustomDatePicker(date);
const day = { dataset: { date: '2026-10-01' } };
customDateStates.get(date).dropdown.listeners.get('click')({ stopPropagation() {},
  target: { closest: selector => selector === '[data-date]' ? day : null } });
assert.equal(date.value, '2026-10-01');
assert.equal(customDateStates.get(date).dropdown.hidden, true);
assert.deepEqual(changes, ['select', 'date']);
""")


def test_first_modal_open_preserves_already_focused_input_and_selection():
    run_scenario("""
const modal = element('section', 'modal'); modal.hidden = true; body.appendChild(modal);
const input = control('input', 'name', modal);
initializeCustomSelects(); drainFrames();
modal.hidden = false;
input.focus(); input.setSelectionRange(2, 5, 'backward');
bodyObserver().callback([{ type: 'attributes', target: modal, attributeName: 'hidden', oldValue: '' }]);
drainFrames(true);
assert.equal(enhanced([input]).length, 1);
assert.equal(document.activeElement, input, 'moving an active control into its shell must not lose focus');
assert.deepEqual(input.focusOptions, { preventScroll: true });
assert.equal(input.selectionStart, 2); assert.equal(input.selectionEnd, 5);
assert.equal(input.selectionDirection, 'backward');
""")


def test_focus_restore_handles_controls_without_selection_and_never_steals_focus():
    run_scenario("""
const number = control('input', 'number'); number.type = 'number';
number.focus(); initializeCustomSelects(); drainFrames(true);
assert.equal(document.activeElement, number);
const select = control('select', 'choice'); select.focus();
bodyObserver().callback([{ type: 'childList', target: body, addedNodes: [select], removedNodes: [] }]);
drainFrames(true);
assert.equal(document.activeElement, customSelectStates.get(select).trigger, 'focused select must keep its visible keyboard entry');
assert.deepEqual(customSelectStates.get(select).trigger.focusOptions, { preventScroll: true });
const input = control('input', 'new'); const other = control('input', 'other');
input.focus(); input.addEventListener('blur', () => other.focus());
bodyObserver().callback([{ type: 'childList', target: body, addedNodes: [input, other], removedNodes: [] }]);
drainFrames(true);
assert.equal(document.activeElement, other, 'a blur handler choosing another focus target must win');
""")
