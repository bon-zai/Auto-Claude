#!/usr/bin/env python3
"""
Pytest Configuration and Shared Fixtures
=========================================

Provides common test fixtures for the Auto-Build Framework test suite.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# Add auto-build directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "auto-build"))


# =============================================================================
# DIRECTORY FIXTURES
# =============================================================================

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory that's cleaned up after the test."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def temp_git_repo(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a temporary git repository with initial commit."""
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=temp_dir, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=temp_dir, capture_output=True
    )

    # Create initial commit
    test_file = temp_dir / "README.md"
    test_file.write_text("# Test Project\n")
    subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=temp_dir, capture_output=True
    )

    yield temp_dir


@pytest.fixture
def spec_dir(temp_dir: Path) -> Path:
    """Create a spec directory inside temp_dir."""
    spec_path = temp_dir / "spec"
    spec_path.mkdir(parents=True)
    return spec_path


# =============================================================================
# PROJECT STRUCTURE FIXTURES
# =============================================================================

@pytest.fixture
def python_project(temp_git_repo: Path) -> Path:
    """Create a sample Python project structure."""
    # Create pyproject.toml
    pyproject = {
        "project": {
            "name": "test-project",
            "version": "0.1.0",
            "dependencies": [
                "flask>=2.0",
                "pytest>=7.0",
                "sqlalchemy>=2.0",
            ],
        },
        "tool": {
            "pytest": {"testpaths": ["tests"]},
            "ruff": {"line-length": 100},
        },
    }

    import tomllib
    # Write as TOML (we'll write manually since tomllib is read-only)
    toml_content = """[project]
name = "test-project"
version = "0.1.0"
dependencies = [
    "flask>=2.0",
    "pytest>=7.0",
    "sqlalchemy>=2.0",
]

[tool.pytest]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
"""
    (temp_git_repo / "pyproject.toml").write_text(toml_content)

    # Create Python files
    (temp_git_repo / "app").mkdir()
    (temp_git_repo / "app" / "__init__.py").write_text("# App module\n")
    (temp_git_repo / "app" / "main.py").write_text("def main():\n    pass\n")

    # Create .env file
    (temp_git_repo / ".env").write_text("DATABASE_URL=postgresql://localhost/test\n")

    # Commit changes
    subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add Python project structure"],
        cwd=temp_git_repo, capture_output=True
    )

    return temp_git_repo


@pytest.fixture
def node_project(temp_git_repo: Path) -> Path:
    """Create a sample Node.js project structure."""
    package_json = {
        "name": "test-project",
        "version": "1.0.0",
        "scripts": {
            "dev": "next dev",
            "build": "next build",
            "test": "jest",
            "lint": "eslint .",
        },
        "dependencies": {
            "next": "^14.0.0",
            "react": "^18.0.0",
            "prisma": "^5.0.0",
        },
        "devDependencies": {
            "jest": "^29.0.0",
            "eslint": "^8.0.0",
            "typescript": "^5.0.0",
        },
    }

    (temp_git_repo / "package.json").write_text(json.dumps(package_json, indent=2))
    (temp_git_repo / "tsconfig.json").write_text('{"compilerOptions": {}}')

    # Create source files
    (temp_git_repo / "src").mkdir()
    (temp_git_repo / "src" / "index.ts").write_text("export const main = () => {};\n")

    # Commit changes
    subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add Node.js project structure"],
        cwd=temp_git_repo, capture_output=True
    )

    return temp_git_repo


@pytest.fixture
def docker_project(temp_git_repo: Path) -> Path:
    """Create a project with Docker configuration."""
    # Dockerfile
    dockerfile = """FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "main.py"]
"""
    (temp_git_repo / "Dockerfile").write_text(dockerfile)

    # docker-compose.yml
    compose = """services:
  app:
    build: .
    ports:
      - "8000:8000"
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: test
  redis:
    image: redis:7
"""
    (temp_git_repo / "docker-compose.yml").write_text(compose)

    # requirements.txt
    (temp_git_repo / "requirements.txt").write_text("flask\nredis\npsycopg2-binary\n")

    # Commit changes
    subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add Docker configuration"],
        cwd=temp_git_repo, capture_output=True
    )

    return temp_git_repo


# =============================================================================
# IMPLEMENTATION PLAN FIXTURES
# =============================================================================

@pytest.fixture
def sample_implementation_plan() -> dict:
    """Return a sample implementation plan structure."""
    return {
        "feature": "User Avatar Upload",
        "workflow_type": "feature",
        "services_involved": ["backend", "worker", "frontend"],
        "phases": [
            {
                "phase": 1,
                "name": "Backend Foundation",
                "type": "setup",
                "chunks": [
                    {
                        "id": "chunk-1-1",
                        "description": "Add avatar fields to User model",
                        "service": "backend",
                        "status": "completed",
                        "files_to_modify": ["app/models/user.py"],
                        "files_to_create": ["migrations/add_avatar.py"],
                    },
                    {
                        "id": "chunk-1-2",
                        "description": "POST /api/users/avatar endpoint",
                        "service": "backend",
                        "status": "pending",
                        "files_to_modify": ["app/routes/users.py"],
                    },
                ],
                "depends_on": [],
            },
            {
                "phase": 2,
                "name": "Worker Pipeline",
                "type": "implementation",
                "chunks": [
                    {
                        "id": "chunk-2-1",
                        "description": "Image processing task",
                        "service": "worker",
                        "status": "pending",
                        "files_to_create": ["app/tasks/images.py"],
                    },
                ],
                "depends_on": [1],
            },
            {
                "phase": 3,
                "name": "Frontend",
                "type": "implementation",
                "chunks": [
                    {
                        "id": "chunk-3-1",
                        "description": "AvatarUpload component",
                        "service": "frontend",
                        "status": "pending",
                        "files_to_create": ["src/components/AvatarUpload.tsx"],
                    },
                ],
                "depends_on": [1],
            },
        ],
        "final_acceptance": [
            "User can upload avatar from profile page",
            "Avatar is automatically resized",
        ],
    }


@pytest.fixture
def implementation_plan_file(spec_dir: Path, sample_implementation_plan: dict) -> Path:
    """Create an implementation_plan.json file in the spec directory."""
    plan_file = spec_dir / "implementation_plan.json"
    plan_file.write_text(json.dumps(sample_implementation_plan, indent=2))
    return plan_file


# =============================================================================
# SPEC FIXTURES
# =============================================================================

@pytest.fixture
def sample_spec() -> str:
    """Return a sample spec content."""
    return """# Avatar Upload Feature

## Overview
Allow users to upload and manage their profile avatars.

## Requirements
1. Users can upload PNG, JPG, or WebP images
2. Images are automatically resized to 200x200
3. Original images are stored for future cropping
4. Upload progress is shown in UI

## Acceptance Criteria
- [ ] POST /api/users/avatar endpoint accepts image uploads
- [ ] Images are processed asynchronously by worker
- [ ] Frontend shows upload progress
- [ ] Avatar displays correctly after upload
"""


@pytest.fixture
def spec_file(spec_dir: Path, sample_spec: str) -> Path:
    """Create a spec.md file in the spec directory."""
    spec_file = spec_dir / "spec.md"
    spec_file.write_text(sample_spec)
    return spec_file


# =============================================================================
# QA FIXTURES
# =============================================================================

@pytest.fixture
def qa_signoff_approved() -> dict:
    """Return an approved QA signoff structure."""
    return {
        "status": "approved",
        "qa_session": 1,
        "timestamp": "2024-01-01T12:00:00",
        "tests_passed": {
            "unit": True,
            "integration": True,
            "e2e": True,
        },
    }


@pytest.fixture
def qa_signoff_rejected() -> dict:
    """Return a rejected QA signoff structure."""
    return {
        "status": "rejected",
        "qa_session": 1,
        "timestamp": "2024-01-01T12:00:00",
        "issues_found": [
            {"title": "Test failure", "type": "unit_test"},
            {"title": "Missing validation", "type": "acceptance"},
        ],
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

@pytest.fixture
def make_commit(temp_git_repo: Path):
    """Factory fixture to create commits."""
    def _make_commit(filename: str, content: str, message: str) -> str:
        filepath = temp_git_repo / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=temp_git_repo, capture_output=True
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=temp_git_repo, capture_output=True, text=True
        )
        return result.stdout.strip()
    return _make_commit


@pytest.fixture
def stage_files(temp_git_repo: Path):
    """Factory fixture to stage files without committing."""
    def _stage_files(files: dict[str, str]) -> None:
        for filename, content in files.items():
            filepath = temp_git_repo / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content)
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
    return _stage_files
