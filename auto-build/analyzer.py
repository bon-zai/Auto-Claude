#!/usr/bin/env python3
"""
Codebase Analyzer
=================

Automatically detects project structure, frameworks, and services.
Supports monorepos with multiple services.

Usage:
    # Index entire project (creates project_index.json)
    python auto-build/analyzer.py --index

    # Analyze specific service
    python auto-build/analyzer.py --service backend

    # Output to specific file
    python auto-build/analyzer.py --index --output path/to/output.json

The analyzer will:
1. Detect if this is a monorepo or single project
2. Find all services/packages and analyze each separately
3. Map interdependencies between services
4. Identify infrastructure (Docker, CI/CD)
5. Document conventions (linting, testing)
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Directories to skip during analysis
SKIP_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    "env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    "vendor",
    ".idea",
    ".vscode",
    "auto-build",
    ".pytest_cache",
    ".mypy_cache",
    "coverage",
    ".coverage",
    "htmlcov",
    "eggs",
    "*.egg-info",
    ".turbo",
    ".cache",
}

# Common service directory names
SERVICE_INDICATORS = {
    "backend", "frontend", "api", "web", "app", "server", "client",
    "worker", "workers", "services", "packages", "apps", "libs",
    "scraper", "crawler", "proxy", "gateway", "admin", "dashboard",
    "mobile", "desktop", "cli", "sdk", "core", "shared", "common",
}

# Files that indicate a service root
SERVICE_ROOT_FILES = {
    "package.json", "requirements.txt", "pyproject.toml", "Cargo.toml",
    "go.mod", "Gemfile", "composer.json", "pom.xml", "build.gradle",
    "Makefile", "Dockerfile",
}


class ServiceAnalyzer:
    """Analyzes a single service/package within a project."""

    def __init__(self, service_path: Path, service_name: str):
        self.path = service_path.resolve()
        self.name = service_name
        self.analysis = {
            "name": service_name,
            "path": str(service_path),
            "language": None,
            "framework": None,
            "type": None,  # backend, frontend, worker, library, etc.
        }

    def analyze(self) -> dict[str, Any]:
        """Run full analysis on this service."""
        self._detect_language_and_framework()
        self._detect_service_type()
        self._find_key_directories()
        self._find_entry_points()
        self._detect_dependencies()
        self._detect_testing()
        self._find_dockerfile()
        return self.analysis

    def _detect_language_and_framework(self) -> None:
        """Detect primary language and framework."""
        # Python detection
        if self._exists("requirements.txt"):
            self.analysis["language"] = "Python"
            self.analysis["package_manager"] = "pip"
            deps = self._read_file("requirements.txt")
            self._detect_python_framework(deps)

        elif self._exists("pyproject.toml"):
            self.analysis["language"] = "Python"
            content = self._read_file("pyproject.toml")
            if "[tool.poetry]" in content:
                self.analysis["package_manager"] = "poetry"
            elif "[tool.uv]" in content:
                self.analysis["package_manager"] = "uv"
            else:
                self.analysis["package_manager"] = "pip"
            self._detect_python_framework(content)

        elif self._exists("Pipfile"):
            self.analysis["language"] = "Python"
            self.analysis["package_manager"] = "pipenv"
            content = self._read_file("Pipfile")
            self._detect_python_framework(content)

        # Node.js/TypeScript detection
        elif self._exists("package.json"):
            pkg = self._read_json("package.json")
            if pkg:
                # Check if TypeScript
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "typescript" in deps:
                    self.analysis["language"] = "TypeScript"
                else:
                    self.analysis["language"] = "JavaScript"

                self.analysis["package_manager"] = self._detect_node_package_manager()
                self._detect_node_framework(pkg)

        # Go detection
        elif self._exists("go.mod"):
            self.analysis["language"] = "Go"
            self.analysis["package_manager"] = "go mod"
            content = self._read_file("go.mod")
            self._detect_go_framework(content)

        # Rust detection
        elif self._exists("Cargo.toml"):
            self.analysis["language"] = "Rust"
            self.analysis["package_manager"] = "cargo"
            content = self._read_file("Cargo.toml")
            self._detect_rust_framework(content)

        # Ruby detection
        elif self._exists("Gemfile"):
            self.analysis["language"] = "Ruby"
            self.analysis["package_manager"] = "bundler"
            content = self._read_file("Gemfile")
            self._detect_ruby_framework(content)

    def _detect_python_framework(self, content: str) -> None:
        """Detect Python framework."""
        content_lower = content.lower()

        # Web frameworks
        frameworks = {
            "fastapi": {"name": "FastAPI", "type": "backend", "port": 8000},
            "flask": {"name": "Flask", "type": "backend", "port": 5000},
            "django": {"name": "Django", "type": "backend", "port": 8000},
            "starlette": {"name": "Starlette", "type": "backend", "port": 8000},
            "litestar": {"name": "Litestar", "type": "backend", "port": 8000},
        }

        for key, info in frameworks.items():
            if key in content_lower:
                self.analysis["framework"] = info["name"]
                self.analysis["type"] = info["type"]
                self.analysis["default_port"] = info["port"]
                break

        # Task queues
        if "celery" in content_lower:
            self.analysis["task_queue"] = "Celery"
            if not self.analysis.get("type"):
                self.analysis["type"] = "worker"
        elif "dramatiq" in content_lower:
            self.analysis["task_queue"] = "Dramatiq"
        elif "huey" in content_lower:
            self.analysis["task_queue"] = "Huey"

        # ORM
        if "sqlalchemy" in content_lower:
            self.analysis["orm"] = "SQLAlchemy"
        elif "tortoise" in content_lower:
            self.analysis["orm"] = "Tortoise ORM"
        elif "prisma" in content_lower:
            self.analysis["orm"] = "Prisma"

    def _detect_node_framework(self, pkg: dict) -> None:
        """Detect Node.js/TypeScript framework."""
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        deps_lower = {k.lower(): k for k in deps.keys()}

        # Frontend frameworks
        frontend_frameworks = {
            "next": {"name": "Next.js", "type": "frontend", "port": 3000},
            "nuxt": {"name": "Nuxt", "type": "frontend", "port": 3000},
            "react": {"name": "React", "type": "frontend", "port": 3000},
            "vue": {"name": "Vue", "type": "frontend", "port": 5173},
            "svelte": {"name": "Svelte", "type": "frontend", "port": 5173},
            "@sveltejs/kit": {"name": "SvelteKit", "type": "frontend", "port": 5173},
            "angular": {"name": "Angular", "type": "frontend", "port": 4200},
            "@angular/core": {"name": "Angular", "type": "frontend", "port": 4200},
            "solid-js": {"name": "SolidJS", "type": "frontend", "port": 3000},
            "astro": {"name": "Astro", "type": "frontend", "port": 4321},
        }

        # Backend frameworks
        backend_frameworks = {
            "express": {"name": "Express", "type": "backend", "port": 3000},
            "fastify": {"name": "Fastify", "type": "backend", "port": 3000},
            "koa": {"name": "Koa", "type": "backend", "port": 3000},
            "hono": {"name": "Hono", "type": "backend", "port": 3000},
            "elysia": {"name": "Elysia", "type": "backend", "port": 3000},
            "@nestjs/core": {"name": "NestJS", "type": "backend", "port": 3000},
        }

        # Check frontend first (Next.js includes React, etc.)
        for key, info in frontend_frameworks.items():
            if key in deps_lower:
                self.analysis["framework"] = info["name"]
                self.analysis["type"] = info["type"]
                self.analysis["default_port"] = info["port"]
                break

        # If no frontend, check backend
        if not self.analysis.get("framework"):
            for key, info in backend_frameworks.items():
                if key in deps_lower:
                    self.analysis["framework"] = info["name"]
                    self.analysis["type"] = info["type"]
                    self.analysis["default_port"] = info["port"]
                    break

        # Build tool
        if "vite" in deps_lower:
            self.analysis["build_tool"] = "Vite"
            if not self.analysis.get("default_port"):
                self.analysis["default_port"] = 5173
        elif "webpack" in deps_lower:
            self.analysis["build_tool"] = "Webpack"
        elif "esbuild" in deps_lower:
            self.analysis["build_tool"] = "esbuild"
        elif "turbopack" in deps_lower:
            self.analysis["build_tool"] = "Turbopack"

        # Styling
        if "tailwindcss" in deps_lower:
            self.analysis["styling"] = "Tailwind CSS"
        elif "styled-components" in deps_lower:
            self.analysis["styling"] = "styled-components"
        elif "@emotion/react" in deps_lower:
            self.analysis["styling"] = "Emotion"

        # State management
        if "zustand" in deps_lower:
            self.analysis["state_management"] = "Zustand"
        elif "@reduxjs/toolkit" in deps_lower or "redux" in deps_lower:
            self.analysis["state_management"] = "Redux"
        elif "jotai" in deps_lower:
            self.analysis["state_management"] = "Jotai"
        elif "pinia" in deps_lower:
            self.analysis["state_management"] = "Pinia"

        # Task queues
        if "bullmq" in deps_lower or "bull" in deps_lower:
            self.analysis["task_queue"] = "BullMQ"
            if not self.analysis.get("type"):
                self.analysis["type"] = "worker"

        # ORM
        if "@prisma/client" in deps_lower or "prisma" in deps_lower:
            self.analysis["orm"] = "Prisma"
        elif "typeorm" in deps_lower:
            self.analysis["orm"] = "TypeORM"
        elif "drizzle-orm" in deps_lower:
            self.analysis["orm"] = "Drizzle"
        elif "mongoose" in deps_lower:
            self.analysis["orm"] = "Mongoose"

        # Scripts
        scripts = pkg.get("scripts", {})
        if "dev" in scripts:
            self.analysis["dev_command"] = f"npm run dev"
        elif "start" in scripts:
            self.analysis["dev_command"] = f"npm run start"

    def _detect_go_framework(self, content: str) -> None:
        """Detect Go framework."""
        frameworks = {
            "gin-gonic/gin": {"name": "Gin", "port": 8080},
            "labstack/echo": {"name": "Echo", "port": 8080},
            "gofiber/fiber": {"name": "Fiber", "port": 3000},
            "go-chi/chi": {"name": "Chi", "port": 8080},
        }

        for key, info in frameworks.items():
            if key in content:
                self.analysis["framework"] = info["name"]
                self.analysis["type"] = "backend"
                self.analysis["default_port"] = info["port"]
                break

    def _detect_rust_framework(self, content: str) -> None:
        """Detect Rust framework."""
        frameworks = {
            "actix-web": {"name": "Actix Web", "port": 8080},
            "axum": {"name": "Axum", "port": 3000},
            "rocket": {"name": "Rocket", "port": 8000},
        }

        for key, info in frameworks.items():
            if key in content:
                self.analysis["framework"] = info["name"]
                self.analysis["type"] = "backend"
                self.analysis["default_port"] = info["port"]
                break

    def _detect_ruby_framework(self, content: str) -> None:
        """Detect Ruby framework."""
        if "rails" in content.lower():
            self.analysis["framework"] = "Ruby on Rails"
            self.analysis["type"] = "backend"
            self.analysis["default_port"] = 3000
        elif "sinatra" in content.lower():
            self.analysis["framework"] = "Sinatra"
            self.analysis["type"] = "backend"
            self.analysis["default_port"] = 4567

        if "sidekiq" in content.lower():
            self.analysis["task_queue"] = "Sidekiq"

    def _detect_service_type(self) -> None:
        """Infer service type from name and content if not already set."""
        if self.analysis.get("type"):
            return

        name_lower = self.name.lower()

        # Infer from name
        if any(kw in name_lower for kw in ["frontend", "client", "web", "ui", "app"]):
            self.analysis["type"] = "frontend"
        elif any(kw in name_lower for kw in ["backend", "api", "server", "service"]):
            self.analysis["type"] = "backend"
        elif any(kw in name_lower for kw in ["worker", "job", "queue", "task", "celery"]):
            self.analysis["type"] = "worker"
        elif any(kw in name_lower for kw in ["scraper", "crawler", "spider"]):
            self.analysis["type"] = "scraper"
        elif any(kw in name_lower for kw in ["proxy", "gateway", "router"]):
            self.analysis["type"] = "proxy"
        elif any(kw in name_lower for kw in ["lib", "shared", "common", "core", "utils"]):
            self.analysis["type"] = "library"
        else:
            self.analysis["type"] = "unknown"

    def _find_key_directories(self) -> None:
        """Find important directories within this service."""
        key_dirs = {}

        # Common directory patterns
        patterns = {
            "src": "Source code",
            "lib": "Library code",
            "app": "Application code",
            "api": "API endpoints",
            "routes": "Route handlers",
            "controllers": "Controllers",
            "models": "Data models",
            "schemas": "Schemas/DTOs",
            "services": "Business logic",
            "components": "UI components",
            "pages": "Page components",
            "views": "Views/templates",
            "hooks": "Custom hooks",
            "utils": "Utilities",
            "helpers": "Helper functions",
            "middleware": "Middleware",
            "tests": "Tests",
            "test": "Tests",
            "__tests__": "Tests",
            "config": "Configuration",
            "tasks": "Background tasks",
            "jobs": "Background jobs",
            "workers": "Worker processes",
        }

        for dir_name, purpose in patterns.items():
            dir_path = self.path / dir_name
            if dir_path.exists() and dir_path.is_dir():
                key_dirs[dir_name] = {
                    "path": str(dir_path.relative_to(self.path)),
                    "purpose": purpose,
                }

        if key_dirs:
            self.analysis["key_directories"] = key_dirs

    def _find_entry_points(self) -> None:
        """Find main entry point files."""
        entry_patterns = [
            "main.py", "app.py", "__main__.py", "server.py", "wsgi.py", "asgi.py",
            "index.ts", "index.js", "main.ts", "main.js", "server.ts", "server.js",
            "app.ts", "app.js", "src/index.ts", "src/index.js", "src/main.ts",
            "src/app.ts", "src/server.ts", "src/App.tsx", "src/App.jsx",
            "pages/_app.tsx", "pages/_app.js",  # Next.js
            "main.go", "cmd/main.go",
            "src/main.rs", "src/lib.rs",
        ]

        for pattern in entry_patterns:
            if self._exists(pattern):
                self.analysis["entry_point"] = pattern
                break

    def _detect_dependencies(self) -> None:
        """Extract key dependencies."""
        if self._exists("package.json"):
            pkg = self._read_json("package.json")
            if pkg:
                deps = pkg.get("dependencies", {})
                dev_deps = pkg.get("devDependencies", {})
                self.analysis["dependencies"] = list(deps.keys())[:20]  # Top 20
                self.analysis["dev_dependencies"] = list(dev_deps.keys())[:10]

        elif self._exists("requirements.txt"):
            content = self._read_file("requirements.txt")
            deps = []
            for line in content.split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    match = re.match(r"^([a-zA-Z0-9_-]+)", line)
                    if match:
                        deps.append(match.group(1))
            self.analysis["dependencies"] = deps[:20]

    def _detect_testing(self) -> None:
        """Detect testing framework and configuration."""
        if self._exists("package.json"):
            pkg = self._read_json("package.json")
            if pkg:
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "vitest" in deps:
                    self.analysis["testing"] = "Vitest"
                elif "jest" in deps:
                    self.analysis["testing"] = "Jest"
                if "@playwright/test" in deps:
                    self.analysis["e2e_testing"] = "Playwright"
                elif "cypress" in deps:
                    self.analysis["e2e_testing"] = "Cypress"

        elif self._exists("pytest.ini") or self._exists("pyproject.toml"):
            self.analysis["testing"] = "pytest"

        # Find test directory
        for test_dir in ["tests", "test", "__tests__", "spec"]:
            if self._exists(test_dir):
                self.analysis["test_directory"] = test_dir
                break

    def _find_dockerfile(self) -> None:
        """Find Dockerfile for this service."""
        dockerfile_patterns = [
            "Dockerfile",
            f"Dockerfile.{self.name}",
            f"docker/{self.name}.Dockerfile",
            f"docker/Dockerfile.{self.name}",
            "../docker/Dockerfile." + self.name,
        ]

        for pattern in dockerfile_patterns:
            if self._exists(pattern):
                self.analysis["dockerfile"] = pattern
                break

    def _detect_node_package_manager(self) -> str:
        """Detect Node.js package manager."""
        if self._exists("pnpm-lock.yaml"):
            return "pnpm"
        elif self._exists("yarn.lock"):
            return "yarn"
        elif self._exists("bun.lockb"):
            return "bun"
        return "npm"

    # Helper methods
    def _exists(self, path: str) -> bool:
        return (self.path / path).exists()

    def _read_file(self, path: str) -> str:
        try:
            return (self.path / path).read_text()
        except (IOError, UnicodeDecodeError):
            return ""

    def _read_json(self, path: str) -> dict | None:
        content = self._read_file(path)
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return None
        return None


class ProjectAnalyzer:
    """Analyzes an entire project, detecting monorepo structure and all services."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir.resolve()
        self.index = {
            "project_root": str(self.project_dir),
            "project_type": "single",  # or "monorepo"
            "services": {},
            "infrastructure": {},
            "conventions": {},
        }

    def analyze(self) -> dict[str, Any]:
        """Run full project analysis."""
        self._detect_project_type()
        self._find_and_analyze_services()
        self._analyze_infrastructure()
        self._detect_conventions()
        self._map_dependencies()
        return self.index

    def _detect_project_type(self) -> None:
        """Detect if this is a monorepo or single project."""
        monorepo_indicators = [
            "pnpm-workspace.yaml",
            "lerna.json",
            "nx.json",
            "turbo.json",
            "rush.json",
        ]

        for indicator in monorepo_indicators:
            if (self.project_dir / indicator).exists():
                self.index["project_type"] = "monorepo"
                self.index["monorepo_tool"] = indicator.replace(".json", "").replace(".yaml", "")
                return

        # Check for packages/apps directories
        if (self.project_dir / "packages").exists() or (self.project_dir / "apps").exists():
            self.index["project_type"] = "monorepo"
            return

        # Check for multiple service directories
        service_dirs_found = 0
        for item in self.project_dir.iterdir():
            if item.is_dir() and item.name in SERVICE_INDICATORS:
                if any((item / f).exists() for f in SERVICE_ROOT_FILES):
                    service_dirs_found += 1

        if service_dirs_found >= 2:
            self.index["project_type"] = "monorepo"

    def _find_and_analyze_services(self) -> None:
        """Find all services and analyze each."""
        services = {}

        if self.index["project_type"] == "monorepo":
            # Look for services in common locations
            service_locations = [
                self.project_dir,
                self.project_dir / "packages",
                self.project_dir / "apps",
                self.project_dir / "services",
            ]

            for location in service_locations:
                if not location.exists():
                    continue

                for item in location.iterdir():
                    if not item.is_dir():
                        continue
                    if item.name in SKIP_DIRS:
                        continue
                    if item.name.startswith("."):
                        continue

                    # Check if this looks like a service
                    has_root_file = any((item / f).exists() for f in SERVICE_ROOT_FILES)
                    is_service_name = item.name.lower() in SERVICE_INDICATORS

                    if has_root_file or (location == self.project_dir and is_service_name):
                        analyzer = ServiceAnalyzer(item, item.name)
                        service_info = analyzer.analyze()
                        if service_info.get("language"):  # Only include if we detected something
                            services[item.name] = service_info
        else:
            # Single project - analyze root
            analyzer = ServiceAnalyzer(self.project_dir, "main")
            service_info = analyzer.analyze()
            if service_info.get("language"):
                services["main"] = service_info

        self.index["services"] = services

    def _analyze_infrastructure(self) -> None:
        """Analyze infrastructure configuration."""
        infra = {}

        # Docker
        if (self.project_dir / "docker-compose.yml").exists():
            infra["docker_compose"] = "docker-compose.yml"
            compose_content = self._read_file("docker-compose.yml")
            infra["docker_services"] = self._parse_compose_services(compose_content)
        elif (self.project_dir / "docker-compose.yaml").exists():
            infra["docker_compose"] = "docker-compose.yaml"
            compose_content = self._read_file("docker-compose.yaml")
            infra["docker_services"] = self._parse_compose_services(compose_content)

        if (self.project_dir / "Dockerfile").exists():
            infra["dockerfile"] = "Dockerfile"

        # Docker directory
        docker_dir = self.project_dir / "docker"
        if docker_dir.exists():
            dockerfiles = list(docker_dir.glob("Dockerfile*")) + list(docker_dir.glob("*.Dockerfile"))
            if dockerfiles:
                infra["docker_directory"] = "docker/"
                infra["dockerfiles"] = [str(f.relative_to(self.project_dir)) for f in dockerfiles]

        # CI/CD
        if (self.project_dir / ".github" / "workflows").exists():
            infra["ci"] = "GitHub Actions"
            workflows = list((self.project_dir / ".github" / "workflows").glob("*.yml"))
            infra["ci_workflows"] = [f.name for f in workflows]
        elif (self.project_dir / ".gitlab-ci.yml").exists():
            infra["ci"] = "GitLab CI"
        elif (self.project_dir / ".circleci").exists():
            infra["ci"] = "CircleCI"

        # Deployment
        deployment_files = {
            "vercel.json": "Vercel",
            "netlify.toml": "Netlify",
            "fly.toml": "Fly.io",
            "render.yaml": "Render",
            "railway.json": "Railway",
            "Procfile": "Heroku",
            "app.yaml": "Google App Engine",
            "serverless.yml": "Serverless Framework",
        }

        for file, platform in deployment_files.items():
            if (self.project_dir / file).exists():
                infra["deployment"] = platform
                break

        self.index["infrastructure"] = infra

    def _parse_compose_services(self, content: str) -> list[str]:
        """Extract service names from docker-compose content."""
        services = []
        in_services = False
        for line in content.split("\n"):
            if line.strip() == "services:":
                in_services = True
                continue
            if in_services:
                # Service names are at 2-space indent
                if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
                    service_name = line.strip().rstrip(":")
                    services.append(service_name)
                elif line and not line.startswith(" "):
                    break  # End of services section
        return services

    def _detect_conventions(self) -> None:
        """Detect project-wide conventions."""
        conventions = {}

        # Python linting
        if (self.project_dir / "ruff.toml").exists() or self._has_in_pyproject("ruff"):
            conventions["python_linting"] = "Ruff"
        elif (self.project_dir / ".flake8").exists():
            conventions["python_linting"] = "Flake8"
        elif (self.project_dir / "pylintrc").exists():
            conventions["python_linting"] = "Pylint"

        # Python formatting
        if (self.project_dir / "pyproject.toml").exists():
            content = self._read_file("pyproject.toml")
            if "[tool.black]" in content:
                conventions["python_formatting"] = "Black"

        # JavaScript/TypeScript linting
        eslint_files = [".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", "eslint.config.js"]
        if any((self.project_dir / f).exists() for f in eslint_files):
            conventions["js_linting"] = "ESLint"

        # Prettier
        prettier_files = [".prettierrc", ".prettierrc.js", ".prettierrc.json", "prettier.config.js"]
        if any((self.project_dir / f).exists() for f in prettier_files):
            conventions["formatting"] = "Prettier"

        # TypeScript
        if (self.project_dir / "tsconfig.json").exists():
            conventions["typescript"] = True

        # Git hooks
        if (self.project_dir / ".husky").exists():
            conventions["git_hooks"] = "Husky"
        elif (self.project_dir / ".pre-commit-config.yaml").exists():
            conventions["git_hooks"] = "pre-commit"

        self.index["conventions"] = conventions

    def _map_dependencies(self) -> None:
        """Map dependencies between services."""
        services = self.index.get("services", {})

        for service_name, service_info in services.items():
            consumes = []

            # Check for API client patterns
            if service_info.get("type") == "frontend":
                # Frontend typically consumes backend
                for other_name, other_info in services.items():
                    if other_info.get("type") == "backend":
                        consumes.append(f"{other_name}.api")

            # Check for shared libraries
            if service_info.get("dependencies"):
                deps = service_info["dependencies"]
                for other_name in services.keys():
                    if other_name in deps or f"@{other_name}" in str(deps):
                        consumes.append(other_name)

            if consumes:
                service_info["consumes"] = consumes

    def _has_in_pyproject(self, tool: str) -> bool:
        """Check if a tool is configured in pyproject.toml."""
        if (self.project_dir / "pyproject.toml").exists():
            content = self._read_file("pyproject.toml")
            return f"[tool.{tool}]" in content
        return False

    def _read_file(self, path: str) -> str:
        try:
            return (self.project_dir / path).read_text()
        except (IOError, UnicodeDecodeError):
            return ""


def analyze_project(project_dir: Path, output_file: Path | None = None) -> dict:
    """
    Analyze a project and optionally save results.

    Args:
        project_dir: Path to the project root
        output_file: Optional path to save JSON output

    Returns:
        Project index as a dictionary
    """
    analyzer = ProjectAnalyzer(project_dir)
    results = analyzer.analyze()

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Project index saved to: {output_file}")

    return results


def analyze_service(project_dir: Path, service_name: str, output_file: Path | None = None) -> dict:
    """
    Analyze a specific service within a project.

    Args:
        project_dir: Path to the project root
        service_name: Name of the service to analyze
        output_file: Optional path to save JSON output

    Returns:
        Service analysis as a dictionary
    """
    # Find the service
    service_path = project_dir / service_name
    if not service_path.exists():
        # Check common locations
        for parent in ["packages", "apps", "services"]:
            candidate = project_dir / parent / service_name
            if candidate.exists():
                service_path = candidate
                break

    if not service_path.exists():
        raise ValueError(f"Service '{service_name}' not found in {project_dir}")

    analyzer = ServiceAnalyzer(service_path, service_name)
    results = analyzer.analyze()

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Service analysis saved to: {output_file}")

    return results


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze project structure, frameworks, and services"
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Project directory to analyze (default: current directory)",
    )
    parser.add_argument(
        "--index",
        action="store_true",
        help="Create full project index (default behavior)",
    )
    parser.add_argument(
        "--service",
        type=str,
        default=None,
        help="Analyze a specific service only",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file for JSON results",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only output JSON, no status messages",
    )

    args = parser.parse_args()

    # Determine what to analyze
    if args.service:
        results = analyze_service(args.project_dir, args.service, args.output)
    else:
        results = analyze_project(args.project_dir, args.output)

    # Print results
    if not args.quiet or not args.output:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
