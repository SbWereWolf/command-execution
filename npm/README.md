# command-execution

The command-execution CLI reads a JSON command chain and writes JSON Lines.
This npm distribution includes the Python implementation and its dependencies.
It requires Node.js 22.0.0+ and a locally installed Python 3.12+.

```sh
npm install -g --engine-strict command-execution
command-execution --help
```

On Windows the launcher looks for Python using `py -3`, then `python` and
`python3`. Set `COMMAND_EXECUTION_PYTHON` to the full path to a specific
interpreter if needed.

```sh
printf '%s\n' '{"commands":[{"argv":["python3","-c","print(42)"],"sync-mode":["std-out"]}]}' | command-execution run
```

The command in `argv` must be available on your platform. See the
[CLI and JSON configuration guide](https://github.com/SbWereWolf/command-execution/blob/master/docs/usage.md).

## Python SDK from an npm installation

The package also supplies the CE wheel and its Python runtime wheels in
`vendor/`. A consumer can resolve CE with npm, verify the wheel files against
`vendor/SHA256SUMS`, and install them into its selected Python environment
without a Python index:

```bash
python -m pip install --no-index --find-links node_modules/command-execution/vendor command-execution==2.0.10
```

Use the exact CE version selected by the consumer's npm lock. The
`vendor/runtime-inputs.json` file identifies the origin and SHA-256 of
each runtime dependency. When using PyPI, the normal pip dependency
resolution applies.
