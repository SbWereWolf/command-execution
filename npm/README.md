# command-execution

The command-execution CLI reads a JSON command chain and writes JSON Lines.
This npm distribution includes the Python implementation and its dependencies.
It requires Node.js 22.14+ and a locally installed Python 3.12+.

```sh
npm install -g command-execution
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
