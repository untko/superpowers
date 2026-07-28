#!/usr/bin/env python3
"""Validate repository-local skill adapters and evolution observations."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re


ADAPTER_SCHEMA = "superpowers-adapter/v1"
OBSERVATION_SCHEMA = "superpowers-observation/v1"
_KEY = re.compile(r"[A-Za-z0-9_-]+")
_INTEGER = re.compile(r"-?[0-9]+")


def _parse_scalar(value: str, line_number: int) -> object:
    if value.startswith(("[", "{")):
        raise ValueError(f"line {line_number}: lists and inline mappings are unsupported")
    if value.startswith(("'", '"')):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError) as error:
            raise ValueError(
                f"line {line_number}: malformed quoted scalar"
            ) from error
        if not isinstance(parsed, str):
            raise ValueError(f"line {line_number}: quoted scalar must be a string")
        return parsed
    if value in {"true", "false"}:
        return value == "true"
    if value == "null":
        return None
    if _INTEGER.fullmatch(value):
        return int(value)
    return value


def _parse_mapping(lines: list[str]) -> dict[str, object]:
    root: dict[str, object] = {}
    stack: list[dict[str, object]] = [root]
    previous_level = 0
    pending_child: dict[str, object] | None = None
    saw_content = False

    for line_number, line in enumerate(lines, start=2):
        if "\t" in line:
            raise ValueError(f"line {line_number}: tabs are invalid indentation")
        if not line.strip():
            continue

        spaces = len(line) - len(line.lstrip(" "))
        if spaces % 2:
            raise ValueError(
                f"line {line_number}: indentation must use two-space increments"
            )
        level = spaces // 2

        if not saw_content and level:
            raise ValueError(f"line {line_number}: indentation must start at zero")
        if saw_content and level > previous_level + 1:
            raise ValueError(f"line {line_number}: indentation jump")
        if saw_content and level == previous_level + 1:
            if pending_child is None:
                raise ValueError(
                    f"line {line_number}: indentation below a scalar is invalid"
                )
            stack.append(pending_child)
        elif level <= previous_level:
            del stack[level + 1 :]

        text = line[spaces:]
        if text.startswith("-"):
            raise ValueError(f"line {line_number}: lists are unsupported")
        if ":" not in text:
            raise ValueError(f"line {line_number}: expected a mapping entry")
        key, raw_value = text.split(":", 1)
        if not _KEY.fullmatch(key):
            raise ValueError(f"line {line_number}: invalid mapping key")

        mapping = stack[level]
        if key in mapping:
            raise ValueError(f"line {line_number}: duplicate key {key!r}")

        value = raw_value.strip()
        if value:
            mapping[key] = _parse_scalar(value, line_number)
            pending_child = None
        else:
            child: dict[str, object] = {}
            mapping[key] = child
            pending_child = child

        previous_level = level
        saw_content = True

    return root


def parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
    """Parse constrained YAML frontmatter and return its mapping and body."""
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError("missing opening frontmatter delimiter")

    closing_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            closing_index = index
            break
    if closing_index is None:
        raise ValueError("missing closing frontmatter delimiter")

    metadata_lines = [line.rstrip("\r\n") for line in lines[1:closing_index]]
    metadata = _parse_mapping(metadata_lines)
    return metadata, "".join(lines[closing_index + 1 :])


def discover_adapter(
    project_root: Path,
    skill_name: str,
    supported_contracts: set[int],
) -> dict[str, object]:
    """Discover and validate one adapter at the protocol's exact location."""
    if not skill_name or Path(skill_name).name != skill_name:
        return {
            "status": "invalid",
            "errors": ["skill name must be one path segment"],
        }

    adapter_path = (
        Path(project_root)
        / ".agents"
        / "superpowers"
        / skill_name
        / "adapter.md"
    )
    try:
        adapter_path.lstat()
    except FileNotFoundError:
        return {"status": "absent", "path": str(adapter_path)}
    except OSError as error:
        return {
            "status": "invalid",
            "path": str(adapter_path),
            "errors": [f"adapter entry cannot be inspected: {error}"],
        }

    if adapter_path.is_symlink():
        try:
            adapter_path.stat()
        except FileNotFoundError:
            return {
                "status": "invalid",
                "path": str(adapter_path),
                "errors": [
                    "adapter entry cannot be read: symlink target does not exist"
                ],
            }
        except OSError as error:
            return {
                "status": "invalid",
                "path": str(adapter_path),
                "errors": [f"adapter entry cannot be read: {error}"],
            }

    try:
        metadata, body = parse_frontmatter(adapter_path.read_text())
    except FileNotFoundError:
        return {
            "status": "invalid",
            "path": str(adapter_path),
            "errors": ["adapter entry cannot be read: entry disappeared"],
        }
    except (OSError, UnicodeError) as error:
        return {
            "status": "invalid",
            "path": str(adapter_path),
            "errors": [f"adapter entry cannot be read: {error}"],
        }
    except ValueError as error:
        return {
            "status": "invalid",
            "path": str(adapter_path),
            "errors": [str(error)],
        }

    errors: list[str] = []
    if metadata.get("schema") != ADAPTER_SCHEMA:
        errors.append(f"schema must be {ADAPTER_SCHEMA}")
    if metadata.get("extends") != skill_name:
        errors.append(f"extends must be {skill_name}")

    contract = metadata.get("contract")
    if type(contract) is not int:
        errors.append("contract must be an integer")
    elif contract not in supported_contracts:
        errors.append(f"contract {contract} is unsupported")

    adapter_version = metadata.get("adapter-version")
    if type(adapter_version) is not int or adapter_version < 1:
        errors.append("adapter-version must be a positive integer")

    if errors:
        return {
            "status": "invalid",
            "path": str(adapter_path),
            "errors": errors,
        }
    return {
        "status": "valid",
        "path": str(adapter_path),
        "metadata": metadata,
        "body": body,
    }


def resolve_adapter_resource(adapter_path: Path, relative_path: str) -> Path:
    """Resolve an existing resource while containing it inside the adapter."""
    requested = Path(relative_path)
    if requested.is_absolute():
        raise ValueError("absolute adapter resource paths are invalid")
    if ".." in requested.parts:
        raise ValueError("adapter resource path resolves outside adapter directory")

    adapter_directory = Path(adapter_path).parent.resolve(strict=True)
    try:
        resolved = (adapter_directory / requested).resolve(strict=True)
    except OSError as error:
        raise ValueError(f"adapter resource does not exist: {relative_path}") from error

    try:
        resolved.relative_to(adapter_directory)
    except ValueError as error:
        raise ValueError(
            "adapter resource resolves outside adapter directory"
        ) from error
    if not resolved.is_file():
        raise ValueError("adapter resource must be a file")
    return resolved


_STRING_FIELDS = (
    "runtime.provider",
    "runtime.model",
    "runtime.reasoning-effort",
    "runtime.harness",
    "runtime.harness-version",
    "runtime.interface",
    "skills.global.name",
    "skills.global.plugin-version",
    "skills.global.git-commit",
    "skills.adapter.path",
    "skills.adapter.git-commit",
    "observation.phase",
    "observation.expected",
    "observation.actual",
    "observation.evidence",
    "observation.diagnosis",
    "candidate.scope",
    "candidate.target",
    "candidate.status",
)

_MAPPING_FIELDS = (
    "runtime",
    "skills",
    "skills.global",
    "skills.adapter",
    "observation",
    "candidate",
)

_ENUMS = {
    "observation.diagnosis": {
        "global-skill",
        "adapter",
        "model",
        "harness",
        "tool",
        "project",
        "uncertain",
        "unknown",
    },
    "candidate.scope": {"local", "potentially-global", "uncertain", "unknown"},
    "candidate.target": {
        "skill",
        "reference",
        "script",
        "test",
        "none",
        "unknown",
    },
}


def _lookup(metadata: dict[str, object], path: str) -> tuple[bool, object]:
    current: object = metadata
    for component in path.split("."):
        if not isinstance(current, dict) or component not in current:
            return False, None
        current = current[component]
    return True, current


def validate_observation(metadata: dict[str, object]) -> list[str]:
    """Return every validation error in observation frontmatter metadata."""
    errors: list[str] = []
    if metadata.get("schema") != OBSERVATION_SCHEMA:
        errors.append(f"schema must be {OBSERVATION_SCHEMA}")

    invalid_mappings: set[str] = set()
    for path in _MAPPING_FIELDS:
        if any(path.startswith(parent + ".") for parent in invalid_mappings):
            continue
        exists, value = _lookup(metadata, path)
        if not exists:
            errors.append(f"{path} is required")
            invalid_mappings.add(path)
        elif not isinstance(value, dict):
            errors.append(f"{path} must be a mapping")
            invalid_mappings.add(path)

    def parent_is_invalid(path: str) -> bool:
        return any(
            path == mapping or path.startswith(mapping + ".")
            for mapping in invalid_mappings
        )

    for path in _STRING_FIELDS:
        if parent_is_invalid(path):
            continue
        exists, value = _lookup(metadata, path)
        if not exists:
            errors.append(f"{path} is required")
        elif not isinstance(value, str) or not value:
            errors.append(f"{path} must be a non-empty string")

    contract_path = "skills.global.contract"
    if not parent_is_invalid(contract_path):
        exists, contract = _lookup(metadata, contract_path)
        if not exists:
            errors.append(f"{contract_path} is required")
        elif type(contract) is not int:
            errors.append(f"{contract_path} must be an integer")
        elif contract != 1:
            errors.append(f"{contract_path} must be 1")

    adapter_version_path = "skills.adapter.version"
    if not parent_is_invalid(adapter_version_path):
        exists, adapter_version = _lookup(metadata, adapter_version_path)
        if not exists:
            errors.append(f"{adapter_version_path} is required")
        elif not (
            (isinstance(adapter_version, str) and bool(adapter_version))
            or (type(adapter_version) is int and adapter_version >= 1)
        ):
            errors.append(
                f"{adapter_version_path} must be a non-empty string "
                "or positive integer"
            )

    for path, allowed in _ENUMS.items():
        exists, value = _lookup(metadata, path)
        if exists and isinstance(value, str) and value not in allowed:
            errors.append(
                f"{path} must be one of {', '.join(sorted(allowed))}"
            )

    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover")
    discover.add_argument("project_root", type=Path)
    discover.add_argument("skill_name")
    discover.add_argument(
        "--supported-contract",
        action="append",
        required=True,
        type=int,
        dest="supported_contracts",
    )

    validate = subparsers.add_parser("validate-observation")
    validate.add_argument("observation", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "discover":
        result = discover_adapter(
            args.project_root,
            args.skill_name,
            set(args.supported_contracts),
        )
    else:
        try:
            metadata, _ = parse_frontmatter(args.observation.read_text())
            errors = validate_observation(metadata)
        except (OSError, UnicodeError, ValueError) as error:
            errors = [str(error)]
        result = (
            {"status": "valid", "errors": []}
            if not errors
            else {"status": "invalid", "errors": errors}
        )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["status"] == "invalid" else 0


if __name__ == "__main__":
    raise SystemExit(main())
