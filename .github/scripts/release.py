"""Tag and registry admission for the independent package release."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
from time import sleep
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def validate_release(root, tag):
    """Validate the selected source before publication."""
    root = Path(root)
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    name, version = project["name"], project["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) or tag != "v" + version:
        raise ValueError("tag must select the stable distribution version")
    module = ast.parse((root / "src/command_execution/__init__.py").read_text())
    versions = [ast.literal_eval(node.value) for node in module.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "__version__"
                        for target in node.targets)]
    if versions != [version]:
        raise ValueError("module version differs from distribution version")
    return name, version


def check_registry(name, version, dist):
    """Decide publication or exact replay without writing to the registry."""
    files = sorted(Path(dist).glob("*.whl"))
    if not files:
        raise ValueError("distribution has no wheel to publish")
    local = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    url = f"https://pypi.org/pypi/{quote(name, safe='')}/{quote(version, safe='')}/json"
    try:
        with urlopen(Request(url, method="GET"), timeout=30) as response:
            document = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return "publish"
        raise ValueError(f"registry refused the release query: HTTP {error.code}") from error
    except (URLError, OSError, ValueError) as error:
        raise ValueError(f"registry query failed: {error}") from error
    try:
        published = {row["filename"]: row["digests"]["sha256"] for row in document["urls"]}
    except (KeyError, TypeError) as error:
        raise ValueError("registry returned invalid release metadata") from error
    if published != local:
        raise ValueError("published release differs from the candidate; use a new version")
    return "already-published"


def verify_publication(name, version, dist):
    """Wait briefly for the uploaded version to become visible in PyPI's API."""
    for delay in (1, 2, 4, 8, 15, 30):
        if check_registry(name, version, dist) == "already-published":
            return "already-published"
        sleep(delay)
    if check_registry(name, version, dist) == "already-published":
        return "already-published"
    raise ValueError("published release did not become visible in the registry")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("validate", "registry", "verify"))
    parser.add_argument("--tag", required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    try:
        name, version = validate_release(args.root, args.tag)
        decision = "validated"
        if args.phase == "registry":
            decision = check_registry(name, version, args.dist)
        elif args.phase == "verify":
            decision = verify_publication(name, version, args.dist)
    except (ValueError, OSError) as error:
        parser.exit(1, f"release: {error}\n")
    print(json.dumps({"name": name, "version": version, "decision": decision}))
    if args.phase == "registry" and os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"decision={decision}\n")


if __name__ == "__main__":
    main()
