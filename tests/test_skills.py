import tempfile
import unittest
from pathlib import Path

from computer_use.skills import (
    SkillRegistry,
    SkillRuntime,
    build_skill_tools,
    extract_frontmatter,
    parse_skill_paths,
    select_candidate_skills,
)


class SkillsTests(unittest.TestCase):
    def test_extract_frontmatter_supports_simple_lists(self):
        metadata, body = extract_frontmatter(
            """---
name: browser_helper
description: Help with browser tasks
tags:
  - browser
  - page
triggers: [open page, inspect]
---
Use browser helper carefully.
"""
        )

        self.assertEqual(metadata['name'], 'browser_helper')
        self.assertEqual(metadata['tags'], ['browser', 'page'])
        self.assertEqual(metadata['triggers'], ['open page', 'inspect'])
        self.assertEqual(body, 'Use browser helper carefully.')

    def test_parse_skill_paths_normalizes_and_deduplicates(self):
        parsed = parse_skill_paths(['~/.skills', './.skills', './.skills'])

        self.assertEqual(len(parsed), 2)
        self.assertTrue(parsed[0].endswith('.skills'))

    def test_repo_local_skill_overrides_global_same_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            global_skill = temp_path / 'global' / 'same_skill'
            local_skill = temp_path / 'local' / 'same_skill'
            global_skill.mkdir(parents=True)
            local_skill.mkdir(parents=True)
            (global_skill / 'SKILL.md').write_text('global desc', encoding='utf-8')
            (local_skill / 'SKILL.md').write_text('local desc', encoding='utf-8')

            registry = SkillRegistry([str(global_skill.parent), str(local_skill.parent)])
            skill = registry.get('same_skill')

            self.assertIsNotNone(skill)
            self.assertEqual(skill.description, 'local desc')

    def test_select_candidate_skills_prefers_explicit_name_match(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / '.skills'
            first = skills_root / 'draw_board'
            second = skills_root / 'browser_helper'
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            (first / 'SKILL.md').write_text(
                """---
name: draw_board
description: Drawing board helper
tags: [draw, board]
---
Use the draw board.
""",
                encoding='utf-8',
            )
            (second / 'SKILL.md').write_text(
                """---
name: browser_helper
description: Browser helper
tags: [browser]
---
Use the browser helper.
""",
                encoding='utf-8',
            )

            registry = SkillRegistry([str(skills_root)])
            candidates = select_candidate_skills(
                'Please use draw_board to draw a shape',
                registry,
                limit=5,
            )

            self.assertEqual([skill.name for skill in candidates], ['draw_board'])

    def test_runtime_reads_declared_text_resource_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_root = Path(temp_dir) / '.skills' / 'browser_helper'
            resources_dir = skill_root / 'resources'
            resources_dir.mkdir(parents=True)
            (skill_root / 'SKILL.md').write_text(
                """---
name: browser_helper
description: Browser helper
tags: [browser]
---
Use the browser helper.
""",
                encoding='utf-8',
            )
            (resources_dir / 'tips.md').write_text('open page first', encoding='utf-8')

            registry = SkillRegistry([str(skill_root.parent)])
            runtime = SkillRuntime(registry)
            candidate = registry.get('browser_helper')
            self.assertIsNotNone(candidate)

            tool_text, payload = runtime.execute_tool_call(
                tool_name='read_skill_resource',
                arguments={
                    'skill_name': 'browser_helper',
                    'resource_path': 'resources/tips.md',
                },
                candidate_skills=[candidate],
            )

            self.assertIn('open page first', tool_text)
            self.assertEqual(payload['resource_path'], 'resources/tips.md')

    def test_runtime_rejects_undeclared_resource(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_root = Path(temp_dir) / '.skills' / 'browser_helper'
            skill_root.mkdir(parents=True)
            (skill_root / 'SKILL.md').write_text(
                """---
name: browser_helper
description: Browser helper
tags: [browser]
---
Use the browser helper.
""",
                encoding='utf-8',
            )

            registry = SkillRegistry([str(skill_root.parent)])
            runtime = SkillRuntime(registry)
            candidate = registry.get('browser_helper')
            self.assertIsNotNone(candidate)

            with self.assertRaisesRegex(ValueError, '资源不存在或不允许读取'):
                runtime.execute_tool_call(
                    tool_name='read_skill_resource',
                    arguments={
                        'skill_name': 'browser_helper',
                        'resource_path': '../secret.txt',
                    },
                    candidate_skills=[candidate],
                )

    def test_build_skill_tools_uses_candidate_names_as_enum(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_root = Path(temp_dir) / '.skills' / 'browser_helper'
            skill_root.mkdir(parents=True)
            (skill_root / 'SKILL.md').write_text('browser helper', encoding='utf-8')
            registry = SkillRegistry([str(skill_root.parent)])
            candidate = registry.get('browser_helper')

            tools = build_skill_tools([candidate])

            self.assertEqual(
                tools[0]['function']['parameters']['properties']['skill_name']['enum'],
                ['browser_helper'],
            )


if __name__ == '__main__':
    unittest.main()
