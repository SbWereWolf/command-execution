"""Execute one qualification release operation and capture its combined output."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from evidence import EXIT_MARKER, START_MARKER, operation_header, release_operation, require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", choices=("npm", "pypi"))
    parser.add_argument("endpoint")
    parser.add_argument("step", help="GitHub Actions display name of the executing step")
    parser.add_argument("log", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    try:
        argv = args.command[1:] if args.command[:1] == ["--"] else args.command
        operation = release_operation(args.channel, argv, args.endpoint)
        tag = os.environ["GITHUB_REF_NAME"]
        require(tag.startswith("qualify-ce-v") and os.environ["GITHUB_REF"] == f"refs/tags/{tag}",
                "capture requires a qualification tag")
        record = {
            "run_id": int(os.environ["GITHUB_RUN_ID"]), "attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
            "tag": tag, "sha": os.environ["GITHUB_SHA"], "job_key": os.environ["GITHUB_JOB"],
            "release_step": args.step, "endpoint": args.endpoint,
            "release_command": {"argv": argv},
        }
        header = operation_header(args.channel, record, operation)
        with args.log.open("xb", buffering=0) as log:
            log.write((START_MARKER + json.dumps(header) + "\n").encode())
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=log,
                                    stderr=subprocess.STDOUT, check=False)
            if result.returncode < 0:
                raise ValueError(f"release command stopped by signal {-result.returncode}")
            log.write(("\n" + EXIT_MARKER + json.dumps({"exit": result.returncode}) + "\n").encode())
    except (KeyError, OSError, ValueError) as error:
        parser.exit(1, f"capture: {error}\n")
    parser.exit(result.returncode)


if __name__ == "__main__":
    main()
