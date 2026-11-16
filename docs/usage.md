# Usage guide

[Quickstart](https://github.com/SbWereWolf/command-execution/blob/v1.0.1/README.md)
· [Русская версия](https://github.com/SbWereWolf/command-execution/blob/v1.0.1/docs/usage.ru.md)

Requires Python 3.11 or later. Install with
`python -m pip install "command-execution==1.0.1"`.

## Prepare and run commands

`plan_action(action, parameters, *, base_dir, interpreters)` validates and expands
the whole action without starting a process. `execute_action` accepts the same
arguments, prepares the whole action first, then runs its commands in order.

This complete example passes a parameter through the child process environment:

```python
import sys
from pathlib import Path

from command_execution import execute_action, plan_action
from command_execution.actions.interpreters import exit_result

action = {
    "commands": [{
        "argv": [
            sys.executable, "-c",
            "import os; print(os.environ['GREETING'])",
        ],
        "cwd": ".",
        "env": {"GREETING": "${greeting}"},
        "interpreter": {"name": "exit", "options": {"accept": [0]}},
    }],
}
parameters = {"greeting": "Hello, Ada!"}
interpreters = {"exit": exit_result}
plan = plan_action(
    action, parameters, base_dir=Path.cwd(), interpreters=interpreters,
)
assert plan["commands"][0]["env"] == {"GREETING": "Hello, Ada!"}
result = execute_action(
    action, parameters, base_dir=Path.cwd(), interpreters=interpreters,
)
print(result["status"])
print(result["commands"][0]["stdout"].decode(), end="")
```

Output:

```text
succeeded
Hello, Ada!
```

### Inputs

| Input | Meaning |
| --- | --- |
| `action` | An object with a `commands` list. An empty list succeeds without processes. |
| `parameters` | A mapping of string names to `str`, `int`, `float` or `bool` values. |
| `base_dir` | An explicit absolute `str` or `Path`; relative command directories resolve against it. |
| `interpreters` | A mapping of names to ready objects exposing `interpret(result, options)`. |

Each command has all four fields:

| Field | Meaning |
| --- | --- |
| `argv` | Nonempty list of strings: executable followed by its arguments. |
| `cwd` | Working directory string, absolute or relative to `base_dir`. |
| `env` | Complete string-to-string process environment. Host variables are not added automatically. |
| `interpreter` | Object with `name` and an `options` object; the name resolves in `interpreters`. |

Parameter expansion uses Python `string.Template` once in every argument, `cwd`
and environment value: `$name` or `${name}` inserts a parameter, `$$` represents
a literal dollar sign. Interpreter options are passed as data without expansion.
Use an absolute executable such as `sys.executable` when the declared environment
provides no `PATH`.

Processes use argument lists with `shell=False`. Shell syntax such as pipes and
redirection is not evaluated. Standard input is closed. The API waits for each
process and captures its full output; it provides no timeout parameter.

### Results and failures

The plan is `{"commands": [...]}` with expanded arguments/environment and resolved
working directories. Planning does not check whether future executables or
directories already exist.

Execution returns an object with:

| Field | Meaning |
| --- | --- |
| `status` | `"succeeded"` or `"failed"`. |
| `commands` | Records for commands actually attempted, in order. |
| `error` | `None` on success, otherwise a diagnostic string. |

Each command record contains `invocation` (`argv`, `cwd`, `env`), `interpreter`,
`exit_code`, `stdout`, `stderr`, `interpretation` and `error`. Output streams are
**bytes**; decode them using the child program's encoding. A command that cannot
start has `exit_code=None`, empty byte streams and an error diagnostic.

`exit_result` accepts exactly the codes listed in `options["accept"]`. With
`[0]`, a nonzero code makes the action fail and later commands are not attempted.
A custom interpreter may accept another code or inspect output. Its
`interpret(result, options)` method returns an object with `success` (boolean),
`value` (any Python value) and `error` (`None` on success, a nonempty string on
failure). Exceptions or invalid interpreter answers become command errors.
Earlier external effects are not rolled back.

Invalid declarations, missing template parameters, a relative `base_dir` or an
unknown interpreter raise `ValueError` during preparation, before any command is
started. Process launch failures are returned in the failed execution result.

## Read and edit JSON configurations

A main JSON document maps operation names to JSON file paths in `operations`.
Relative paths resolve against the main file's directory. The selected document
contains a `requirements` list of objects with unique nonempty string `id`s.
Operation `run` uses an `applications` list instead.

The following complete example creates temporary files, reads and updates one
item, and removes items. Reading or editing stored declarations does not execute
commands.

```python
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from command_execution import (
    add_requirement, clear_requirements, delete_requirement,
    list_requirement_ids, read_requirements, update_requirement,
)

with TemporaryDirectory() as directory:
    root = Path(directory)
    main = root / "main.json"
    items = root / "items.json"
    main.write_text(json.dumps({"operations": {"infra": "items.json"}}), encoding="utf-8")
    items.write_text(json.dumps({"owner": "demo", "requirements": []}), encoding="utf-8")

    add_requirement(main, "infra", {"id": "greet", "label": "Hello"})
    print(json.dumps(list_requirement_ids(main, "infra")))
    print(read_requirements(main, "infra", ["greet"])[0]["label"])
    update_requirement(main, "infra", "greet", [
        {"op": "replace", "path": "/label", "value": "Updated"},
    ])
    print(read_requirements(main, "infra", "all")[0]["label"])
    delete_requirement(main, "infra", "greet")
    add_requirement(main, "infra", {"id": "temporary"})
    clear_requirements(main, "infra")
    print(json.dumps(list_requirement_ids(main, "infra")))
    assert json.loads(items.read_text(encoding="utf-8"))["owner"] == "demo"
```

Output:

```text
["greet"]
Hello
Updated
[]
```

### Configuration API

All functions take `config_path` and `operation` first.

| Function | Remaining arguments | Return value |
| --- | --- | --- |
| `list_requirement_ids` | None | IDs in document order. |
| `read_requirements` | `selection` | Full copied objects in selected order; `"all"` uses document order. |
| `add_requirement` | Complete `requirement` object | `None`. |
| `update_requirement` | `identifier`, `changes` | `None`. |
| `delete_requirement` | `identifier` | `None`. |
| `clear_requirements` | None | `None`. |

`selection` is a list of unique string IDs or the string `"all"`; `[]` selects
nothing. Missing selected IDs, duplicate IDs or selections, unknown operations,
invalid JSON and unreadable files raise `ValueError`.

`changes` is a list of JSON Patch operations: `add`, `replace` and `remove`, using
JSON Pointer paths. `copy`, `move` and `test` are not supported. Each write
preserves other items and document metadata and replaces the selected JSON file
through a temporary file in the same directory. Writes require an existing,
writable file and directory; they do not create missing configuration documents.
Use the actual returned/error state to handle failed writes.
