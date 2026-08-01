"""Tests for deterministic observation generation."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import adapter_protocol
import new_observation


class RenderFrontmatterTest(unittest.TestCase):
    def test_round_trips_through_the_project_parser(self):
        metadata = {
            "schema": adapter_protocol.OBSERVATION_SCHEMA,
            "observation": {"expected": "a value with: a colon and 'quotes'"},
            "skills": {"global": {"dirty": True, "contract": 1}},
        }
        text = new_observation.render_frontmatter(metadata)
        parsed, body = adapter_protocol.parse_frontmatter(text + "body\n")
        self.assertEqual(
            parsed["observation"]["expected"], "a value with: a colon and 'quotes'"
        )
        self.assertIs(parsed["skills"]["global"]["dirty"], True)
        self.assertEqual(parsed["skills"]["global"]["contract"], 1)
        self.assertEqual(body.strip(), "body")

    def test_collapses_newlines_into_single_line_scalars(self):
        metadata = {"observation": {"evidence": "line one\nline two"}}
        text = new_observation.render_frontmatter(metadata)
        # A line-count assertion here is vacuous: repr() already keeps an
        # embedded "\n" on one physical line even without the " ".join(...
        # .split()) collapse, so a bare line count would pass either way.
        # Assert the collapsed content directly instead.
        self.assertIn("evidence: 'line one line two'", text)


class BuildMetadataTest(unittest.TestCase):
    def test_produces_metadata_that_validates(self):
        metadata = new_observation.build_metadata(
            skill="evolving-skills",
            phase="verification",
            expected="Evidence is recorded without changing global skills.",
            actual="A reusable friction pattern required an explicit local note.",
            evidence="Sanitized command result.",
            diagnosis="uncertain",
            scope="potentially-global",
            target="reference",
            runtime={"model": "test-model"},
            provenance={"git-commit": "abc1234", "dirty": True, "plugin-version": "0"},
            adapter=None,
        )
        self.assertEqual(adapter_protocol.validate_observation(metadata), [])
        self.assertIs(metadata["skills"]["global"]["dirty"], True)
        self.assertEqual(metadata["runtime"]["model"], "test-model")
        self.assertEqual(metadata["runtime"]["harness"], "unknown")
        self.assertEqual(metadata["skills"]["adapter"]["path"], "unknown")


class WriteObservationTest(unittest.TestCase):
    def _metadata(self):
        return new_observation.build_metadata(
            skill="evolving-skills",
            phase="verification",
            expected="expected",
            actual="actual",
            evidence="evidence",
            diagnosis="uncertain",
            scope="local",
            target="none",
            runtime={},
            provenance={},
            adapter=None,
        )

    def test_writes_a_listable_note_into_pending(self):
        with tempfile.TemporaryDirectory() as root:
            path = new_observation.write_observation(
                Path(root), self._metadata(), "Sanitized body."
            )
            self.assertEqual(path.parent.name, "pending")
            import parse_observations

            listed = parse_observations.list_observations(
                parse_observations.observation_root(Path(root))
            )
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["skill"], "evolving-skills")

    def test_archive_now_lands_in_archived_and_leaves_pending_empty(self):
        with tempfile.TemporaryDirectory() as root:
            path = new_observation.write_observation(
                Path(root), self._metadata(), "Sanitized body.", archive_now=True
            )
            self.assertEqual(path.parent.name, "archived")
            pending = Path(root) / ".superpowers" / "observations" / "pending"
            self.assertEqual(list(pending.iterdir()), [])

    def test_refuses_to_write_invalid_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            metadata = self._metadata()
            del metadata["observation"]["expected"]
            with self.assertRaises(ValueError):
                new_observation.write_observation(Path(root), metadata, "body")
            pending = Path(root) / ".superpowers" / "observations" / "pending"
            self.assertFalse(pending.exists() and list(pending.iterdir()))

    def test_refuses_to_write_through_a_dangling_pending_symlink(self):
        with tempfile.TemporaryDirectory() as root:
            metadata = self._metadata()
            now = "2026-08-01-000000"
            store = new_observation.ensure_observation_store(Path(root))
            filename = new_observation._filename(metadata, now)
            outside_target = Path(root) / "outside.md"
            (store["pending"] / filename).symlink_to(outside_target)

            with self.assertRaises(ValueError):
                new_observation.write_observation(
                    Path(root), metadata, "Sanitized body.", now=now
                )

            self.assertFalse(outside_target.exists())


if __name__ == "__main__":
    unittest.main()
