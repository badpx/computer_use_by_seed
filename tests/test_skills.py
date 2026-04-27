import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import computer_use.skills as skills_module
from computer_use.skills import (
    Skill,
    discover_skills,
    load_skill,
    parse_frontmatter,
    skills_to_tools,
)


class TestSkills(unittest.TestCase):
    def _write_skill(
        self,
        base_dir: str,
        directory_name: str,
        name: str,
        description: str,
        instructions: str,
    ) -> Path:
        skill_dir = Path(base_dir) / directory_name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            "---\n"
            "\n"
            f"{instructions}",
            encoding="utf-8",
        )
        return skill_dir

    # 1
    def test_parse_frontmatter_extracts_name_and_description(self):
        content = (
            "---\n"
            "name: open-browser\n"
            "description: Navigate to URLs\n"
            "---\n"
            "\n"
            "## Instructions\n"
            "Step 1"
        )
        metadata, body = parse_frontmatter(content)
        self.assertEqual(metadata["name"], "open-browser")
        self.assertEqual(metadata["description"], "Navigate to URLs")
        self.assertIn("## Instructions", body)

    # 2
    def test_parse_frontmatter_no_frontmatter(self):
        content = "Just plain content"
        metadata, body = parse_frontmatter(content)
        self.assertEqual(metadata, {})
        self.assertEqual(body, "Just plain content")

    # 3
    def test_parse_frontmatter_malformed_single_delimiter(self):
        content = "---\nname: foo\n"
        metadata, body = parse_frontmatter(content)
        self.assertEqual(metadata, {})
        self.assertEqual(body, content)

    # 4
    def test_discover_skills_finds_valid_skills(self):
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as root_dir:
            skill_dir = Path(tmpdir) / "myskill"
            skill_dir.mkdir()
            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text(
                "---\n"
                "name: myskill\n"
                "description: A test skill\n"
                "---\n"
                "\n"
                "Do something useful",
                encoding="utf-8",
            )

            with patch.object(skills_module, "project_skills_dir", return_value=Path(root_dir)):
                skills = discover_skills(tmpdir)
            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].name, "myskill")
            self.assertEqual(skills[0].description, "A test skill")
            self.assertIn("Do something useful", skills[0].instructions)

    # 5
    def test_discover_skills_missing_dir(self):
        with patch.object(
            skills_module,
            "project_skills_dir",
            return_value=Path("/nonexistent/project/skills"),
        ):
            result = discover_skills("/nonexistent/path/xyz")
        self.assertEqual(result, [])

    # 6
    def test_discover_skills_skips_directories_without_skill_md(self):
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as root_dir:
            empty_dir = Path(tmpdir) / "noskill"
            empty_dir.mkdir()

            with patch.object(skills_module, "project_skills_dir", return_value=Path(root_dir)):
                skills = discover_skills(tmpdir)
            self.assertEqual(skills, [])

    # 7
    def test_discover_skills_includes_project_root_skills(self):
        with tempfile.TemporaryDirectory() as project_dir:
            root_skills_dir = Path(project_dir) / "skills"
            root_skills_dir.mkdir()
            self._write_skill(
                str(root_skills_dir),
                "root-skill",
                "root-skill",
                "Project skill",
                "Use project skill.",
            )

            with patch.object(skills_module, "project_skills_dir", return_value=root_skills_dir):
                skills = discover_skills("/nonexistent/custom/skills")

        self.assertEqual([skill.name for skill in skills], ["root-skill"])
        self.assertIn("Use project skill.", skills[0].instructions)

    # 8
    def test_discover_skills_custom_dir_overrides_project_root_by_name(self):
        with tempfile.TemporaryDirectory() as project_dir, tempfile.TemporaryDirectory() as custom_dir:
            root_skills_dir = Path(project_dir) / "skills"
            root_skills_dir.mkdir()
            self._write_skill(
                str(root_skills_dir),
                "open-browser",
                "open-browser",
                "Project open browser",
                "Project instructions.",
            )
            custom_skill_dir = self._write_skill(
                custom_dir,
                "open-browser",
                "open-browser",
                "Custom open browser",
                "Custom instructions.",
            )

            with patch.object(skills_module, "project_skills_dir", return_value=root_skills_dir):
                skills = discover_skills(custom_dir)

        self.assertEqual([skill.name for skill in skills], ["open-browser"])
        self.assertEqual(skills[0].description, "Custom open browser")
        self.assertEqual(skills[0].directory, custom_skill_dir)
        self.assertIn("Custom instructions.", skills[0].instructions)

    # 9
    def test_discover_skills_deduplicates_when_custom_dir_is_project_root(self):
        with tempfile.TemporaryDirectory() as project_dir:
            root_skills_dir = Path(project_dir) / "skills"
            root_skills_dir.mkdir()
            self._write_skill(
                str(root_skills_dir),
                "same-dir",
                "same-dir",
                "Same dir",
                "Same directory instructions.",
            )

            with patch.object(skills_module, "project_skills_dir", return_value=root_skills_dir):
                skills = discover_skills(str(root_skills_dir))

        self.assertEqual([skill.name for skill in skills], ["same-dir"])

    # 10
    def test_skills_to_tools_generates_correct_format(self):
        skill = Skill(
            name="greeter",
            description="Say hello",
            instructions="Greet the user",
            directory=Path("/tmp/greeter"),
        )
        tools = skills_to_tools([skill])
        self.assertEqual(len(tools), 1)
        tool = tools[0]
        self.assertEqual(tool["type"], "function")
        self.assertEqual(tool["function"]["name"], "skill__greeter")
        self.assertEqual(tool["function"]["description"], "Say hello")
        self.assertEqual(
            tool["function"]["parameters"],
            {"type": "object", "properties": {}, "required": []},
        )

    # 11
    def test_load_skill_found_returns_instructions(self):
        skill = Skill(
            name="myskill",
            description="desc",
            instructions="Follow these steps",
            directory=Path("/tmp/myskill"),
        )
        result = load_skill([skill], "skill__myskill")
        self.assertEqual(result, "Follow these steps")

    # 12
    def test_load_skill_not_found_returns_error(self):
        skill = Skill(
            name="myskill",
            description="desc",
            instructions="steps",
            directory=Path("/tmp/myskill"),
        )
        result = load_skill([skill], "skill__unknown")
        self.assertIn("Unknown skill", result)
        self.assertIn("skill__unknown", result)


if __name__ == "__main__":
    unittest.main()
