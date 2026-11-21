"""Build, smoke-test, and compare the npm release tarball."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import tomllib
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
NPM_SOURCE = ROOT / "npm"
REGISTRY = "https://registry.npmjs.org"
PUBLICATION_WAIT_SECONDS = 25 * 60
PUBLICATION_POLL_SECONDS = 30


def checked_wheels():
    lock_path = NPM_SOURCE / "wheelhouse.lock.json"
    wheelhouse = NPM_SOURCE / "wheelhouse"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if set(lock) != {"runtime", "build"} or not all(lock.values()):
        raise ValueError("wheelhouse lock must declare build and runtime inputs")
    names = set(lock["runtime"]) | set(lock["build"])
    if names != {path.name for path in wheelhouse.iterdir()} or len(names) != sum(map(len, lock.values())):
        raise ValueError("wheelhouse files do not match the lock")
    result = {}
    for group, entries in lock.items():
        result[group] = []
        for name, metadata in entries.items():
            if Path(name).name != name or not name.endswith(".whl"):
                raise ValueError(f"invalid wheel filename in lock: {name}")
            source = urlsplit(metadata["origin"])
            if source.scheme != "https" or source.hostname != "files.pythonhosted.org" or Path(source.path).name != name:
                raise ValueError(f"invalid wheel provenance: {name}")
            path = wheelhouse / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
                raise ValueError(f"wheelhouse SHA-256 mismatch: {name}")
            if name.split("-")[1] != metadata["version"]:
                raise ValueError(f"wheelhouse version mismatch: {name}")
            result[group].append(path)
    return lock_path, result


def build_sdk_wheel(work, vendor, build_wheels):
    source = work / "source"
    source.mkdir()
    for name in ("pyproject.toml", "README.md"):
        shutil.copyfile(ROOT / name, source / name)
    shutil.copytree(ROOT / "src", source / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
    venv = work / "build"
    subprocess.run([sys.executable, "-m", "venv", venv], check=True)
    python = venv / "bin" / "python"
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if not epoch:
        epoch = subprocess.check_output(
            ["git", "log", "-1", "--format=%ct"], cwd=ROOT, text=True,
        ).strip()
    env = os.environ | {"SOURCE_DATE_EPOCH": epoch, "PIP_CONFIG_FILE": os.devnull}
    pip = [python, "-m", "pip", "--isolated", "--disable-pip-version-check", "--no-cache-dir"]
    subprocess.run([*pip, "install", "--no-index", "--no-deps", *build_wheels], env=env, check=True)
    subprocess.run([*pip, "wheel", "--no-index", "--no-deps", "--no-build-isolation",
                    "--wheel-dir", vendor, source], env=env, check=True)


def pack(tarball):
    lock, groups = checked_wheels()
    if tarball.exists():
        raise ValueError(f"output already exists: {tarball}")
    tarball.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temporary:
        work = Path(temporary)
        staged = work / "npm"
        staged.mkdir()
        for filename in ("package.json", "README.md"):
            shutil.copyfile(NPM_SOURCE / filename, staged / filename)
        shutil.copytree(NPM_SOURCE / "bin", staged / "bin")
        shutil.copytree(
            ROOT / "src" / "command_execution", staged / "src" / "command_execution",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        vendor = staged / "vendor"
        vendor.mkdir()
        for wheel in groups["runtime"]:
            shutil.copyfile(wheel, vendor / wheel.name)
        build_sdk_wheel(work, vendor, groups["build"])
        manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(vendor.glob("*.whl"))}
        (vendor / "SHA256SUMS").write_text(
            "".join(f"{digest}  {name}\n" for name, digest in manifest.items()), encoding="utf-8",
        )
        provenance = json.loads(lock.read_text(encoding="utf-8"))["runtime"]
        (vendor / "runtime-inputs.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        subprocess.run([
            "npm", "pack", "--ignore-scripts", "--pack-destination", tarball.parent,
        ], cwd=staged, check=True)
    if not tarball.is_file():
        raise ValueError(f"npm pack did not produce {tarball}")


def smoke(tarball):
    with TemporaryDirectory() as temporary:
        subprocess.run([
            "npm", "install", "--prefix", temporary, "--ignore-scripts", "--no-audit",
            "--no-fund", tarball,
        ], check=True)
        launcher = Path(temporary) / "node_modules" / ".bin" / "command-execution"
        command = {"commands": [{"argv": [sys.executable, "-c", "print('npm smoke')"],
                                 "sync-mode": ["std-out"]}]}
        result = subprocess.run(
            [launcher, "run"], input=json.dumps(command), text=True,
            stdout=subprocess.PIPE, check=True,
        )
        events = [json.loads(line) for line in result.stdout.splitlines()]
        output = b"".join(
            base64.b64decode(event["data"])
            for event in events if event["event"] == "output" and event["stream"] == "out"
        )
        if output != b"npm smoke\n" or events[-1]["result"]["status"] != "succeeded":
            raise ValueError("installed npm CLI did not run the expected child command")
        rejected = subprocess.run(
            [launcher, "validate"], input="{}", text=True, stdout=subprocess.DEVNULL,
        )
        if rejected.returncode != 2:
            raise ValueError("installed npm CLI did not preserve the validation exit code")
    print("Installed npm CLI passed")


def registry(name, version, integrity, registry_url=REGISTRY):
    request = Request(f"{registry_url.rstrip('/')}/{quote(name, safe='')}/{quote(version, safe='')}",
                      headers={"Cache-Control": "no-cache"})
    try:
        with urlopen(request, timeout=30) as response:
            package = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return "publish"
        raise
    if package.get("dist", {}).get("integrity") != integrity:
        raise ValueError(f"npm already has {name}@{version} with different bytes")
    return "already-published"


def verify_publication(name, version, integrity, registry_url=REGISTRY):
    """Wait for npm's publish-time validation before comparing public integrity."""
    deadline = monotonic() + PUBLICATION_WAIT_SECONDS
    while registry(name, version, integrity, registry_url) != "already-published":
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise ValueError(
                f"npm did not make {name}@{version} public within "
                f"{PUBLICATION_WAIT_SECONDS // 60} minutes"
            )
        print(f"Waiting for npm to make {name}@{version} public", flush=True)
        sleep(min(PUBLICATION_POLL_SECONDS, remaining))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("pack", "smoke", "registry", "verify"))
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist" / "npm")
    parser.add_argument("--registry-url", default=REGISTRY)
    args = parser.parse_args()
    try:
        manifest = json.loads((NPM_SOURCE / "package.json").read_text(encoding="utf-8"))
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        name, version = manifest["name"], manifest["version"]
        if (name, version) != (project["name"], project["version"]) or args.tag != f"v{version}":
            raise ValueError("npm, Python and tag release identities must agree")
        tarball = args.output_dir.resolve() / f"{name}-{version}.tgz"
        if args.phase == "pack":
            pack(tarball)
        elif args.phase == "smoke":
            smoke(tarball)
        else:
            integrity = "sha512-" + base64.b64encode(hashlib.sha512(tarball.read_bytes()).digest()).decode()
            if args.phase == "registry":
                print(registry(name, version, integrity, args.registry_url))
            else:
                verify_publication(name, version, integrity, args.registry_url)
                print(f"Verified {name}@{version}: {integrity}")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"npm release: {error}\n")


if __name__ == "__main__":
    main()
