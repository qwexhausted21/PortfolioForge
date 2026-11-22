"""Tests for readme_generator module."""

import pytest
from pathlib import Path
import tempfile

from readme_generator import generate_readme_content, generate_readme, load_existing_readme


class TestGenerateReadmeContent:
    """Tests for generate_readme_content function."""

    def test_basic_generation(self):
        """Test basic README generation with minimal inputs."""
        content = generate_readme_content(
            project_name="TestProject",
            description="A test project",
            tech_stack="Python, FastAPI",
            demo_link="",
            private=False
        )
        assert "# TestProject" in content
        assert "A test project" in content
        assert "Python" in content
        assert "FastAPI" in content
        assert "![Public]" in content
        assert "![Private]" not in content

    def test_private_repo_badge(self):
        """Test private repo badge."""
        content = generate_readme_content(
            project_name="PrivateProject",
            description="",
            tech_stack="",
            demo_link="",
            private=True
        )
        assert "![Private]" in content
        assert "Приватный" in content

    def test_public_repo_badge(self):
        """Test public repo badge."""
        content = generate_readme_content(
            project_name="PublicProject",
            description="",
            tech_stack="",
            demo_link="",
            private=False
        )
        assert "![Public]" in content
        assert "Публичный" in content

    def test_tech_stack_badges(self):
        """Test tech stack badges generation."""
        content = generate_readme_content(
            project_name="Test",
            description="",
            tech_stack="Python, FastAPI, React",
            demo_link="",
            private=False
        )
        assert "![Python]" in content
        assert "![FastAPI]" in content
        assert "![React]" in content

    def test_demo_section(self):
        """Test demo section generation."""
        content = generate_readme_content(
            project_name="Test",
            description="",
            tech_stack="",
            demo_link="https://example.com/demo",
            private=False
        )
        assert "## 🚀 Демо" in content
        assert "https://example.com/demo" in content

    def test_empty_tech_stack(self):
        """Test empty tech stack handling."""
        content = generate_readme_content(
            project_name="Test",
            description="",
            tech_stack="",
            demo_link="",
            private=False
        )
        assert "Не указан" in content

    def test_semicolon_separated_tech_stack(self):
        """Test semicolon as separator."""
        content = generate_readme_content(
            project_name="Test",
            description="",
            tech_stack="Python; FastAPI; React",
            demo_link="",
            private=False
        )
        assert "![Python]" in content
        assert "![FastAPI]" in content
        assert "![React]" in content

    def test_unicode_in_description(self):
        """Test unicode characters in description."""
        content = generate_readme_content(
            project_name="Тест",
            description="Описание на русском 🚀",
            tech_stack="Python",
            demo_link="",
            private=False
        )
        assert "Тест" in content
        assert "Описание на русском 🚀" in content


class TestGenerateReadme:
    """Tests for generate_readme function."""

    def test_creates_file(self):
        """Test that README.md file is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir)
            readme_path = generate_readme(
                project_name="TestProject",
                description="Test description",
                tech_stack="Python",
                demo_link="",
                output_path=output_path,
                private=False
            )
            assert readme_path.exists()
            assert readme_path.name == "README.md"
            content = readme_path.read_text(encoding="utf-8")
            assert "# TestProject" in content

    def test_overwrites_existing(self):
        """Test that existing README is overwritten."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir)
            # Create first README
            generate_readme("Project1", "Desc1", "Python", "", output_path, False)
            # Create second README with same path
            readme_path = generate_readme("Project2", "Desc2", "Go", "", output_path, False)
            content = readme_path.read_text(encoding="utf-8")
            assert "# Project2" in content
            assert "Project1" not in content


class TestLoadExistingReadme:
    """Tests for load_existing_readme function."""

    def test_loads_existing(self):
        """Test loading existing README.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = Path(tmpdir) / "README.md"
            readme_path.write_text("# Existing Project\n\nContent here", encoding="utf-8")
            content = load_existing_readme(tmpdir)
            assert content == "# Existing Project\n\nContent here"

    def test_returns_none_for_missing(self):
        """Test returns None when README doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            content = load_existing_readme(tmpdir)
            assert content is None

    def test_ignores_non_readme_files(self):
        """Test that other files don't interfere."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "readme.txt").write_text("Not markdown", encoding="utf-8")
            content = load_existing_readme(tmpdir)
            assert content is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])