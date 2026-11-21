#!/usr/bin/env bash
# Publish real bytes to an isolated receiver and reinstall from that receiver.
set -euo pipefail
kind=${1:?Select npm or pypi}
artifact=$(realpath -- "${2:?Select candidate artifact}")
version=${3:?Select candidate version}
shift 3
root=${CE_CHECK_ROOT:?Run inside with-registry.sh}
mkdir "$root/download"
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]

capture_upload() {
  local endpoint=$1
  shift
  if [[ -n ${CE_CAPTURE_RELEASE-} ]]; then
    "${CE_PYTHON:?}" -B "$CE_CAPTURE_RELEASE" "$kind" "$endpoint" "Qualify release" "$root/operation.log" -- "$@"
  else
    "$@" > "$root/upload.log" 2>&1
  fi
}

if [[ $kind == npm ]]; then
  test "${CE_NPM_REGISTRY:?}" = http://127.0.0.1:4873/
  capture_upload "$CE_NPM_REGISTRY" npm publish "$artifact" --registry "$CE_NPM_REGISTRY" \
    --fetch-retries=0 --ignore-scripts --json
  npm view "command-execution@$version" dist --registry "$CE_NPM_REGISTRY" --json >"$root/dist.json"
  tarball=$(jq -er .tarball "$root/dist.json")
  [[ $tarball == "$CE_NPM_REGISTRY"* ]]
  curl -q -fsSL "$tarball" -o "$root/download/command-execution-$version.tgz"
  staged="sha512-$(openssl dgst -sha512 -binary "$artifact" | base64 -w0)"
  readback="sha512-$(openssl dgst -sha512 -binary "$root/download/command-execution-$version.tgz" | base64 -w0)"
  test "$staged" = "$readback"
  test "$staged" = "$(jq -er .integrity "$root/dist.json")"
  npm install --prefix "$root/installed" --registry "$CE_NPM_REGISTRY" --cache "$root/install-cache"     --no-audit --no-fund "command-execution@$version" >"$root/install.log"
  launcher="$root/installed/node_modules/.bin/command-execution"
  printf '%s\n' '{"commands":[{"argv":["/bin/echo","CE qualification"],"sync-mode":["std-out"]}]}' | "$launcher" run > "$root/cli.jsonl"
  jq -se '(map(select(.event=="output" and .stream=="out").data)|join("")|@base64d)=="CE qualification\n"
    and (last.result.status=="succeeded")' "$root/cli.jsonl" >/dev/null
  code=0
  printf '{}\n' | "$launcher" validate >"$root/validation.log" 2>&1 || code=$?
  test "$code" = 2
  printf '%s\n' "$staged" > "$root/digest"
elif [[ $kind == pypi ]]; then
  test "${CE_PYPI_UPLOAD:?}" = http://127.0.0.1:3141/root/qualification/
  tools=${CE_TWINE:?Select Twine with the configured Python test runtime}
  python=${CE_PYTHON:?Select the clean-install Python}
  fixture=${CE_SDK_FIXTURE:?Select the existing CE SDK oracle}
  capture_upload "$CE_PYPI_UPLOAD" "$tools" upload --repository-url "$CE_PYPI_UPLOAD" \
    --disable-progress-bar "$artifact" "$@"
  "$python" -m venv "$root/venv"
  pip=("$root/venv/bin/python" -m pip --disable-pip-version-check --no-cache-dir)
  "${pip[@]}" download --index-url "$CE_PYPI_SIMPLE" --no-deps --dest "$root/download" "command-execution==$version" >"$root/download.log" 2>&1
  staged=$(sha256sum "$artifact" | cut -d' ' -f1)
  readback=$(sha256sum "$root/download/${artifact##*/}" | cut -d' ' -f1)
  test "$staged" = "$readback"
  "${pip[@]}" install --index-url "$CE_PYPI_SIMPLE" "command-execution==$version" packaging >"$root/install.log" 2>&1
  "${pip[@]}" check >"$root/pip-check.log"
  mkdir "$root/sdk-workspace"
  "$root/venv/bin/python" -I -B "$fixture" "v$version" "$root/sdk-workspace" > "$root/sdk.log"
  printf '%s\n' '{"commands":[{"argv":["/bin/echo","CE qualification"],"sync-mode":["std-out"]}]}' |
    "$root/venv/bin/command-execution" run > "$root/cli.jsonl"
  jq -se '(map(select(.event=="output" and .stream=="out").data)|join("")|@base64d)=="CE qualification\n"
    and (last.result.status=="succeeded")' "$root/cli.jsonl" >/dev/null
  printf '%s\n' "$staged" > "$root/digest"
else
  exit 2
fi
printf 'Local %s publish, download and clean install verified for CE %s\n' "$kind" "$version"
