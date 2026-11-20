# command-execution

<a id="purpose"></a>
Run ordered commands from JSON, retain their results, and choose when to forward
stdout and stderr. The Python API also edits ordered configuration lists and
nested JSON values, renders typed parameters, and interprets command results.

Each command chooses sync/async execution and stop/continue on failure.
Your commands or Bash scripts own filesystem, environment and signal policy.
Requires Python 3.12+. Command-line examples use Ubuntu.

## Install

From the selected source checkout, use your prepared Python environment:

```bash
python -m pip install .
```

For a published release, select an available 2.x version from your package index.
See [installation and version selection](https://github.com/SbWereWolf/command-execution/blob/master/docs/maintenance.md#installation-and-versions)
for offline packages and verification.

<a id="quickstart"></a>
## Quickstart

With installed `command-execution` on PATH:

```bash
command-execution run <<'JSON'
{"commands":[{"id":"hello","argv":["printf","Hello from CE\\n"],
"execution":"sync","on_error":"stop","sync-mode":["std-out"],"batch-mode":[]}]}
JSON
```

stdout contains JSON Lines: an `output` event tagged `stream: "out"` and
`delivery: "immediate"`, followed by a terminal `result` with
`result.status: "succeeded"`. Decode output `data` from base64 to get
`Hello from CE\n`. Raw child bytes do not corrupt the JSON framing.

The same task without forwarding output:

```python
from command_execution import CommandPlanner, ChainCoordinator

plan, issues = CommandPlanner().compile({
    "commands": [{"id": "hello", "argv": ["printf", "Hello from CE\n"]}]
})
assert not issues
result = ChainCoordinator(plan).run(None)
assert result.status == "succeeded"
assert result.commands[0].raw.stdout == b"Hello from CE\n"
print(result.commands[0].raw.stdout.decode(), end="")
```

Default stream selections are empty; raw results are still retained.

## Documentation

- [CLI, JSON configuration and Python API](https://github.com/SbWereWolf/command-execution/blob/master/docs/usage.md)
- [Order and failure policy](https://github.com/SbWereWolf/command-execution/blob/master/docs/usage.md#execution-policy)
- [Typed and deferred parameters](https://github.com/SbWereWolf/command-execution/blob/master/docs/usage.md#parameters)
- [Ordered collections and nested edits](https://github.com/SbWereWolf/command-execution/blob/master/docs/usage.md#json-and-collections)
- [Output, storage and interpretation](https://github.com/SbWereWolf/command-execution/blob/master/docs/usage.md#results-and-output)
- [Maintenance and caller-owned Unix commands](https://github.com/SbWereWolf/command-execution/blob/master/docs/maintenance.md)
