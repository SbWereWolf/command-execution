"""Check the installed distribution and the 2.x API against a real child."""
import importlib.abc
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import sysconfig

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


class NoEnvironmentDependency(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'environment_maintenance' or fullname.startswith('environment_maintenance.'):
            raise AssertionError('Independent command library imports its consumer')


release_tag, workspace = sys.argv[1:]
fixture_dir = Path(__file__).resolve().parent
os.chdir(workspace)

distribution = importlib.metadata.distribution('command-execution')
assert release_tag == 'v' + distribution.version
declared = [Requirement(value) for value in (distribution.requires or [])]
assert not any(canonicalize_name(value.name) == 'environment-maintenance'
               for value in declared)
for name, expected_specifier in {'jsonpatch': '>=1.36', 'jsonpointer': '>=3.4'}.items():
    matching = [value for value in declared if canonicalize_name(value.name) == name]
    assert len(matching) == 1, 'Required runtime dependency missing or ambiguous: ' + name
    assert str(matching[0].specifier) == expected_specifier
    assert matching[0].marker is None
    assert not matching[0].extras

sys.meta_path.insert(0, NoEnvironmentDependency())
import command_execution as api

assert Path(api.__file__).is_relative_to(sysconfig.get_path('purelib'))
assert api.__version__ == distribution.version

launches = []


def observe_launch(event, arguments):
    if event == 'subprocess.Popen':
        launches.append(arguments[1])


sys.addaudithook(observe_launch)
document = json.loads((fixture_dir / 'action.json').read_text())
child = str(fixture_dir / 'child.py')
plan, issues = api.CommandPlanner().compile(
    document, {'python': sys.executable, 'probe': child}, profile='wr-template'
)
assert not issues
assert not launches
result = api.ChainCoordinator(
    plan,
    interpreter=lambda raw, spec: {
        'success': raw.exit_code == 7, 'value': raw.exit_code, 'error': None,
    },
).run(None)
assert launches == [[sys.executable, '-B', child]]
assert result.status == 'succeeded'
row = result.commands[0]
assert row.raw.exit_code == 7
assert row.raw.stdout == b'package-out\x00\xff'
assert row.raw.stderr == b'package-err\xfe'
assert row.interpretation == {'success': True, 'value': 7, 'error': None}

document = {'requirements': [{'id': 'first'}], 'metadata': 'keep'}
collection = api.DocumentCollection(document, 'requirements')
assert collection.ids() == ['first']
updated = collection.add({'id': 'second'}).patch_child(
    'second', [{'op': 'add', 'path': '/value', 'value': 9}]
)
assert updated.document() == {
    'requirements': [{'id': 'first'}, {'id': 'second', 'value': 9}],
    'metadata': 'keep',
}
assert collection.document() == document
print('independent-package-contract-ok')
