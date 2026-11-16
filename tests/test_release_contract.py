"""Independent 1.0.0 expectations and read-only publication gate behavior.

Metadata tests observe the real existing bootstrap. Gate tests are authored
before implementation and require the future gate; their missing-file error
is deliberately not used as behavioral RED evidence.
"""
import ast
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
CONTRACT = json.loads((FIXTURES / "release-contract.json").read_text())


def declared_version(path):
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "__version__"
                   for target in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError("Package does not declare __version__")


def checked_registry_reply(*, payload=b"", failure=None):
    """Observe urllib's effective request before returning a fixture.

    Both supported urlopen call styles are accepted. Identity and method are
    independent literal expectations, never a production URL helper's output.
    """
    def reply(target, data=None, *args, **kwargs):
        if isinstance(target, Request):
            actual_url = target.full_url
            actual_method = target.get_method()
            if data is not None and target.method is None:
                actual_method = "POST"
        else:
            actual_url = target
            actual_method = "POST" if data is not None else "GET"
        actual = (actual_url, actual_method)
        expected = (CONTRACT["release_api_url"], CONTRACT["request_method"])
        if actual != expected:
            raise AssertionError(f"Unexpected registry request: {actual!r}")
        if failure is not None:
            raise failure
        return io.BytesIO(payload)
    return reply


class MetadataContract(unittest.TestCase):
    """Literal user-selected version; no production-generated oracle."""

    def test_bootstrap_has_independent_package_identity(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        self.assertEqual(project["name"], CONTRACT["name"])

    def test_distribution_declares_requested_release(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        self.assertEqual(project["version"], CONTRACT["source_version"])

    def test_module_declares_requested_release(self):
        self.assertEqual(
            declared_version(ROOT / "src/command_execution/__init__.py"),
            CONTRACT["source_version"],
        )


class RegistryTransportContract(unittest.TestCase):
    """Sensitivity controls runnable before the future producer exists."""

    def test_matching_string_get_receives_the_fixture(self):
        reply = checked_registry_reply(payload=b"approved")
        with reply(CONTRACT["release_api_url"], timeout=10) as result:
            self.assertEqual(result.read(), b"approved")

    def test_matching_request_object_receives_the_fixture(self):
        reply = checked_registry_reply(payload=b"approved")
        request = Request(CONTRACT["release_api_url"], method="GET")
        with reply(request, timeout=10) as result:
            self.assertEqual(result.read(), b"approved")

    def test_matching_get_can_receive_the_absent_release(self):
        absent = HTTPError(CONTRACT["release_api_url"], 404, "Not Found", None, None)
        reply = checked_registry_reply(failure=absent)
        with self.assertRaises(HTTPError) as raised:
            reply(CONTRACT["release_api_url"])
        self.assertEqual(raised.exception.code, 404)

    def test_wrong_package_version_or_route_fails_before_the_404_fixture(self):
        absent = HTTPError(CONTRACT["release_api_url"], 404, "Not Found", None, None)
        reply = checked_registry_reply(failure=absent)
        for url in CONTRACT["invalid_release_urls"]:
            with self.subTest(url=url):
                with self.assertRaisesRegex(AssertionError, "registry request"):
                    reply(url)

    def test_non_get_method_fails_before_the_404_fixture(self):
        absent = HTTPError(CONTRACT["release_api_url"], 404, "Not Found", None, None)
        reply = checked_registry_reply(failure=absent)
        for method in ("POST", "PUT", "DELETE"):
            with self.subTest(method=method):
                request = Request(CONTRACT["release_api_url"], method=method)
                with self.assertRaisesRegex(AssertionError, "registry request"):
                    reply(request)

    def test_implicit_post_body_fails_before_the_success_fixture(self):
        reply = checked_registry_reply(payload=b"approved")
        with self.assertRaisesRegex(AssertionError, "registry request"):
            reply(CONTRACT["release_api_url"], b"body")


class ReleaseGateContract(unittest.TestCase):
    """Future gate subject; network service responses are independent inputs."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "command_release_gate", ROOT / ".github/scripts/release.py"
        )
        cls.gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.gate)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.project = self.workspace / "project"
        shutil.copytree(FIXTURES / "release-project", self.project)
        self.dist = self.workspace / "dist"
        self.dist.mkdir()
        self.artifact = self.dist / CONTRACT["filename"]
        self.artifact.write_text(CONTRACT["distribution_text"])

    def test_accepts_matching_stable_tag_and_metadata(self):
        self.assertEqual(
            self.gate.validate_release(self.project, CONTRACT["tag"]),
            ("command-execution", "1.0.0"),
        )

    def test_rejects_tag_that_selects_another_version(self):
        with self.assertRaisesRegex(ValueError, "tag"):
            self.gate.validate_release(self.project, CONTRACT["mismatched_tag"])

    def test_rejects_branch_name_as_release_tag(self):
        with self.assertRaisesRegex(ValueError, "tag"):
            self.gate.validate_release(self.project, "master")

    def test_rejects_module_and_distribution_version_mismatch(self):
        (self.project / "src/command_execution/__init__.py").write_text(
            '__version__ = "0.9.0"\n'
        )
        with self.assertRaisesRegex(ValueError, "version"):
            self.gate.validate_release(self.project, CONTRACT["tag"])

    def check_registry(self):
        return self.gate.check_registry(
            CONTRACT["name"], CONTRACT["version"], self.dist
        )

    def test_absent_release_permits_publication(self):
        missing = HTTPError(CONTRACT["release_api_url"], 404, "Not Found", None, None)
        with patch.object(self.gate, "urlopen",
                          side_effect=checked_registry_reply(failure=missing)):
            self.assertEqual(self.check_registry(), "publish")

    def test_exact_published_files_are_idempotent_and_unchanged(self):
        response = (FIXTURES / "published-release.json").read_bytes()
        before = self.artifact.read_bytes()
        with patch.object(self.gate, "urlopen",
                          side_effect=checked_registry_reply(payload=response)):
            self.assertEqual(
                [self.check_registry(), self.check_registry()],
                ["already-published", "already-published"],
            )
        self.assertEqual(self.artifact.read_bytes(), before)
        self.assertEqual(list(self.dist.iterdir()), [self.artifact])

    def test_different_published_bytes_refuse_another_upload(self):
        self.artifact.write_bytes(b"different candidate bytes\n")
        response = (FIXTURES / "published-release.json").read_bytes()
        with patch.object(self.gate, "urlopen",
                          side_effect=checked_registry_reply(payload=response)):
            with self.assertRaisesRegex(ValueError, "published"):
                self.check_registry()

    def test_partial_published_release_is_not_a_completed_replay(self):
        with patch.object(self.gate, "urlopen",
                          side_effect=checked_registry_reply(payload=b'{"urls": []}')):
            with self.assertRaisesRegex(ValueError, "published"):
                self.check_registry()

    def test_network_failure_does_not_authorize_publication(self):
        with patch.object(self.gate, "urlopen",
                          side_effect=checked_registry_reply(failure=URLError("unavailable"))):
            with self.assertRaisesRegex(ValueError, "registry"):
                self.check_registry()

    def test_registry_permission_failure_is_not_an_absent_release(self):
        denied = HTTPError(CONTRACT["release_api_url"], 403, "Forbidden", None, None)
        with patch.object(self.gate, "urlopen",
                          side_effect=checked_registry_reply(failure=denied)):
            with self.assertRaisesRegex(ValueError, "registry"):
                self.check_registry()

    def test_empty_local_distribution_cannot_be_published(self):
        self.artifact.unlink()
        missing = HTTPError(CONTRACT["release_api_url"], 404, "Not Found", None, None)
        with patch.object(self.gate, "urlopen",
                          side_effect=checked_registry_reply(failure=missing)):
            with self.assertRaisesRegex(ValueError, "distribution"):
                self.check_registry()


if __name__ == "__main__":
    unittest.main()
