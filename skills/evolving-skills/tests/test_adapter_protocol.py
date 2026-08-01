import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    import adapter_protocol
except ModuleNotFoundError:
    adapter_protocol = None


VALID_ADAPTER = """\
---
schema: superpowers-adapter/v1
extends: wrap-session
contract: 1
adapter-version: 1
---
Use the repository closeout policy.
"""

VALID_OBSERVATION = {
    "schema": "superpowers-observation/v1",
    "runtime": {
        "provider": "openai",
        "model": "gpt-5.6-sol",
        "reasoning-effort": "high",
        "harness": "codex-app",
        "harness-version": "unknown",
        "interface": "desktop",
    },
    "skills": {
        "global": {
            "name": "wrap-session",
            "contract": 1,
            "plugin-version": "unknown",
            "git-commit": "unknown",
        },
        "adapter": {
            "path": "unknown",
            "version": "unknown",
            "git-commit": "unknown",
        },
    },
    "observation": {
        "phase": "durable-context",
        "expected": "Update the existing task record.",
        "actual": "Created a duplicate handoff document.",
        "evidence": "Two handoff files were present.",
        "diagnosis": "global-skill",
    },
    "candidate": {
        "scope": "potentially-global",
        "target": "skill",
        "status": "observed",
    },
}


def _valid_observation_metadata() -> dict:
    """Return a fresh deep copy of a valid v1 observation metadata dict."""
    return copy.deepcopy(VALID_OBSERVATION)


class ProtocolTestCase(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            adapter_protocol,
            "adapter_protocol implementation must exist",
        )


class ParseFrontmatterTests(ProtocolTestCase):
    def test_parses_nested_mappings_and_scalar_types(self):
        metadata, body = adapter_protocol.parse_frontmatter(
            """\
---
title: "Closeout adapter"
enabled: true
disabled: false
optional: null
contract: 1
runtime:
  provider: 'openai'
  details:
    interface: desktop
---
Body text.
"""
        )

        self.assertEqual(
            metadata,
            {
                "title": "Closeout adapter",
                "enabled": True,
                "disabled": False,
                "optional": None,
                "contract": 1,
                "runtime": {
                    "provider": "openai",
                    "details": {"interface": "desktop"},
                },
            },
        )
        self.assertEqual(body, "Body text.\n")

    def test_rejects_missing_frontmatter(self):
        with self.assertRaisesRegex(ValueError, "frontmatter"):
            adapter_protocol.parse_frontmatter("No metadata here.\n")

    def test_rejects_malformed_indentation(self):
        malformed_documents = (
            "---\nruntime:\n    provider: openai\n---\n",
            "---\nruntime:\n  provider: openai\n   model: gpt\n---\n",
            "---\nruntime:\n\tprovider: openai\n---\n",
        )

        for document in malformed_documents:
            with self.subTest(document=document):
                with self.assertRaisesRegex(ValueError, "indent"):
                    adapter_protocol.parse_frontmatter(document)

    def test_rejects_lists_and_duplicate_keys(self):
        invalid_documents = (
            "---\nitems:\n  - one\n---\n",
            "---\nschema: one\nschema: two\n---\n",
            "---\nitems: [one, two]\n---\n",
        )

        for document in invalid_documents:
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    adapter_protocol.parse_frontmatter(document)


class DiscoverAdapterTests(ProtocolTestCase):
    def write_adapter(self, root, content):
        path = root / ".agents" / "superpowers" / "wrap-session" / "adapter.md"
        path.parent.mkdir(parents=True)
        path.write_text(content)
        return path

    def test_absent_adapter_selects_global_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            result = adapter_protocol.discover_adapter(
                Path(directory), "wrap-session", {1}
            )

        self.assertEqual(result["status"], "absent")
        self.assertNotIn("errors", result)

    def test_invalid_skill_names_never_fall_back_to_absent(self):
        invalid_names = (
            "",
            ".",
            "..",
            "Wrap-Session",
            "wrap_session",
            "wrap/session",
            "/wrap-session",
            "wrap--session",
        )
        with tempfile.TemporaryDirectory() as directory:
            for skill_name in invalid_names:
                with self.subTest(skill_name=skill_name):
                    result = adapter_protocol.discover_adapter(
                        Path(directory), skill_name, {1}
                    )

                    self.assertEqual(
                        result,
                        {
                            "status": "invalid",
                            "errors": [
                                "skill name must match "
                                "[a-z0-9]+(?:-[a-z0-9]+)*"
                            ],
                        },
                    )

    def test_valid_adapter_is_discovered_at_exact_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.write_adapter(root, VALID_ADAPTER)

            result = adapter_protocol.discover_adapter(root, "wrap-session", {1})

        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["path"], str(path))
        self.assertEqual(result["metadata"]["contract"], 1)
        self.assertEqual(result["body"], "Use the repository closeout policy.\n")

    def test_wrong_schema_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_adapter(
                root, VALID_ADAPTER.replace("superpowers-adapter/v1", "other/v1")
            )

            result = adapter_protocol.discover_adapter(root, "wrap-session", {1})

        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("schema" in error for error in result["errors"]))

    def test_wrong_extends_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_adapter(
                root, VALID_ADAPTER.replace("extends: wrap-session", "extends: qa")
            )

            result = adapter_protocol.discover_adapter(root, "wrap-session", {1})

        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("extends" in error for error in result["errors"]))

    def test_unsupported_contract_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_adapter(root, VALID_ADAPTER.replace("contract: 1", "contract: 2"))

            result = adapter_protocol.discover_adapter(root, "wrap-session", {1})

        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("contract" in error for error in result["errors"]))

    def test_missing_frontmatter_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_adapter(root, "No frontmatter.\n")

            result = adapter_protocol.discover_adapter(root, "wrap-session", {1})

        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("frontmatter" in error for error in result["errors"]))

    def test_dangling_adapter_symlink_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter_path = (
                root / ".agents" / "superpowers" / "wrap-session" / "adapter.md"
            )
            adapter_path.parent.mkdir(parents=True)
            adapter_path.symlink_to(root / "missing-adapter.md")

            result = adapter_protocol.discover_adapter(root, "wrap-session", {1})

        self.assertEqual(result["status"], "invalid")
        self.assertEqual(
            result["errors"],
            ["adapter entry cannot be read: symlink target does not exist"],
        )

    def test_adapter_file_symlink_escape_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter_path = (
                root / ".agents" / "superpowers" / "wrap-session" / "adapter.md"
            )
            adapter_path.parent.mkdir(parents=True)
            with tempfile.TemporaryDirectory() as external_directory:
                external_adapter = Path(external_directory) / "adapter.md"
                external_adapter.write_text(VALID_ADAPTER)
                adapter_path.symlink_to(external_adapter)

                result = adapter_protocol.discover_adapter(
                    root, "wrap-session", {1}
                )

        self.assertEqual(result["status"], "invalid")
        self.assertEqual(
            result["errors"],
            ["adapter entry resolves outside adapter directory"],
        )

    def test_adapter_directory_symlink_escape_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapters_root = root / ".agents" / "superpowers"
            adapters_root.mkdir(parents=True)
            with tempfile.TemporaryDirectory() as external_directory:
                external_adapter_directory = Path(external_directory)
                (external_adapter_directory / "adapter.md").write_text(VALID_ADAPTER)
                (adapters_root / "wrap-session").symlink_to(
                    external_adapter_directory, target_is_directory=True
                )

                result = adapter_protocol.discover_adapter(
                    root, "wrap-session", {1}
                )

        self.assertEqual(result["status"], "invalid")
        self.assertEqual(
            result["errors"],
            ["adapter directory resolves outside project root"],
        )


class ResolveAdapterResourceTests(ProtocolTestCase):
    def test_resolves_existing_resource_inside_adapter_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter_path = Path(directory) / "adapter.md"
            adapter_path.write_text(VALID_ADAPTER)
            resource = Path(directory) / "references" / "policy.md"
            resource.parent.mkdir()
            resource.write_text("Policy")

            resolved = adapter_protocol.resolve_adapter_resource(
                adapter_path, "references/policy.md"
            )

        self.assertEqual(resolved, resource.resolve())

    def test_rejects_absolute_and_parent_traversal_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter_path = Path(directory) / "adapter.md"
            adapter_path.write_text(VALID_ADAPTER)

            for resource_path in ("/tmp/policy.md", "../policy.md"):
                with self.subTest(resource_path=resource_path):
                    with self.assertRaisesRegex(ValueError, "outside|absolute"):
                        adapter_protocol.resolve_adapter_resource(
                            adapter_path, resource_path
                        )

    def test_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter_dir = root / "adapter"
            adapter_dir.mkdir()
            adapter_path = adapter_dir / "adapter.md"
            adapter_path.write_text(VALID_ADAPTER)
            outside = root / "outside.md"
            outside.write_text("Outside")
            (adapter_dir / "escape.md").symlink_to(outside)

            with self.assertRaisesRegex(ValueError, "outside"):
                adapter_protocol.resolve_adapter_resource(adapter_path, "escape.md")


class ValidateObservationTests(ProtocolTestCase):
    def test_valid_observation_has_no_errors(self):
        self.assertEqual(adapter_protocol.validate_observation(VALID_OBSERVATION), [])

    def test_reports_all_missing_nested_fields(self):
        metadata = {
            "schema": "superpowers-observation/v1",
            "runtime": {},
            "skills": {"global": {}, "adapter": {}},
            "observation": {},
            "candidate": {},
        }

        errors = adapter_protocol.validate_observation(metadata)

        self.assertGreaterEqual(len(errors), 20)
        self.assertTrue(any("runtime.provider" in error for error in errors))
        self.assertTrue(any("skills.global.contract" in error for error in errors))
        self.assertTrue(any("skills.adapter.path" in error for error in errors))
        self.assertTrue(any("observation.evidence" in error for error in errors))
        self.assertTrue(any("candidate.status" in error for error in errors))

    def test_reports_wrong_nested_types_without_stopping(self):
        metadata = dict(VALID_OBSERVATION)
        metadata.update(
            {
                "runtime": "openai",
                "skills": None,
                "observation": [],
                "candidate": 1,
            }
        )

        errors = adapter_protocol.validate_observation(metadata)

        self.assertEqual(len(errors), 4)
        self.assertTrue(all("mapping" in error for error in errors))

    def test_enforces_enums_and_accepts_unknown(self):
        for field, invalid in (
            (("observation", "diagnosis"), "guess"),
            (("candidate", "scope"), "global"),
            (("candidate", "target"), "adapter"),
        ):
            with self.subTest(field=field):
                metadata = json.loads(json.dumps(VALID_OBSERVATION))
                metadata[field[0]][field[1]] = invalid
                errors = adapter_protocol.validate_observation(metadata)
                self.assertEqual(len(errors), 1)
                self.assertIn(".".join(field), errors[0])

                metadata[field[0]][field[1]] = "unknown"
                self.assertEqual(adapter_protocol.validate_observation(metadata), [])

    def test_rejects_observation_contract_other_than_one(self):
        metadata = json.loads(json.dumps(VALID_OBSERVATION))
        metadata["skills"]["global"]["contract"] = 2

        errors = adapter_protocol.validate_observation(metadata)

        self.assertEqual(errors, ["skills.global.contract must be 1"])


class ClassifyObservationTests(ProtocolTestCase):
    def test_classify_returns_current_for_valid_v1(self):
        metadata = _valid_observation_metadata()
        self.assertEqual(
            adapter_protocol.classify_observation(metadata), ("current", [])
        )

    def test_classify_returns_invalid_with_errors_for_malformed_v1(self):
        metadata = _valid_observation_metadata()
        del metadata["observation"]["expected"]
        status, errors = adapter_protocol.classify_observation(metadata)
        self.assertEqual(status, "invalid")
        self.assertIn("observation.expected is required", errors)

    def test_classify_returns_invalid_for_missing_schema(self):
        metadata = _valid_observation_metadata()
        del metadata["schema"]
        status, errors = adapter_protocol.classify_observation(metadata)
        self.assertEqual(status, "invalid")
        self.assertEqual(errors, ["schema is required"])

    def test_classify_returns_unknown_schema_for_unregistered_version(self):
        metadata = _valid_observation_metadata()
        metadata["schema"] = "superpowers-observation/v9"
        status, errors = adapter_protocol.classify_observation(metadata)
        self.assertEqual(status, "unknown-schema")
        self.assertEqual(errors, ["unknown observation schema superpowers-observation/v9"])

    def test_classify_returns_outdated_for_registered_older_version(self):
        metadata = _valid_observation_metadata()
        metadata["schema"] = "superpowers-observation/v0-test"
        adapter_protocol.OBSERVATION_VALIDATORS["superpowers-observation/v0-test"] = (
            lambda _metadata: []
        )
        self.addCleanup(
            adapter_protocol.OBSERVATION_VALIDATORS.pop,
            "superpowers-observation/v0-test",
            None,
        )
        self.assertEqual(
            adapter_protocol.classify_observation(metadata), ("outdated", [])
        )

    def test_validate_observation_message_unchanged_for_unknown_schema(self):
        metadata = _valid_observation_metadata()
        metadata["schema"] = "superpowers-observation/v9"
        self.assertEqual(
            adapter_protocol.validate_observation(metadata),
            ["schema must be superpowers-observation/v1"],
        )

    def test_dirty_flag_is_optional_and_absent_is_valid(self):
        metadata = _valid_observation_metadata()
        self.assertNotIn("dirty", metadata["skills"]["global"])
        self.assertEqual(adapter_protocol.validate_observation(metadata), [])

    def test_dirty_flag_accepts_boolean(self):
        metadata = _valid_observation_metadata()
        metadata["skills"]["global"]["dirty"] = True
        self.assertEqual(adapter_protocol.validate_observation(metadata), [])

    def test_dirty_flag_rejects_non_boolean(self):
        metadata = _valid_observation_metadata()
        metadata["skills"]["global"]["dirty"] = "yes"
        self.assertEqual(
            adapter_protocol.validate_observation(metadata),
            ["skills.global.dirty must be a boolean"],
        )

    _OPTIONAL_STRING_CASES = (
        ("runtime", "os"),
        ("runtime", "workspace"),
        ("runtime", "session-id"),
        ("observation", "observed"),
    )

    def test_optional_string_fields_absent_is_valid(self):
        metadata = _valid_observation_metadata()
        for block, key in self._OPTIONAL_STRING_CASES:
            self.assertNotIn(key, metadata[block])
        self.assertEqual(adapter_protocol.validate_observation(metadata), [])

    def test_optional_string_fields_accept_non_empty_string(self):
        values = {
            ("runtime", "os"): "darwin",
            ("runtime", "workspace"): "production",
            ("runtime", "session-id"): "abc123",
            ("observation", "observed"): "2026-07-25",
        }
        for block, key in self._OPTIONAL_STRING_CASES:
            metadata = _valid_observation_metadata()
            metadata[block][key] = values[(block, key)]
            self.assertEqual(adapter_protocol.validate_observation(metadata), [])

    def test_optional_string_fields_reject_wrong_type(self):
        for block, key in self._OPTIONAL_STRING_CASES:
            metadata = _valid_observation_metadata()
            metadata[block][key] = 7
            self.assertEqual(
                adapter_protocol.validate_observation(metadata),
                [f"{block}.{key} must be a non-empty string"],
            )

    def test_optional_string_fields_reject_empty_string(self):
        for block, key in self._OPTIONAL_STRING_CASES:
            metadata = _valid_observation_metadata()
            metadata[block][key] = ""
            self.assertEqual(
                adapter_protocol.validate_observation(metadata),
                [f"{block}.{key} must be a non-empty string"],
            )

    # Pinned to their values from before schema-version dispatch (c194c6d):
    # validate_observation must keep returning the combined schema + field
    # diagnostics for a non-current note, not just the schema line.

    def test_validate_observation_reports_schema_only_for_missing_schema(self):
        metadata = _valid_observation_metadata()
        del metadata["schema"]
        self.assertEqual(
            adapter_protocol.validate_observation(metadata),
            ["schema must be superpowers-observation/v1"],
        )

    def test_validate_observation_reports_schema_and_field_errors_together(self):
        metadata = _valid_observation_metadata()
        metadata["schema"] = "superpowers-observation/v2"
        del metadata["observation"]["expected"]
        self.assertEqual(
            adapter_protocol.validate_observation(metadata),
            [
                "schema must be superpowers-observation/v1",
                "observation.expected is required",
            ],
        )

    def test_validate_observation_reports_schema_only_for_non_string_schema(self):
        metadata = _valid_observation_metadata()
        metadata["schema"] = 1
        self.assertEqual(
            adapter_protocol.validate_observation(metadata),
            ["schema must be superpowers-observation/v1"],
        )


class CliTests(ProtocolTestCase):
    def test_discover_cli_emits_json_and_uses_protocol_exit_codes(self):
        script = SCRIPTS_DIR / "adapter_protocol.py"
        with tempfile.TemporaryDirectory() as directory:
            absent = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "discover",
                    directory,
                    "wrap-session",
                    "--supported-contract",
                    "1",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            root = Path(directory)
            path = (
                root / ".agents" / "superpowers" / "wrap-session" / "adapter.md"
            )
            path.parent.mkdir(parents=True)
            path.write_text(VALID_ADAPTER.replace("contract: 1", "contract: 2"))
            invalid = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "discover",
                    directory,
                    "wrap-session",
                    "--supported-contract",
                    "1",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(absent.returncode, 0)
        self.assertEqual(json.loads(absent.stdout)["status"], "absent")
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(json.loads(invalid.stdout)["status"], "invalid")

    def test_validate_observation_cli_reads_frontmatter_file(self):
        script = SCRIPTS_DIR / "adapter_protocol.py"
        with tempfile.TemporaryDirectory() as directory:
            observation_path = Path(directory) / "observation.md"
            observation_path.write_text(
                "---\n"
                "schema: superpowers-observation/v1\n"
                "runtime:\n"
                "  provider: openai\n"
                "---\n"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "validate-observation",
                    str(observation_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["status"], "invalid")
        self.assertTrue(any("runtime.model" in error for error in payload["errors"]))


if __name__ == "__main__":
    unittest.main()
