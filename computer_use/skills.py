"""
基础 Skills 运行时
支持本地 skills 发现、候选筛选，以及通过 function call 按需披露 skill 内容。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


TEXT_RESOURCE_SUFFIXES = {
    '.md',
    '.txt',
    '.json',
    '.yaml',
    '.yml',
    '.py',
    '.toml',
    '.ini',
    '.cfg',
}


@dataclass
class SkillDefinition:
    """单个 skill 的结构化定义。"""

    name: str
    description: str
    tags: List[str]
    triggers: List[str]
    path: Path
    skill_md_path: Path
    body: str
    metadata: Dict[str, Any]
    resource_paths: List[str]


def parse_skill_paths(configured_paths: Optional[Sequence[str] | str]) -> List[str]:
    """标准化 skills 目录列表。"""
    if configured_paths is None:
        return []

    if isinstance(configured_paths, str):
        raw_items = configured_paths.split(os.pathsep)
    else:
        raw_items = []
        for item in configured_paths:
            if item is None:
                continue
            raw_items.extend(str(item).split(os.pathsep))

    normalized: List[str] = []
    seen = set()
    for item in raw_items:
        path = item.strip()
        if not path:
            continue
        expanded = str(Path(path).expanduser())
        if expanded in seen:
            continue
        seen.add(expanded)
        normalized.append(expanded)
    return normalized


def extract_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """解析 SKILL.md 中的简单 YAML frontmatter。"""
    if not text.startswith('---'):
        return {}, text.strip()

    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        return {}, text.strip()

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == '---':
            end_index = index
            break

    if end_index is None:
        return {}, text.strip()

    metadata_lines = lines[1:end_index]
    body = '\n'.join(lines[end_index + 1:]).strip()
    return _parse_simple_yaml(metadata_lines), body


def _parse_simple_yaml(lines: Sequence[str]) -> Dict[str, Any]:
    """解析首版所需的浅层 YAML。"""
    metadata: Dict[str, Any] = {}
    current_list_key: Optional[str] = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        if stripped.startswith('- '):
            if current_list_key is None:
                continue
            metadata.setdefault(current_list_key, [])
            metadata[current_list_key].append(_parse_scalar(stripped[2:].strip()))
            continue

        current_list_key = None
        if ':' not in stripped:
            continue

        key, raw_value = stripped.split(':', 1)
        key = key.strip()
        value = raw_value.strip()
        if not value:
            metadata[key] = []
            current_list_key = key
            continue

        if value.startswith('[') and value.endswith(']'):
            inner = value[1:-1].strip()
            if not inner:
                metadata[key] = []
            else:
                metadata[key] = [
                    _parse_scalar(item.strip()) for item in inner.split(',')
                ]
            continue

        metadata[key] = _parse_scalar(value)

    return metadata


def _parse_scalar(value: str) -> Any:
    """解析简单标量值。"""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    if value.lower() in {'true', 'false'}:
        return value.lower() == 'true'
    return value


def _to_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


class SkillRegistry:
    """本地 skill 发现与加载。"""

    def __init__(self, skill_paths: Sequence[str]):
        self.skill_paths = parse_skill_paths(skill_paths)
        self._skills: Optional[Dict[str, SkillDefinition]] = None

    def load(self) -> Dict[str, SkillDefinition]:
        """扫描 skills 目录。repo 本地目录优先级高于全局目录。"""
        if self._skills is not None:
            return self._skills

        skills: Dict[str, SkillDefinition] = {}
        for base_path in self.skill_paths:
            root = Path(base_path).expanduser()
            if not root.exists() or not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                if not child.is_dir():
                    continue
                skill_md_path = child / 'SKILL.md'
                if not skill_md_path.exists():
                    continue
                skill = self._load_skill(child, skill_md_path)
                skills[skill.name] = skill

        self._skills = skills
        return self._skills

    def get(self, skill_name: str) -> Optional[SkillDefinition]:
        return self.load().get(skill_name)

    def values(self) -> List[SkillDefinition]:
        return list(self.load().values())

    def _load_skill(self, path: Path, skill_md_path: Path) -> SkillDefinition:
        text = skill_md_path.read_text(encoding='utf-8')
        metadata, body = extract_frontmatter(text)
        name = str(metadata.get('name') or path.name).strip()
        description = str(metadata.get('description') or _extract_first_paragraph(body) or path.name).strip()
        tags = _to_string_list(metadata.get('tags'))
        triggers = _to_string_list(metadata.get('triggers'))

        return SkillDefinition(
            name=name,
            description=description,
            tags=tags,
            triggers=triggers,
            path=path,
            skill_md_path=skill_md_path,
            body=body,
            metadata=metadata,
            resource_paths=self._list_resource_paths(path),
        )

    def _list_resource_paths(self, skill_path: Path) -> List[str]:
        resources_dir = skill_path / 'resources'
        if not resources_dir.exists() or not resources_dir.is_dir():
            return []

        resource_paths = []
        for file_path in sorted(resources_dir.rglob('*')):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in TEXT_RESOURCE_SUFFIXES:
                continue
            resource_paths.append(file_path.relative_to(skill_path).as_posix())
        return resource_paths


def _extract_first_paragraph(text: str) -> str:
    for paragraph in re.split(r'\n\s*\n', text):
        stripped = paragraph.strip()
        if stripped:
            return stripped
    return ''


def select_candidate_skills(
    instruction: str,
    registry: SkillRegistry,
    limit: int = 5,
) -> List[SkillDefinition]:
    """按任务指令筛选最相关的候选 skills。"""
    instruction_text = str(instruction or '')
    instruction_tokens = _tokenize(instruction_text)
    scored: List[Tuple[int, str, SkillDefinition]] = []

    for skill in registry.values():
        score = _score_skill(instruction_text, instruction_tokens, skill)
        if score <= 0:
            continue
        scored.append((score, skill.name.lower(), skill))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored[: max(0, limit)]]


def _score_skill(
    instruction_text: str,
    instruction_tokens: set[str],
    skill: SkillDefinition,
) -> int:
    lowered_instruction = instruction_text.lower()
    score = 0

    if skill.name.lower() in lowered_instruction:
        score += 100

    searchable_tokens = set()
    searchable_tokens.update(_tokenize(skill.name))
    searchable_tokens.update(_tokenize(skill.description))
    for item in skill.tags + skill.triggers:
        searchable_tokens.update(_tokenize(item))

    score += len(instruction_tokens & searchable_tokens)
    return score


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r'[A-Za-z0-9_\-\u4e00-\u9fff]+', text or '')
        if token
    }


def build_skill_tools(candidate_skills: Sequence[SkillDefinition]) -> List[Dict[str, Any]]:
    """构建方舟 function calling tools。"""
    if not candidate_skills:
        return []

    skill_names = [skill.name for skill in candidate_skills]
    return [
        {
            'type': 'function',
            'function': {
                'name': 'load_skill',
                'description': '加载一个候选 skill 的完整说明与可读资源清单。仅在该 skill 明显有助于当前任务时调用。',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'skill_name': {
                            'type': 'string',
                            'enum': skill_names,
                            'description': '要展开的 skill 名称',
                        }
                    },
                    'required': ['skill_name'],
                },
            },
        },
        {
            'type': 'function',
            'function': {
                'name': 'read_skill_resource',
                'description': '按需读取已加载 skill 的附带文本资源。先调用 load_skill，再根据返回的 resource_paths 选择要读取的文件。',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'skill_name': {
                            'type': 'string',
                            'enum': skill_names,
                            'description': '所属 skill 名称',
                        },
                        'resource_path': {
                            'type': 'string',
                            'description': '资源相对路径，必须来自 load_skill 返回的 resource_paths',
                        },
                    },
                    'required': ['skill_name', 'resource_path'],
                },
            },
        },
    ]


class SkillRuntime:
    """执行 skill 相关 tool call。"""

    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def execute_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        candidate_skills: Sequence[SkillDefinition],
    ) -> Tuple[str, Dict[str, Any]]:
        candidate_by_name = {skill.name: skill for skill in candidate_skills}
        if tool_name == 'load_skill':
            skill_name = str(arguments.get('skill_name') or '').strip()
            skill = candidate_by_name.get(skill_name)
            if skill is None:
                raise ValueError(f'未知或未授权的 skill: {skill_name}')
            payload = self._build_load_skill_payload(skill)
            return json.dumps(payload, ensure_ascii=False), payload

        if tool_name == 'read_skill_resource':
            skill_name = str(arguments.get('skill_name') or '').strip()
            resource_path = str(arguments.get('resource_path') or '').strip()
            skill = candidate_by_name.get(skill_name)
            if skill is None:
                raise ValueError(f'未知或未授权的 skill: {skill_name}')
            payload = self._build_read_resource_payload(skill, resource_path)
            return json.dumps(payload, ensure_ascii=False), payload

        raise ValueError(f'未知的 skill tool: {tool_name}')

    def _build_load_skill_payload(self, skill: SkillDefinition) -> Dict[str, Any]:
        return {
            'skill_name': skill.name,
            'description': skill.description,
            'tags': skill.tags,
            'triggers': skill.triggers,
            'instructions': skill.body,
            'resource_paths': skill.resource_paths,
        }

    def _build_read_resource_payload(
        self,
        skill: SkillDefinition,
        resource_path: str,
    ) -> Dict[str, Any]:
        normalized = resource_path.replace('\\', '/').strip('/')
        if normalized not in set(skill.resource_paths):
            raise ValueError(f'资源不存在或不允许读取: {resource_path}')

        resource_file = (skill.path / normalized).resolve()
        skill_root = skill.path.resolve()
        if not str(resource_file).startswith(str(skill_root)):
            raise ValueError(f'资源路径越界: {resource_path}')
        if not resource_file.exists() or not resource_file.is_file():
            raise ValueError(f'资源文件不存在: {resource_path}')
        if resource_file.suffix.lower() not in TEXT_RESOURCE_SUFFIXES:
            raise ValueError(f'不支持的资源类型: {resource_path}')

        content = resource_file.read_text(encoding='utf-8')
        return {
            'skill_name': skill.name,
            'resource_path': normalized,
            'content': content,
        }


def build_skills_prompt_section(candidate_skills: Sequence[SkillDefinition]) -> str:
    """构建注入 system prompt 的 skills 说明段。"""
    if not candidate_skills:
        return ''

    lines = [
        '## Skills',
        '- Some task-specific skills are available as function tools.',
        '- Only load a skill when it is clearly relevant to the current task.',
        '- After loading a skill, read only the specific resources you need.',
        '- Do not load every skill by default.',
        '- After any tool use, your final reply must still follow the Thought/Action format.',
        '',
        '### Candidate Skills',
    ]
    for skill in candidate_skills:
        lines.append(f"- {skill.name}: {skill.description}")
    return '\n'.join(lines)
