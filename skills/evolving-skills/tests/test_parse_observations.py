import unittest
import os
import shutil
import tempfile
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# Add scripts folder to sys.path for importing parse_observations
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))
import parse_observations


EVOLVING_SKILL_DIR = Path(__file__).resolve().parents[1]
SKILLS_DIR = EVOLVING_SKILL_DIR.parent


V1_OBSERVATION = """---
schema: superpowers-observation/v1
runtime:
  provider: openai
  model: gpt-5.6-sol
  reasoning-effort: high
  harness: codex-app
  harness-version: unknown
  interface: desktop
skills:
  global:
    name: wrap-session
    contract: 1
    plugin-version: unknown
    git-commit: unknown
  adapter:
    path: unknown
    version: unknown
    git-commit: unknown
observation:
  phase: durable-context
  expected: Update the existing task record.
  actual: Created a duplicate handoff document.
  evidence: Two handoff files were present.
  diagnosis: global-skill
candidate:
  scope: potentially-global
  target: skill
  status: observed
---
Observation body.
"""

class TestParseObservations(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.obs_dir = os.path.join(self.test_dir, "observations")
        self.archive_dir = os.path.join(self.obs_dir, "archive")
        os.makedirs(self.obs_dir, exist_ok=True)
        
        # Create a sample raw observation file
        self.sample_file = os.path.join(self.obs_dir, "2026-07-24-1200-systematic-debugging-failed-during-hypothesis.md")
        sample_content = """---
timestamp: 2026-07-24-1200
skill: systematic-debugging
phase: hypothesis
context_slug: test-failure
status: pending_distillation
---

# Superpower Observation Note

- **Observed Failure / Friction**: Skipped reading log before hypothesizing fix.
- **Verbatim Rationalization / Fallback**: "I'm 99% sure I know what failed."
- **Environment / Project Context**: Test suite error in python service.
- **Proposed Universal Improvement**: Add Red Flag for "I know what failed without looking".
"""
        with open(self.sample_file, "w", encoding="utf-8") as f:
            f.write(sample_content)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_list_observations(self):
        observations = parse_observations.list_observations(self.obs_dir)
        self.assertEqual(len(observations), 1)
        obs = observations[0]
        self.assertEqual(obs["skill"], "systematic-debugging")
        self.assertEqual(obs["phase"], "hypothesis")
        self.assertEqual(obs["status"], "pending_distillation")
        self.assertIn("Skipped reading log", obs["content"])

    def test_archive_observation(self):
        archived_path = parse_observations.archive_observation(self.sample_file, self.archive_dir)
        self.assertFalse(os.path.exists(self.sample_file))
        self.assertTrue(os.path.exists(archived_path))
        self.assertTrue(archived_path.startswith(self.archive_dir))


class TestRepositoryObservationStore(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_observation_root_is_repository_local(self):
        self.assertEqual(
            parse_observations.observation_root(self.project_root),
            self.project_root.resolve() / ".superpowers" / "observations",
        )

    def test_ensure_observation_store_creates_lifecycle_directories_and_ignore(self):
        store = parse_observations.ensure_observation_store(self.project_root)

        self.assertEqual(
            store["root"],
            self.project_root.resolve() / ".superpowers" / "observations",
        )
        for name in ("pending", "proposed", "archived"):
            self.assertTrue(store[name].is_dir())
        self.assertEqual((store["root"] / ".gitignore").read_text(), "*\n")

    def test_ensure_observation_store_rejects_symlinked_superpowers_directory(self):
        with tempfile.TemporaryDirectory() as external_directory:
            (self.project_root / ".superpowers").symlink_to(
                external_directory, target_is_directory=True
            )

            with self.assertRaisesRegex(ValueError, "symlinked .superpowers"):
                parse_observations.ensure_observation_store(self.project_root)

            self.assertFalse(
                (Path(external_directory) / "observations").exists()
            )

    def test_ensure_observation_store_rejects_symlinked_observation_root(self):
        with tempfile.TemporaryDirectory() as external_directory:
            (self.project_root / ".superpowers").mkdir()
            (self.project_root / ".superpowers" / "observations").symlink_to(
                external_directory, target_is_directory=True
            )

            with self.assertRaisesRegex(ValueError, "symlinked observations"):
                parse_observations.ensure_observation_store(self.project_root)

            self.assertFalse((Path(external_directory) / "pending").exists())

    def test_ensure_observation_store_rejects_symlinked_lifecycle_directories(self):
        for lifecycle_name in ("pending", "proposed", "archived"):
            with self.subTest(lifecycle_name=lifecycle_name):
                with tempfile.TemporaryDirectory() as project_directory:
                    project_root = Path(project_directory)
                    store = parse_observations.ensure_observation_store(project_root)
                    store[lifecycle_name].rmdir()
                    with tempfile.TemporaryDirectory() as external_directory:
                        store[lifecycle_name].symlink_to(
                            external_directory, target_is_directory=True
                        )

                        with self.assertRaisesRegex(
                            ValueError, f"symlinked {lifecycle_name}"
                        ):
                            parse_observations.ensure_observation_store(project_root)

    def test_cli_defaults_project_root_to_current_directory(self):
        output = StringIO()
        with patch.object(Path, "cwd", return_value=self.project_root):
            with redirect_stdout(output):
                parse_observations.main(["--init"])

        created = json.loads(output.getvalue())
        self.assertEqual(created["root"], str(parse_observations.observation_root(self.project_root)))

    def test_repository_listing_without_initialized_store_is_empty(self):
        observations = parse_observations.list_observations(
            parse_observations.observation_root(self.project_root),
            repository_local=True,
        )

        self.assertEqual(observations, [])

    def test_repository_listing_reads_only_valid_pending_v1_observations(self):
        store = parse_observations.ensure_observation_store(self.project_root)
        pending = store["pending"] / "pending.md"
        pending.write_text(V1_OBSERVATION)
        (store["proposed"] / "proposal.md").write_text(V1_OBSERVATION)
        (store["archived"] / "old.md").write_text(V1_OBSERVATION)
        (store["pending"] / "invalid.md").write_text("---\nschema: invalid\n---\nBad")

        with redirect_stderr(StringIO()):
            observations = parse_observations.list_observations(store["root"])

        self.assertEqual([observation["filename"] for observation in observations], ["pending.md"])
        observation = observations[0]
        self.assertEqual(observation["runtime"]["provider"], "openai")
        self.assertEqual(observation["skills"]["global"]["name"], "wrap-session")
        self.assertEqual(observation["observation"]["phase"], "durable-context")
        self.assertEqual(observation["candidate"]["scope"], "potentially-global")

        with redirect_stderr(StringIO()):
            direct_pending = parse_observations.list_observations(store["pending"])
        self.assertEqual([item["filename"] for item in direct_pending], ["pending.md"])

    def test_repository_listing_rejects_symlinked_pending_directory_escape(self):
        store = parse_observations.ensure_observation_store(self.project_root)
        store["pending"].rmdir()
        with tempfile.TemporaryDirectory() as external_directory:
            external_pending = Path(external_directory)
            (external_pending / "outside.md").write_text(V1_OBSERVATION)
            store["pending"].symlink_to(
                external_pending, target_is_directory=True
            )

            with self.assertRaisesRegex(ValueError, "symlinked pending"):
                parse_observations.list_observations(store["root"])

    def test_default_listing_rejects_symlinked_canonical_observation_root(self):
        (self.project_root / ".superpowers").mkdir()
        with tempfile.TemporaryDirectory() as external_directory:
            external_root = Path(external_directory)
            (external_root / "outside.md").write_text(
                "---\nskill: outside\n---\nExternal legacy note."
            )
            local_root = self.project_root / ".superpowers" / "observations"
            local_root.symlink_to(external_root, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "symlinked observations"):
                parse_observations.list_observations(
                    parse_observations.observation_root(self.project_root)
                )

    def test_default_listing_rejects_symlinked_canonical_pending_path(self):
        local_root = self.project_root / ".superpowers" / "observations"
        local_root.mkdir(parents=True)
        with tempfile.TemporaryDirectory() as external_directory:
            external_pending = Path(external_directory)
            (external_pending / "outside.md").write_text(
                "---\nskill: outside\n---\nExternal legacy note."
            )
            local_pending = local_root / "pending"
            local_pending.symlink_to(external_pending, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "symlinked pending"):
                parse_observations.list_observations(local_pending)

    def test_repository_listing_rejects_symlinked_pending_note_escape(self):
        store = parse_observations.ensure_observation_store(self.project_root)
        with tempfile.TemporaryDirectory() as external_directory:
            external_note = Path(external_directory) / "outside.md"
            external_note.write_text(V1_OBSERVATION)
            (store["pending"] / "outside.md").symlink_to(external_note)
            errors = StringIO()

            with redirect_stderr(errors):
                observations = parse_observations.list_observations(store["root"])

        self.assertEqual(observations, [])
        self.assertIn("symlinked observation note", errors.getvalue())

    def test_repository_archival_moves_pending_note_to_archived(self):
        store = parse_observations.ensure_observation_store(self.project_root)
        pending = store["pending"] / "note.md"
        pending.write_text(V1_OBSERVATION)

        archived = parse_observations.archive_observation(pending, store["archived"])

        self.assertFalse(pending.exists())
        self.assertEqual(Path(archived), store["archived"] / "note.md")
        self.assertTrue(Path(archived).is_file())

    def test_repository_archival_rejects_existing_destination(self):
        store = parse_observations.ensure_observation_store(self.project_root)
        pending = store["pending"] / "note.md"
        pending.write_text(V1_OBSERVATION)
        destination = store["archived"] / "note.md"
        destination.write_text("Existing archive note.")

        with self.assertRaises(FileExistsError):
            parse_observations.archive_observation(pending, store["archived"])

        self.assertTrue(pending.exists())
        self.assertEqual(destination.read_text(), "Existing archive note.")

    def test_repository_archival_rejects_source_outside_pending(self):
        store = parse_observations.ensure_observation_store(self.project_root)
        proposal = store["proposed"] / "proposal.md"
        proposal.write_text(V1_OBSERVATION)

        with self.assertRaises(ValueError):
            parse_observations.archive_observation(proposal, store["archived"])

        self.assertTrue(proposal.exists())

    def test_repository_archival_rejects_symlinked_pending_note_escape(self):
        store = parse_observations.ensure_observation_store(self.project_root)
        with tempfile.TemporaryDirectory() as external_directory:
            external_note = Path(external_directory) / "outside.md"
            external_note.write_text(V1_OBSERVATION)
            pending_link = store["pending"] / "outside.md"
            pending_link.symlink_to(external_note)

            with self.assertRaisesRegex(ValueError, "symlinked observation note"):
                parse_observations.archive_observation(
                    pending_link, store["archived"]
                )

            self.assertTrue(external_note.exists())
            self.assertFalse((store["archived"] / "outside.md").exists())

    def test_repository_archival_rejects_archived_directory_symlink_escape(self):
        store = parse_observations.ensure_observation_store(self.project_root)
        pending = store["pending"] / "note.md"
        pending.write_text(V1_OBSERVATION)
        external_archive = self.project_root / "external-archive"
        external_archive.mkdir()
        store["archived"].rmdir()
        store["archived"].symlink_to(external_archive, target_is_directory=True)

        with self.assertRaises(ValueError):
            parse_observations.archive_observation(pending, store["archived"])

        self.assertTrue(pending.exists())
        self.assertFalse((external_archive / "note.md").exists())

    def test_repository_archival_rejects_archived_directory_symlink_to_proposed(self):
        store = parse_observations.ensure_observation_store(self.project_root)
        pending = store["pending"] / "note.md"
        pending.write_text(V1_OBSERVATION)
        store["archived"].rmdir()
        store["archived"].symlink_to(store["proposed"], target_is_directory=True)

        with self.assertRaises(ValueError):
            parse_observations.archive_observation(pending, store["archived"])

        self.assertTrue(pending.exists())
        self.assertFalse((store["proposed"] / "note.md").exists())

    def test_explicit_obs_dir_keeps_legacy_flat_output(self):
        legacy_dir = self.project_root / "legacy-observations"
        legacy_dir.mkdir()
        (legacy_dir / "legacy.md").write_text(
            "---\ntimestamp: 2026-07-29\nskill: wrap-session\nphase: closeout\n---\nLegacy body."
        )

        output = StringIO()
        with redirect_stdout(output):
            parse_observations.main(["--obs-dir", str(legacy_dir), "--list"])

        observations = json.loads(output.getvalue())
        self.assertEqual(observations[0]["skill"], "wrap-session")
        self.assertEqual(observations[0]["phase"], "closeout")
        self.assertEqual(observations[0]["frontmatter"]["timestamp"], "2026-07-29")
        self.assertNotIn("runtime", observations[0])


class TestInstalledSkillPortabilityContract(unittest.TestCase):
    def test_commands_resolve_installed_helpers_outside_the_active_project(self):
        evolving_skill = (EVOLVING_SKILL_DIR / "SKILL.md").read_text()
        using_skill = (SKILLS_DIR / "using-superpowers" / "SKILL.md").read_text()
        protocol_reference = (
            EVOLVING_SKILL_DIR / "references" / "local-adapter-protocol.md"
        ).read_text()
        combined = "\n".join((evolving_skill, using_skill, protocol_reference))

        self.assertIn(
            "directory containing this loaded `evolving-skills/SKILL.md`",
            evolving_skill,
        )
        self.assertGreaterEqual(
            evolving_skill.count(
                'python3 "$SKILL_DIR/scripts/parse_observations.py"'
            ),
            2,
        )
        self.assertIn('--project-root "$PROJECT_ROOT" --list', evolving_skill)
        self.assertIn('--project-root "$PROJECT_ROOT" --archive', evolving_skill)
        self.assertIn("installed `superpowers:evolving-skills` skill", using_skill)
        self.assertIn(
            "reference shipped with that installed skill",
            using_skill,
        )
        self.assertNotIn("$PROJECT_ROOT/skills/evolving-skills", combined)
        self.assertNotIn("python3 skills/evolving-skills/scripts", combined)

    def test_protocol_reference_has_standard_frontmatter(self):
        protocol_reference = (
            EVOLVING_SKILL_DIR / "references" / "local-adapter-protocol.md"
        ).read_text()

        self.assertTrue(
            protocol_reference.startswith(
                "---\n"
                "title: Local Adapter and Skill Evolution Protocol\n"
                "---\n"
            )
        )


if __name__ == "__main__":
    unittest.main()
