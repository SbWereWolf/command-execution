# Maintaining command-execution

<a id="installation-and-versions"></a>
## Installation and versions

Use Python 3.11+ with pip. Choose an available 2.x release from your index,
a complete offline wheelhouse, or the selected source checkout.
From that checkout, install into your prepared environment:

```bash
python -m pip install .
```

The wheelhouse must also supply the declared jsonpatch/jsonpointer dependencies.
Application imports use their own selected installation, not sibling checkouts.
Inspect an installed copy:

```python
import importlib.metadata
import command_execution
print(importlib.metadata.version("command-execution"))
print(command_execution.__file__)
```

The [2.x API](usage.md) uses the documented classes.
Application-specific plan_action/execute_action/plan_chain/execute_chain and
configuration-file facades are imported from `environment_maintenance`, not
the CE2 namespace. A breaking API change needs a major version; compatible
additions a minor; compatible fixes a patch. Never overwrite an occupied
distribution/version with different bytes.

Record selected version, origin and wheel hash. Local builds/tags/tests do not
prove public availability. Keep each bugfix build immutable; update consumer
dependencies once at final rollout, then verify each real installation.

<a id="unix-commands"></a>
## Caller-owned Unix commands

`ProcessWorker` launches supplied argv with shell=False and captures results.
Explicitly supply `["bash", "-c", "..."]` or a specialized Bash script to use
shell syntax. Quote inputs in the caller script; do not concatenate untrusted
data into a shell command.

Timeout, signals, cwd, environment, redirects and file replacement belong to the
supplied commands/scripts. An exit code is only an observed code until a caller
protocol establishes its cause. No implicit retry, rollback or exactly-once
effect is promised.

When needed, consumer scripts implement parent creation, existing-mode
preservation, exclusive creation and atomic publication. Their checks inspect
actual hashes/modes/failures; CE makes no separate storage guarantee.
WR/EM own their packaged Bash resources; CE owns pure JSON transformations.

<a id="module-boundaries"></a>
## Module responsibilities

| Module | Responsibility |
|---|---|
| json_codec, json_paths | Pure JSON profiles, edits and merge |
| collections | Ordered detached configuration lists |
| parameters | Lookup, rendering, deferred resolution |
| command_model | Command/chunk/outcome values |
| configuration | Planning and named output selectors |
| results | Storage and dispatch snapshot |
| error_policy | Stop/continue decision |
| delivery | Immediate/replayed output and serialized JSONL |
| lists, execution | Dispatch synchronization and raw process coordination |

Interpretation normalization does not own scheduling/storage/delivery.
Consumer schemas, deployment policy, recovery sessions and filesystem rules
stay outside these generic responsibilities.

<a id="package-verification"></a>
## Verification and delivery

Run meaningful affected checks/examples through the selected installed package,
with exact expected values/bytes and real effects. Package tests must work
outside Git; source/history preservation is a separate integration check.

The English root README supplies package description. Changed source/docs or
metadata need a correctly identified final artifact, never a rebuild over an
occupied version. Verify package contents, hashes and installed bytes. Working
configs/environments/credentials/Task evidence stay outside distributions.

Primary user links use stable default-branch paths and section anchors, without
commit IDs, release tags or line numbers. Retain a pointer after a public path
move. Check new paths on the actual delivered branch before claiming live
package-page links; publishing and adoption need their own observations.
