import ast
from pathlib import Path


SUPPORT = Path(__file__).with_name('emergency_sessions_support.py')


def test_support_has_fixed_groups_head_and_safe_output():
    tree = ast.parse(SUPPORT.read_text(encoding='utf-8'))
    values = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {'HEAD', 'GROUPS'}
    }
    assert values['HEAD'] == '0006_credit_accounting_persistence'
    assert len(values['GROUPS']) == 8
    text = SUPPORT.read_text(encoding='utf-8')
    assert 'AUTH_LOGIN_ENABLED' in text
    assert 'provider raw response' not in text.lower()
    assert 'print(json.dumps(result))' in text
