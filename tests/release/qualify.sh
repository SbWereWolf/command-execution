#!/usr/bin/env bash
# Build or publish one channel inside its own isolated network namespace.
set -euo pipefail

repo=$(git rev-parse --show-toplevel)
cd "$repo"
driver="$repo/.github/scripts/release-channel.sh"
helpers="$repo/tests/release"

if [[ ${1-} == --inside ]]; then
  shift
  channel=$1
  out=$2
  tag=$3
  artifact=$4
  candidate=$(bash "$driver" artifact "$channel" "$out/candidate")
  test "$candidate" = "$out/candidate/$artifact"
  if [[ $channel == npm ]]; then
    bash "$helpers/roundtrip.sh" npm "$candidate" "${tag#v}"
    bash "$helpers/npm-sdk.sh" "$CE_CHECK_ROOT/installed/node_modules/$RELEASE_PACKAGE" "${tag#v}" \
      "$out/npm-sdk" "$CE_SDK_FIXTURE" "$repo/npm/wheelhouse/packaging-26.3-py3-none-any.whl"
    "$CE_PYTHON" -I -B .github/scripts/npm-release.py registry --tag "$tag" --output-dir "$out/candidate" \
      --registry-url "$CE_NPM_REGISTRY" | tee "$out/registry-replay.log"
    test "$(cat "$out/registry-replay.log")" = already-published
    mkdir "$out/conflict"
    cp "$candidate" "$out/conflict/$artifact"
    printf 'conflicting candidate\n' >> "$out/conflict/$artifact"
    code=0
    "$CE_PYTHON" -I -B .github/scripts/npm-release.py registry --tag "$tag" --output-dir "$out/conflict" \
      --registry-url "$CE_NPM_REGISTRY" > "$out/conflict.log" 2>&1 || code=$?
    test "$code" -eq 1
    grep -F 'different bytes' "$out/conflict.log"
  else
    bash "$helpers/roundtrip.sh" pypi "$candidate" "${tag#v}" \
      "$CE_PYPI_BUILD_INPUTS/jsonpatch-1.48-py3-none-any.whl" \
      "$CE_PYPI_BUILD_INPUTS/jsonpointer-3.12-py3-none-any.whl" \
      "$CE_PYPI_BUILD_INPUTS/packaging-26.3-py3-none-any.whl"
  fi
  exit
fi

phase=$1
channel=$2
out=$3
tag=$4
artifact=$5
mkdir -- "$out"
export CE_PYTHON CE_SDK_FIXTURE CE_CAPTURE_RELEASE CE_REGISTRY_UNAVAILABLE
CE_PYTHON=$(command -v "${RELEASE_PYTHON:-python3}")
CE_SDK_FIXTURE="$repo/tests/fixtures/command-package/check_installed.py"
CE_CAPTURE_RELEASE="$helpers/capture-release.py"
CE_REGISTRY_UNAVAILABLE=
if [[ $phase == build || $RELEASE_REF_NAME == *-"$channel"-outage ]]; then
  CE_REGISTRY_UNAVAILABLE=$channel
fi

if [[ $channel == npm ]]; then
  export CE_NODE24_BIN_DIR CE_VERDACCIO NPM_CONFIG_CACHE
  CE_NODE24_BIN_DIR=${CE_NODE24_BIN_DIR:-$(dirname "$(command -v node)")}
  NPM_CONFIG_CACHE="$out/bootstrap-npm-cache"
  if [[ -z ${CE_VERDACCIO-} && $CE_REGISTRY_UNAVAILABLE != npm ]]; then
    npm install --prefix "$out/npm-tools" --registry https://registry.npmjs.org/ \
      --ignore-scripts --no-audit --no-fund verdaccio@7.1.2 > "$out/bootstrap-npm.log" 2>&1
    CE_VERDACCIO="$out/npm-tools/node_modules/.bin/verdaccio"
    cp "$out/npm-tools/package-lock.json" "$out/test-tools-lock.json"
  fi
  cp "$repo/npm/wheelhouse.lock.json" "$out/input-lock.json"
  cp -a "$repo/npm/wheelhouse" "$out/locked-inputs"
elif [[ $channel == pypi ]]; then
  export CE_DEVPI_INIT CE_DEVPI_SERVER CE_TWINE CE_PYPI_BUILD_INPUTS
  if [[ $phase == publish && -z ${CE_TWINE-} ]]; then
    "$CE_PYTHON" -m venv "$out/python-tools"
    "$out/python-tools/bin/python" -m pip --disable-pip-version-check --no-cache-dir install \
      --index-url https://pypi.org/simple devpi-server==6.21.0 twine==7.0.0 > "$out/bootstrap-python.log" 2>&1
    CE_DEVPI_INIT="$out/python-tools/bin/devpi-init"
    CE_DEVPI_SERVER="$out/python-tools/bin/devpi-server"
    CE_TWINE="$out/python-tools/bin/twine"
    "$out/python-tools/bin/python" -m pip freeze --all > "$out/test-tools-lock.txt"
  fi
  if [[ -z ${CE_PYPI_BUILD_INPUTS-} ]]; then
    CE_PYPI_BUILD_INPUTS="$out/locked-inputs"
    "$CE_PYTHON" -m pip --disable-pip-version-check --no-cache-dir download --index-url https://pypi.org/simple \
      --only-binary=:all: --no-deps --dest "$CE_PYPI_BUILD_INPUTS" setuptools==84.2.1 wheel==0.48.0 \
      packaging==26.3 jsonpatch==1.48 jsonpointer==3.12 > "$out/python-inputs.log" 2>&1
  fi
  (cd "$CE_PYPI_BUILD_INPUTS" && sha256sum ./*.whl) > "$out/python-inputs.sha256"
else
  exit 2
fi

if [[ $phase == build ]]; then
  zone="$out/isolation"
  code=0
  bash "$helpers/with-registry.sh" "$channel" "$zone" --     bash "$driver" prepare "$channel" "$out/build" > "$out/build.log" 2>&1 || code=$?
  cat "$out/build.log"
  test "$code" -eq 0
  cp -- "$out/build/$artifact" "$out/build/manifest.json" "$out/"
  cp -- "$zone/network.log" "$out/build-network.log"
  exit
fi

test "$phase" = publish
build=${6:?Select the downloaded distribution}
bash "$driver" artifact "$channel" "$build" >/dev/null
mkdir "$out/candidate"
cp -- "$build/$artifact" "$build/manifest.json" "$out/candidate/"
cp -- "$build/build.log" "$build/build-network.log" "$out/"
zone="$out/isolation"
code=0
bash "$helpers/with-registry.sh" "$channel" "$zone" -- \
  bash "$helpers/qualify.sh" --inside "$channel" "$out" "$tag" "$artifact" || code=$?
mkdir "$out/report"
for file in network.log health.json operation.log dist.json digest install.log pip-check.log sdk.log cli.jsonl validation.log; do
  if [[ -f $zone/$file ]]; then cp "$zone/$file" "$out/report/"; fi
done
if [[ -d $zone/download ]]; then cp -a "$zone/download" "$out/report/"; fi
if [[ -f $out/report/operation.log ]]; then cat "$out/report/operation.log"; fi
printf '%s\n' "$code" > "$out/report/exit"
exit "$code"
