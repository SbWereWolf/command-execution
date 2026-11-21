"""Verify qualification records. Capture remains the responsibility of each job."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

CHANNELS = ("npm", "pypi")
START_MARKER = "CE_RELEASE_START "
EXIT_MARKER = "CE_RELEASE_EXIT "
UPLOADS = {"npm": ("npm", "publish", "--registry"),
           "pypi": ("twine", "upload", "--repository-url")}
GATES = {"npm": "npm-release.py", "pypi": "release.py"}
LOG_IDENTITY = ("run_id", "attempt", "tag", "sha", "job_key", "release_step")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_path(root, name):
    path = Path(name)
    require(not path.is_absolute() and ".." not in path.parts, f"invalid evidence path: {name}")
    location = root / path
    require(location.is_file() and location.stat().st_size > 0, f"missing evidence: {name}")
    return location


def digest(path, channel):
    data = path.read_bytes()
    if channel == "npm":
        return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")
    return hashlib.sha256(data).hexdigest()


def verify_artifact(root, proof, channel):
    staged = artifact_path(root, proof["built_file"])
    downloaded = artifact_path(root, proof["downloaded_file"])
    require(staged != downloaded, "build and registry readback must be distinct files")
    actual = digest(staged, channel)
    require(actual == digest(downloaded, channel) == proof["registry_digest"], f"{channel} registry bytes differ")


def verify_inputs(root, items, channel):
    require(bool(items), f"{channel} lacks an input inventory")
    names = set()
    for item in items:
        path = artifact_path(root, item["path"])
        require(path not in names, f"repeated input: {item['path']}")
        names.add(path)
        require(item["channel"] == channel and item["kind"] in {"source", "tool", "dependency"},
                f"foreign or prebuilt input: {item['path']}")
        require(bool(item["origin"]) and bool(item["version"]), "input origin or version is absent")
        require(digest(path, "pypi") == item["sha256"], f"input digest mismatch: {item['path']}")


def check_endpoint(value):
    url = urlsplit(value)
    require(url.scheme == "http" and url.hostname == "127.0.0.1" and url.port
            and url.username is None and url.password is None, f"expected a test loopback endpoint: {value}")


def match_run(data, tag, source):
    require(data["event"] == "push" and data["head_branch"] == tag, "run is not the push of the stated tag")
    require(data["head_sha"] == source, "run SHA does not match")
    require(data["status"] == "completed" and data["conclusion"] == "failure",
            "expected a completed run containing a genuine failure")
    require(type(data["id"]) is int and data["id"] > 0 and type(data["run_attempt"]) is int
            and data["run_attempt"] > 0, "missing run or attempt identity")


def match_job(jobs, run, record, conclusion):
    hits = [job for job in jobs if job["id"] == record["job_id"]]
    require(len(hits) == 1, "job is absent or duplicated in Actions evidence")
    job = hits[0]
    for key, expected in (("run_id", run["id"]), ("run_attempt", run["run_attempt"]),
                          ("head_sha", run["head_sha"]), ("name", record["job_name"])):
        require(job[key] == expected, f"job identity differs: {key}")
    require(job["status"] == "completed" and job["conclusion"] == conclusion
            and job.get("started_at") and job.get("completed_at"), f"job did not finish with {conclusion}")
    return job


def assert_step(job, name, conclusion):
    results = [step["conclusion"] for step in job["steps"] if step["name"] == name]
    require(results == [conclusion], f"step {name!r} did not finish with {conclusion}")


def endpoint_arguments(argv, option):
    options = [arg.split("=", 1)[1] for arg in argv if arg.startswith(option + "=")]
    options.extend(argv[index + 1] if index + 1 < len(argv) else None
                   for index, arg in enumerate(argv) if arg == option)
    return options


def release_operation(channel, argv, endpoint):
    check_endpoint(endpoint)
    require(isinstance(argv, list) and len(argv) >= 2 and all(isinstance(arg, str) for arg in argv),
            "release command has no valid argv")
    binary, *arguments = argv
    launcher = Path(binary).name
    executable, phase, endpoint_option = UPLOADS[channel]
    if (launcher, arguments[0]) == (executable, phase):
        require(not any(arg.split("=", 1)[0] == "--dry-run" for arg in arguments),
                "no actual publish/upload command recorded")
        require(endpoint_arguments(arguments, endpoint_option) == [endpoint], "upload targets another registry")
        return "upload"

    if re.fullmatch(r"python(?:3(?:[.][0-9]+)?)?", launcher):
        while arguments and arguments[0] in {"-I", "-B"}:
            arguments = arguments[1:]
        if len(arguments) >= 2 and Path(arguments[0]).parts[-3:] == (".github", "scripts", GATES[channel]) and arguments[1] == "registry":
            require(endpoint_arguments(arguments[2:], "--registry-url") == [endpoint], "gate targets another registry")
            return "gate"
    raise ValueError(f"{channel} evidence does not identify its release operation or registry gate")


def operation_header(channel, record, operation):
    command = record["release_command"]
    return {
        **{key: record[key] for key in LOG_IDENTITY},
        "channel": channel, "operation": operation, "argv": command["argv"],
        "endpoint": record["endpoint"],
    }


def operation_output(root, command, header):
    lines = artifact_path(root, command["log"]).read_text(encoding="utf-8").splitlines()
    require(len(lines) >= 3 and lines[0].startswith(START_MARKER) and lines[-1].startswith(EXIT_MARKER),
            "expected the capture log of the release operation")
    require(not any(line.startswith((START_MARKER, EXIT_MARKER)) for line in lines[1:-1]),
            "mixed operation logs")
    require(json.loads(lines[0][len(START_MARKER):]) == header, "log is for a different release operation")
    require(json.loads(lines[-1][len(EXIT_MARKER):]) == {"exit": command["exit"]},
            "release log exit code does not match")
    return "\n".join(lines[1:-1])


def verify_command(root, channel, record, expected_success):
    command = record["release_command"]
    endpoint = record["endpoint"]
    check_endpoint(endpoint)
    require(command["endpoint"] == endpoint, "release command is not bound to the expected endpoint")
    operation = release_operation(channel, command["argv"], endpoint)
    if expected_success:
        require(operation == "upload", "no actual publish/upload command recorded")
    exit_code = command["exit"]
    require(type(exit_code) is int and (exit_code == 0) == expected_success, "unexpected command exit status")
    log = operation_output(root, command, operation_header(channel, record, operation))
    if not expected_success:
        require(urlsplit(endpoint).netloc in log, "registry failure output does not identify the registry address")
        require(re.search(r"connection refused|econnrefused|failed to connect|connect timeout|etimedout|"
                          r"connectionerror|network is unreachable|could not connect", log, re.IGNORECASE),
                "failure log does not show a registry connection failure")


def verify_run(root, descriptor, failing, source):
    tag = descriptor["tag"]
    require(re.fullmatch(r"qualify-ce-v[0-9]+[.][0-9]+[.][0-9]+(?:-r[1-9][0-9]*)?-(pypi|npm)-outage", tag)
            and tag.endswith(f"-{failing}-outage"), "incorrect qualification tag")
    run = read_json(artifact_path(root, descriptor["run_json"]))
    jobs = read_json(artifact_path(root, descriptor["jobs_json"]))["jobs"]
    match_run(run, tag, source)
    require(len({descriptor[channel]["job_id"] for channel in CHANNELS}) == 2, "one job cannot prove both channels")

    for channel in CHANNELS:
        record = descriptor[channel]
        require((record["run_id"], record["attempt"], record["tag"], record["sha"])
                == (run["id"], run["run_attempt"], tag, source), "receipt is from a different run, attempt, tag or SHA")
        passed = channel != failing
        job = match_job(jobs, run, record, "success" if passed else "failure")
        require(record["job_key"] and record["ready_step"] != record["release_step"],
                "missing job or prerequisite identity")
        assert_step(job, record["ready_step"], "success")
        assert_step(job, record["release_step"], "success" if passed else "failure")
        steps = [step["name"] for step in job["steps"]]
        require(steps.index(record["ready_step"]) < steps.index(record["release_step"]),
                "release operation ran before its prerequisite")
        verify_command(root, channel, record, passed)
        if passed:
            assert_step(job, record["install_step"], "success")
            require(type(record["install"]["exit"]) is int and record["install"]["exit"] == 0
                    and record["install"]["fresh_prefix"] is True, "fresh install not established")
            artifact_path(root, record["install"]["log"])
            network = artifact_path(root, record["network_log"]).read_text(encoding="utf-8").splitlines()
            blocked_hosts = ("pypi.org", "files.pythonhosted.org") if channel == "npm" else ("registry.npmjs.org",)
            require(all(f"unreachable {host}" in network for host in blocked_hosts),
                    "missing observation of the other registry being unreachable")
            verify_artifact(root, record["artifact"], channel)
            verify_inputs(root, record["inputs"], channel)

    return run["id"], tag.rsplit("-", 2)[0]


def verify_qualification(path, expected_mode):
    manifest = read_json(path)
    source = manifest["sha"]
    require(manifest["evidence_kind"] == expected_mode, "fixture is not a qualification run")
    require(re.fullmatch(r"[0-9a-f]{40}", source), "invalid candidate SHA")
    require(set(manifest["runs"]) == set(CHANNELS), "both failure directions are required")
    npm_run, npm_release = verify_run(path.parent, manifest["runs"]["npm"], "npm", source)
    pypi_run, pypi_release = verify_run(path.parent, manifest["runs"]["pypi"], "pypi", source)
    require(npm_run != pypi_run and npm_release == pypi_release, "expected two distinct runs for one release")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args()
    mode = "fixture" if args.fixture else "actions"
    try:
        verify_qualification(args.manifest, mode)
    except (KeyError, OSError, TypeError, ValueError) as error:
        parser.exit(1, f"evidence: {error}\n")
    print(f"Verified two complementary {mode} records")


if __name__ == "__main__":
    main()
