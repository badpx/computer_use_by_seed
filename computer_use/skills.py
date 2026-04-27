"""Skills system for computer_use agent."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class Skill:
    name: str
    description: str
    instructions: str
    directory: Path
    # TODO: Level 3 — 支持按需加载附加资源文件（如 REFERENCE.md、schema 等）
    # resources: List[Path] = field(default_factory=list)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a SKILL.md file.

    Frontmatter is delimited by ``---`` lines at the start and end.
    Each line inside is parsed as ``key: value`` (split on first ``:``)
    without requiring any external YAML library.

    Returns a ``(metadata_dict, body_text)`` tuple.  If the content has
    no valid frontmatter the metadata dict is empty and body is the
    original content.
    """
    if not content.startswith("---"):
        return ({}, content)

    lines = content.split("\n")
    # Find the closing '---' (skip the opening one at index 0)
    end_index = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_index = i
            break

    if end_index is None:
        # Malformed: only one '---' found
        return ({}, content)

    metadata: dict = {}
    for line in lines[1:end_index]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()

    body = "\n".join(lines[end_index + 1 :])
    return (metadata, body)


def project_skills_dir() -> Path:
    """Return the project-root skills directory."""
    return Path(__file__).resolve().parents[1] / "skills"


def _normalize_dir(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except OSError:
        return path.expanduser()


def _skill_search_dirs(skills_dir: Optional[str]) -> List[Path]:
    paths = [project_skills_dir()]
    if skills_dir:
        paths.append(Path(skills_dir))

    deduped: List[Path] = []
    seen = set()
    for path in paths:
        normalized = _normalize_dir(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(path.expanduser())
    return deduped


def _scan_skills_dir(skills_dir: Path) -> Iterable[Skill]:
    if not skills_dir.exists():
        return []

    skills: List[Skill] = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        skill_file = child / "SKILL.md"
        if not skill_file.exists():
            continue

        content = skill_file.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(content)

        name = metadata.get("name")
        description = metadata.get("description")
        if not name or not description:
            continue

        skills.append(
            Skill(
                name=name,
                description=description,
                instructions=body,
                directory=child,
                # TODO: Level 3 — 扫描 child 目录下的附加文件（排除 SKILL.md）填充 resources
            )
        )
    return skills


def discover_skills(skills_dir: Optional[str]) -> List[Skill]:
    """Scan project-root skills plus *skills_dir* for ``SKILL.md`` files.

    Each valid skill directory must have a ``SKILL.md`` whose frontmatter
    includes both ``name`` and ``description``.  Directories that don't
    meet this requirement are silently skipped.

    Project-root ``skills/`` is scanned first.  *skills_dir* is scanned
    afterwards, so custom skills with the same ``name`` override project
    skills.

    Returns the list sorted by skill name for deterministic ordering.
    If neither directory exists an empty list is returned.
    """
    skills_by_name = {}
    for directory in _skill_search_dirs(skills_dir):
        for skill in _scan_skills_dir(directory):
            skills_by_name[skill.name] = skill

    skills = list(skills_by_name.values())
    skills.sort(key=lambda s: s.name)
    return skills


def skills_to_tools(skills: List[Skill]) -> List[dict]:
    """Convert skills to OpenAI-compatible function-calling tool format."""
    tools: List[dict] = []
    for skill in skills:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": f"skill__{skill.name}",
                    "description": skill.description,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            }
        )
    return tools


def load_skill(skills: List[Skill], tool_name: str) -> str:
    """Look up a skill by its tool name and return its instructions.

    *tool_name* has the form ``skill__<name>``.  The ``skill__`` prefix
    is stripped before matching against known skill names.  If no match
    is found a human-readable error listing available skills is returned.

    # TODO: Level 3 — 支持独立的 resource tool（如 load_resource__<skill>__<filename>），
    #   让模型可以按需加载附加资源文件而无需将全部内容一次性注入上下文。
    # TODO: Level 3 — 支持在 skill 目录下发现并执行脚本（scripts/*.py），
    #   只将脚本输出注入消息，而非脚本源码，以节省 context 并提高确定性。
    """
    name = tool_name.removeprefix("skill__")
    for skill in skills:
        if skill.name == name:
            return skill.instructions
    available = ", ".join(s.name for s in skills)
    return f"Unknown skill: {tool_name}. Available: {available}"
