#!/usr/bin/env bash
# Install CE's supported SDK from local npm-delivered wheels alone.
set -euo pipefail
package_dir=$(realpath -- "${1:?Select installed npm package directory}")
version=${2:?Select CE version}
work=${3:?Select new scratch directory}
fixture=${4:?Select CE SDK smoke fixture}
oracle_wheel=$(realpath -- "${5:?Select checked packaging wheel for the SDK test oracle}")
python=${CE_PYTHON:?Select clean-install Python}

(cd "$package_dir/vendor" && sha256sum --strict -c SHA256SUMS)
mkdir -- "$work"
"$python" -m venv "$work/venv"
export PIP_CONFIG_FILE=/dev/null
unset PIP_INDEX_URL PIP_EXTRA_INDEX_URL PIP_FIND_LINKS
pip=("$work/venv/bin/python" -m pip --disable-pip-version-check --no-cache-dir)
"${pip[@]}" install --no-index --find-links "$package_dir/vendor" "command-execution==$version" > "$work/consumer-install.log" 2>&1
"${pip[@]}" check
# The SDK oracle uses packaging to inspect metadata. Install it after consumer resolution.
"${pip[@]}" install --no-index --no-deps "$oracle_wheel" > "$work/oracle-install.log" 2>&1
mkdir "$work/fixture"
"$work/venv/bin/python" -I -B "$fixture" "v$version" "$work/fixture"
