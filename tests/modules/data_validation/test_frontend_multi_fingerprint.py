"""Exercise the production fingerprint body: nested edits must not disappear."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js unavailable")
def test_multi_fingerprint_keeps_nested_semantics():
    source = (Path(__file__).resolve().parents[3] / "src/auto_check/modules/data_validation/web/pages/workbench.js").read_text(encoding="utf-8")
    function = "function canonicalOptionKey" + source.split("function canonicalOptionKey", 1)[1].split("function optionsFingerprint", 1)[0]
    script = function + """
const original = {
  expression: {left: 'amount', op: 'eq', right_type: 'value', right: 0},
  filters: [{field: 'status', op: 'eq', value: '1'}],
  join: {on: [{left: 'code', right: 'foreign_code'}]}
};
const key = canonicalOptionKey(original);
for (const mutate of [
  x => x.expression.left = 'other_amount',
  x => x.expression.right = 1,
  x => x.expression.op = 'neq',
  x => x.filters[0].value = '2',
  x => x.join.on[0].right = 'wrong_key'
]) {
  const changed = structuredClone(original);
  mutate(changed);
  if (canonicalOptionKey(changed) === key) throw Error('Nested semantic edit was discarded');
}
const reordered = {join: original.join, filters: original.filters,
  expression: {right: 0, right_type: 'value', op: 'eq', left: 'amount'}};
if (canonicalOptionKey(reordered) !== key) throw Error('Property order changed semantic fingerprint');
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
