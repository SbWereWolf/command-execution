# Using command-execution

<a id="command-line"></a>
## Command line

`command-execution run` reads a JSON document from stdin and writes JSON Lines
to stdout. `command-execution validate` checks without starting commands.
Documents contain a `commands` array and may contain `input` and `parameters`.
The CLI uses the `resolved` profile: argv is already prepared. It does not
expand shell variables or invoke a shell implicitly.

```bash
command-execution validate <<'JSON'
{"commands":[{"id":"inspect","argv":["printf","ready"],"batch-mode":[],"sync-mode":[]}]}
JSON
```

Expect exit 0 and one terminal `validation_result` with `valid: true`,
`status: "valid"`, `issue_count: 0`. No child starts.
`validate` exits 2 for issues, emitting all collected issues before its terminal
result. `run` exits 0 for success, 1 for a failed executed chain, and 2 for an
invalid document that prevents planning. Argparse usage diagnostics use stderr.

<a id="execution-policy"></a>
## Execution policy

| Field | Meaning | Default |
|---|---|---|
| `id` | Unique nonempty string | `command-N`, zero-based source index |
| `argv` | Nonempty array of strings passed directly | Required |
| `order` | Integer launch priority, lower first | Source index |
| `execution` | `sync` waits; `async` allows further dispatch | `sync` |
| `on_error` | `stop` or `continue` on interpretation failure | `stop` |
| `sync-mode` | Streams forwarded during processing | `[]` |
| `batch-mode` | Streams replayed after launched work finishes | `[]` |

Equal priorities keep source order. Result slots retain source indices.
Additional fields remain in `CommandSpec.properties`; the consumer interprets them.

An observed failed stop-command prevents further launches. It does not cancel
already launched work or undo effects. A late async failure cannot retroactively
prevent an earlier launch. Continue retains failure and permits later commands.
Transport, store, delivery and observer infrastructure failures stop further
dispatch independently of `on_error`. Recovery, deployment acceptance and retry
belong to the caller.

```python
from command_execution import CommandPlanner, ChainCoordinator
plan, issues = CommandPlanner().compile({"commands": [
    {"id": "bad", "argv": ["bash", "-c", "printf problem >&2; exit 7"],
     "on_error": "continue"},
    {"id": "after", "argv": ["printf", "still ran"]}
]})
assert not issues
result = ChainCoordinator(plan).run(None)
assert result.status == "failed"
assert [row.raw.returncode for row in result.commands] == [7, 0]
assert result.commands[1].raw.stdout == b"still ran"
print("failed result retained; successor completed")
```

`dispatch(input)` returns a `ChainRun`. Its `dispatch_snapshot()` freezes
aggregate data/status/error at the end of dispatch; command rows can later become
visible as workers finish. `wait()` returns the final aggregate after workers
and selected batch replay. `run(input)` is dispatch-and-wait.

<a id="results-and-output"></a>
## Results and output

`sync-mode` and `batch-mode` independently accept arrays containing `std-err`
and `std-out`. Empty means no forwarding. Selecting both phases replays the
same captured chunks; it does not execute the command twice. Execution mode
and output delivery are separate.

| Selection | Internal named flag |
|---|---|
| `[]` | `OutputStreams.NONE` |
| `["std-err"]` | `OutputStreams.STD_ERR` (bit 1) |
| `["std-out"]` | `OutputStreams.STD_OUT` (bit 2) |
| Both | `OutputStreams.ALL` |

Output events contain `run_id`, `command_id`, `message_id`, `sequence`,
`stream` (`out`/`err`), `delivery` (`immediate`/`batch`),
`encoding: "base64"` and `data`. Decode base64 to recover arbitrary bytes.
Replayed events retain the captured message identity and sequence. Chunks need
not correspond to lines; no cross-stream ordering of independent child writes
is promised. One final `result` follows selected batch output.

SDK `ChainResult` has `status`, `commands`, final `data`, `error`,
`infrastructure_errors`, `observer_errors` and `delivery_errors`.
Rows retain input, source index, state, raw outcome and interpretation, even
when both selectors are empty. Unlaunched stopped rows are `not_attempted`.

`MemoryResultStore` owns outcome/chunk storage; `ErrorPolicy` owns stop/continue;
`OutputDelivery` selects events; `JSONLWriter` serializes through one writer.
None of these selects application deployment policy.

A complete binary roundtrip through the installed CLI:

```python
import base64
import json
import subprocess
import sys

document = {"commands": [{
    "id": "binary",
    "argv": [sys.executable, "-I", "-B", "-c",
             "import os;os.write(1,bytes([0,255]));os.write(2,bytes([254]))"],
    "sync-mode": ["std-out", "std-err"],
    "batch-mode": ["std-out", "std-err"]
}]}
completed = subprocess.run([sys.executable, "-I", "-B", "-m",
    "command_execution.cli", "run"], input=json.dumps(document).encode(),
    capture_output=True, check=False)
assert completed.returncode == 0 and completed.stderr == b""
events = [json.loads(line) for line in completed.stdout.splitlines()]
assert events[-1]["event"] == "result"
for phase in ("immediate", "batch"):
    selected = [e for e in events if e["event"] == "output" and e["delivery"] == phase]
    for stream, expected in [("out", bytes([0, 255])), ("err", bytes([254]))]:
        assert b"".join(base64.b64decode(e["data"]) for e in selected
                        if e["stream"] == stream) == expected
immediate = [e["message_id"] for e in events if e.get("delivery") == "immediate"]
batch = [e["message_id"] for e in events if e.get("delivery") == "batch"]
assert immediate == batch
print("exact binary output in both delivery phases")
```

<a id="sdk"></a>
## Interpretation and data flow

Pass `interpreter=callback` to `ChainCoordinator`; it receives `(raw, spec)`.
`RawOutcome` contains `argv`, `returncode`, byte `stdout`/`stderr`,
optional `launch_error` and `transport_errors`. Return a dict containing
boolean `success`, `value` and `error`. Exceptions/malformed replies become
contextual interpretation failures governed by the command's `on_error`, while
raw bytes and exit facts remain. The default accepts exit 0 and rejects launch
failure.

SDK `value` may be an arbitrary Python object; it is not implicitly next input.
CLI/event serialization still requires a representable value.
For a sync command, explicit `next_input` advances data only after validation
by the JSON stdin encoder. Missing means preserve input; null/false/zero/empty
are explicit values. Valid input may advance even on failed/continue.
Invalid input records a contextual error and keeps the last valid data.
Async results never advance synchronous chain data.

```python
import json
import sys
from command_execution import CommandPlanner, ChainCoordinator

def increment(raw, spec):
    received = json.loads(raw.stdout)
    return {"success": True, "value": "separate result", "error": None,
            "next_input": {"n": received["n"] + 1}}

echo = [sys.executable, "-I", "-B", "-c",
        "import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())"]
plan, issues = CommandPlanner().compile({"commands": [
    {"id": "first", "argv": echo}, {"id": "second", "argv": echo}
]})
assert not issues
result = ChainCoordinator(plan, interpreter=increment).run({"n": 3})
assert result.data == {"n": 5}
assert [json.loads(row.raw.stdout) for row in result.commands] == [{"n": 3}, {"n": 4}]
print(json.dumps(result.data, sort_keys=True))
```

Expect `{"n": 5}`. Commands/interpreters may have arbitrary effects.
An `on_result(row)` observer runs after row storage; its exception is an observer
failure, not rollback. Exit codes alone do not establish timeout/signal causes.

A causal async example: both commands receive the initial snapshot; only the
sync result advances data. The caller's events release its own interpreter.

```python
import json
import sys
from threading import Event
from command_execution import CommandPlanner, ChainCoordinator

started, release = Event(), Event()
echo = [sys.executable, "-I", "-B", "-c",
        "import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())"]
def interpret(raw, spec):
    if spec.id == "background":
        started.set()
        assert release.wait(5)
        following = {"n": 99}
    else:
        assert started.wait(5)
        following = {"n": 1}
        release.set()
    return {"success": True, "value": json.loads(raw.stdout), "error": None,
            "next_input": following}

plan, issues = CommandPlanner().compile({"commands": [
    {"id": "background", "argv": echo, "execution": "async", "on_error": "continue"},
    {"id": "sync", "argv": echo}
]})
assert not issues
try:
    result = ChainCoordinator(plan, interpreter=interpret).run({"n": 0})
finally:
    release.set()
assert result.status == "succeeded" and result.data == {"n": 1}
assert [row.interpretation["value"] for row in result.commands] == [{"n": 0}, {"n": 0}]
print("async snapshot retained; only sync advanced data")
```

<a id="json-and-collections"></a>
## JSON and ordered collections

These APIs transform values without file IO.

```python
from command_execution import DocumentCollection, JSONPathEditor, JSONMerger
original = {"commands": [{"id": "a"}, {"id": "b"}], "metadata": {"keep": True}}
collection = DocumentCollection(original, "commands")
edited = collection.patch_child("a", [
    {"op": "add", "path": "/consumer", "value": {"queue": ["one", "two"]}}
]).move("b", 0)
assert collection.ids() == ["a", "b"]
assert edited.ids() == ["b", "a"]
assert edited.select(["a"])[0]["consumer"]["queue"] == ["one", "two"]
assert edited.document()["metadata"] == {"keep": True}
assert "consumer" not in original["commands"][0]
assert edited.reorder(["a", "b"]).ids() == ["a", "b"]
editor = JSONPathEditor()
assert editor.set({}, "/service/port", 8080) == {"service": {"port": 8080}}
assert editor.patch({"a": [1]}, [{"op": "add", "path": "/a/-", "value": 2}]) == {"a": [1, 2]}
assert JSONMerger().merge({"a": {"x": 1}, "b": [1]}, {"a": {"y": 2}, "b": []}) == {
    "a": {"x": 1, "y": 2}, "b": []}
print("ordered edits preserve input and consumer fields")
```

`DocumentCollection(document, array_name, id_field="id")` requires unique
nonempty IDs. Its select/add/replace/delete/clear/move/reorder/patch_child
methods return detached data or a new collection. Move uses a zero-based index;
reorder requires the exact permutation; unknown selections fail.
`JSONPathEditor.get/set/remove` support JSON Pointer and dotted profiles.
Set may create object parents; Pointer uses `~1` for slash and `~0` for tilde.
Patch supports add/replace/remove. `JSONMerger` overlays objects recursively and
replaces arrays/scalars. Extra application fields keep their types and meaning.

`JSONCodec("ce-object-v1")` reads objects and rejects duplicate keys.
`JSONCodec("wr-json-v1")` supplies WR-compatible JSON numbers and canonical
UTF-16 key ordering. Select the profile matching the caller's contract.

<a id="parameters"></a>
## Parameters and deferred values

```python
from command_execution import ParameterLookup, TemplateRenderer, DeferredResolver
values = {"service": {"ports": [8080, 9090]}, "items": [1, 2]}
assert ParameterLookup().resolve(values, "service.ports.1") == 9090
renderer = TemplateRenderer()
assert renderer.render({"ports": "${service.ports}"}, values) == {"ports": [8080, 9090]}
late = renderer.render("${outputs.file}", {}, "wr-flow", deferred=("outputs.file",))
assert late == "${outputs.file}"
assert DeferredResolver().resolve_at_consumption(late, {"outputs": {"file": "ready"}}) == "ready"
assert renderer.render("${items}", values, "wr-workflow") == "1,2"
print("typed value and consumption-time resolution confirmed")
```

Full placeholders retain types in WR template/flow profiles; embedded placeholders
use profile-specific strings. Own-property lookup supports array indices and
`length`. Missing values fail unless explicitly deferred or collected.
Profiles: resolved (copy), python-template (Python string.Template), wr-template,
wr-flow (including longest matching dotted keys), wr-workflow (exact keys/string
rendering). Resolve at consumption time; CE does not invent workflow stages.

<a id="validation"></a>
## Validation and tolerant selectors

Unknown/non-string/duplicate selector entries are errors but are ignored while
valid selections remain. Normal execution emits no diagnostics for them.
Validation/test mode reports all errors with command/field/element locations.

```bash
command-execution validate <<'JSON'
{"commands":[{"id":"inspect","argv":["printf","must not run"],
"batch-mode":["std-out","bad","std-out"],"sync-mode":[]}]}
JSON
```

Expect exit 2, two `configuration_issue` events and one final
`validation_result` with `valid: false`, `issue_count: 2`. No child starts.
With `run`, these selector errors alone do not stop execution; valid std-out
batch selection remains. Structural errors such as invalid argv prevent planning.
