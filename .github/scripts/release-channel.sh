#!/usr/bin/env bash
set -euo pipefail

phase=${1:?Select release phase}
channel=${2:?Select release channel}
out=${3:?Select output directory}
mode=${RELEASE_MODE:?Select release mode}
ref=${RELEASE_REF_NAME:?Select release ref}
sha=${RELEASE_SHA:?Select source commit}
python=${RELEASE_PYTHON:-python3}
package=${RELEASE_PACKAGE:?Select package name}
repo=$(git rev-parse --show-toplevel)
cd "$repo"
test "$(git rev-parse HEAD)" = "$sha"
case "$channel" in npm|pypi) ;; *) exit 2 ;; esac
case "$mode" in
  production) [[ $ref =~ ^v([0-9]+\.[0-9]+\.[0-9]+)$ ]] ;;
  qualification) [[ $ref =~ ^qualify-ce-v([0-9]+\.[0-9]+\.[0-9]+)(-r[1-9][0-9]*)?-(npm|pypi)-outage$ ]] ;;
  *) exit 2 ;;
esac
version=${BASH_REMATCH[1]}
tag="v$version"
actual=$("$python" -I -B .github/scripts/release.py validate --tag "$tag")
test "$(jq -r .name <<<"$actual")" = "$package"
test "$(jq -r .version <<<"$actual")" = "$version"
export SOURCE_DATE_EPOCH
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)

if [[ $channel == npm ]]; then
  artifact="$package-$version.tgz"
else
  artifact="${package//-/_}-$version-py3-none-any.whl"
fi

seal_artifact() {
  local hash
  hash=$(sha256sum "$out/$artifact" | cut -d' ' -f1)
  jq -n --arg sha "$sha" --arg ref "$ref" --arg channel "$channel" --arg name "$package" \
    --arg version "$version" --arg artifact "$artifact" --arg digest "$hash" \
    '{source_sha:$sha, ref:$ref, channel:$channel, package:$name, version:$version, artifact:$artifact, sha256:$digest}' \
    > "$out/manifest.json"
}

verify_artifact() {
  local hash
  hash=$(sha256sum "$out/$artifact" | cut -d' ' -f1)
  jq -e --arg sha "$sha" --arg ref "$ref" --arg channel "$channel" --arg name "$package" \
    --arg version "$version" --arg artifact "$artifact" --arg digest "$hash" \
    '.=={source_sha:$sha,ref:$ref,channel:$channel,package:$name,version:$version,artifact:$artifact,sha256:$digest}' \
    "$out/manifest.json" >/dev/null
}

build_pypi() (
  local work py
  work=$(mktemp -d "${RUNNER_TEMP:-/tmp}/ce-python.XXXXXX")
  trap 'find "$work" -depth -delete' EXIT
  mkdir "$work/source"
  git archive "$sha" pyproject.toml README.md src | tar -x -C "$work/source"
  "$python" -m venv "$work/venv"
  py="$work/venv/bin/python"
  local -a pip=("$py" -m pip --disable-pip-version-check --no-cache-dir)
  if [[ $mode == qualification ]]; then
    local wheelhouse=${CE_PYPI_BUILD_INPUTS:?Select qualified Python build inputs}
    "${pip[@]}" install --no-index --find-links "$wheelhouse" setuptools==84.2.1 wheel==0.48.0 packaging==26.3
  else
    "${pip[@]}" install setuptools==84.2.1 wheel==0.48.0 packaging==26.3 twine
  fi
  "${pip[@]}" wheel --no-index --no-deps --no-build-isolation --wheel-dir "$out" "$work/source"
  if [[ $mode == production ]]; then
    "$py" -m twine check "$out/$artifact"
    "${pip[@]}" install "$out/$artifact"
    mkdir "$work/smoke"
    "$py" -I -B tests/fixtures/command-package/check_installed.py "$tag" "$work/smoke"
  fi
)

case "$phase" in
  identity)
    printf '%s\n' "$actual"
    ;;
  prepare)
    mkdir -- "$out"
    if [[ $channel == npm ]]; then
      "$python" -I -B .github/scripts/npm-release.py pack --tag "$tag" --output-dir "$out"
      "$python" -I -B .github/scripts/npm-release.py smoke --tag "$tag" --output-dir "$out"
    else
      "$python" -I -B tests/test_release_contract.py -v
      build_pypi
    fi
    seal_artifact
    ;;
  artifact)
    verify_artifact
    printf '%s\n' "$out/$artifact"
    ;;
  registry|verify)
    test "$mode" = production
    verify_artifact
    if [[ $channel == npm ]]; then
      "$python" -I -B .github/scripts/npm-release.py "$phase" --tag "$tag" --output-dir "$out"
    else
      "$python" -I -B .github/scripts/release.py "$phase" --tag "$tag" --dist "$out" | jq -er .decision
    fi
    ;;
  qualify-build)
    test "$mode" = qualification
    exec bash tests/release/qualify.sh build "$channel" "$out" "$tag" "$artifact"
    ;;
  qualify)
    test "$mode" = qualification
    exec bash tests/release/qualify.sh publish "$channel" "$out" "$tag" "$artifact" "${4:?Select the downloaded distribution}"
    ;;
  *) exit 2 ;;
esac
