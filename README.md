# command-execution

Run external commands from Python using explicit, reusable command declarations.
Prepare arguments, working directories and environment variables before starting
processes, decide which exit codes mean success, and inspect the actual output.

Use it for build steps, local automation or tools that store their commands in
JSON. The same library can read and edit those JSON configurations: select items
by ID, add them, update fields with JSON Patch, or remove them.

Requires **Python 3.11 or later**.

## Install

```sh
python -m pip install "command-execution==1.0.1"
```

## Quickstart

This example starts a real Python subprocess and prints its result:

```python
import sys
from pathlib import Path

from command_execution import execute_action
from command_execution.actions.interpreters import exit_result

action = {
    "commands": [{
        "argv": [sys.executable, "-c", "print('Hello from command-execution')"],
        "cwd": ".",
        "env": {},
        "interpreter": {"name": "exit", "options": {"accept": [0]}},
    }],
}
result = execute_action(
    action, {},
    base_dir=Path.cwd(),
    interpreters={"exit": exit_result},
)
print(result["status"])
print(result["commands"][0]["stdout"].decode(), end="")
```

Output:

```text
succeeded
Hello from command-execution
```

Each command declares its argument list, working directory, complete environment
and result interpreter. Commands run in order; execution stops at the first
failed launch or rejected result. `stdout` and `stderr` are preserved as bytes,
and `exit_code` contains the actual process return code.

## Learn more

The [usage guide](https://github.com/SbWereWolf/command-execution/blob/v1.0.1/docs/usage.md)
explains parameter substitution, planning without execution, result fields,
failure handling and a complete JSON configuration example.

| API | Purpose |
| --- | --- |
| `plan_action` | Expand and validate a command declaration without starting processes. |
| `execute_action` | Prepare and run commands, returning output and interpreted results. |
| `list_requirement_ids`, `read_requirements` | Read selected configuration items. |
| `add_requirement`, `update_requirement` | Add an item or edit it with JSON Patch. |
| `delete_requirement`, `clear_requirements` | Remove one item or empty the selected list. |

[Русская версия](https://github.com/SbWereWolf/command-execution/blob/v1.0.1/README.ru.md)
· [Руководство на русском](https://github.com/SbWereWolf/command-execution/blob/v1.0.1/docs/usage.ru.md)
