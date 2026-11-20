"""Build, smoke-test, and compare the npm release tarball."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import tomllib
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
NPM_SOURCE = ROOT / "npm"
REGISTRY = "https://registry.npmjs.org"
PUBLICATION_WAIT_SECONDS = 25 * 60
PUBLICATION_POLL_SECONDS = 30


def pack(tarball):
    tarball.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temporary:
        staged = Path(temporary)
        for filename in ("package.json", "README.md"):
            shutil.copyfile(NPM_SOURCE / filename, staged / filename)
        shutil.copytree(NPM_SOURCE / "bin", staged / "bin")
        shutil.copytree(
            ROOT / "src" / "command_execution", staged / "src" / "command_execution",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        subprocess.run([
            sys.executable, "-m", "pip", "download", "--disable-pip-version-check",
            "--index-url", "https://pypi.org/simple", "--only-binary=:all:",
            "--no-deps", "--require-hashes", "-r", NPM_SOURCE / "requirements.txt",
            "--dest", staged / "vendor",
        ], check=True)
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


def registry(name, version, integrity):
    request = Request(f"{REGISTRY}/{name}/{version}",
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


def verify_publication(name, version, integrity):
    """Wait for npm's publish-time validation before comparing public integrity."""
    deadline = monotonic() + PUBLICATION_WAIT_SECONDS
    while registry(name, version, integrity) != "already-published":
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
                print(registry(name, version, integrity))
            else:
                verify_publication(name, version, integrity)
                print(f"Verified {name}@{version}: {integrity}")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"npm release: {error}\n")


if __name__ == "__main__":
    main()
