#!/usr/bin/env node
const { spawnSync } = require('node:child_process');
const { join } = require('node:path');

const packageRoot = join(__dirname, '..');
const pythonOverride = process.env.COMMAND_EXECUTION_PYTHON;
const candidates = pythonOverride ? [[pythonOverride]] : process.platform === 'win32'
  ? [['py', '-3'], ['python'], ['python3']]
  : [['python3'], ['python']];

const python = candidates.find(([executable, ...options]) => {
  const probe = spawnSync(executable, [...options, '-I', '-c',
    'import sys; sys.exit(sys.version_info < (3, 12))'], { stdio: 'ignore' });
  return probe.status === 0;
});
if (!python) {
  console.error('command-execution requires Python 3.12+. Set COMMAND_EXECUTION_PYTHON to its executable.');
  process.exitCode = 1;
} else {
  const [executable, ...options] = python;
  const entry = [
    'from pathlib import Path',
    'import sys',
    'root = Path(sys.argv.pop(1))',
    'sys.path[:0] = [str(root / "src"), *map(str, sorted((root / "vendor").glob("*.whl")))]',
    'from command_execution.cli import main',
    'raise SystemExit(main())',
  ].join('\n');
  const result = spawnSync(executable,
    [...options, '-I', '-B', '-c', entry, packageRoot, ...process.argv.slice(2)],
    { stdio: 'inherit' });
  if (result.error) console.error(result.error.message);
  process.exitCode = result.status ?? 1;
}
