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


class MetadataContract(unittest.TestCase):
    """Literal user-selected version; no production-generated oracle."""

    def test_bootstrap_has_independent_package_identity(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        self.assertEqual(project["name"], CONTRACT["name"])

    def test_distribution_declares_requested_release(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        self.assertEqual(project["version"], CONTRACT["version"])

    def test_module_declares_requested_release(self):
        self.assertEqual(
            declared_version(ROOT / "src/command_execution/__init__.py"),
            CONTRACT["version"],
        )


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
        missing = HTTPError("https://pypi.org", 404, "Not Found", None, None)
        with patch.object(self.gate, "urlopen", side_effect=missing):
            self.assertEqual(self.check_registry(), "publish")

    def test_exact_published_files_are_idempotent_and_unchanged(self):
        response = (FIXTURES / "published-release.json").read_bytes()
        before = self.artifact.read_bytes()
        replies = [io.BytesIO(response), io.BytesIO(response)]
        with patch.object(self.gate, "urlopen", side_effect=replies):
            self.assertEqual(
                [self.check_registry(), self.check_registry()],
                ["already-published", "already-published"],
            )
        self.assertEqual(self.artifact.read_bytes(), before)
        self.assertEqual(list(self.dist.iterdir()), [self.artifact])

    def test_different_published_bytes_refuse_another_upload(self):
        self.artifact.write_bytes(b"different candidate bytes\n")
        response = (FIXTURES / "published-release.json").read_bytes()
        with patch.object(self.gate, "urlopen", return_value=io.BytesIO(response)):
            with self.assertRaisesRegex(ValueError, "published"):
                self.check_registry()

    def test_partial_published_release_is_not_a_completed_replay(self):
        with patch.object(self.gate, "urlopen", return_value=io.BytesIO(b'{"urls": []}')):
            with self.assertRaisesRegex(ValueError, "published"):
                self.check_registry()

    def test_network_failure_does_not_authorize_publication(self):
        with patch.object(self.gate, "urlopen", side_effect=URLError("unavailable")):
            with self.assertRaisesRegex(ValueError, "registry"):
                self.check_registry()

    def test_registry_permission_failure_is_not_an_absent_release(self):
        denied = HTTPError("https://pypi.org", 403, "Forbidden", None, None)
        with patch.object(self.gate, "urlopen", side_effect=denied):
            with self.assertRaisesRegex(ValueError, "registry"):
                self.check_registry()

    def test_empty_local_distribution_cannot_be_published(self):
        self.artifact.unlink()
        missing = HTTPError("https://pypi.org", 404, "Not Found", None, None)
        with patch.object(self.gate, "urlopen", side_effect=missing):
            with self.assertRaisesRegex(ValueError, "distribution"):
                self.check_registry()


if __name__ == "__main__":
    unittest.main()
