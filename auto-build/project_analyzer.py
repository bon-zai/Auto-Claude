"""
Smart Project Analyzer for Dynamic Security Profiles
=====================================================

Analyzes project structure to automatically determine which commands
should be allowed for safe autonomous development.

This system:
1. Detects languages, frameworks, databases, and infrastructure
2. Parses package.json scripts, Makefile targets, pyproject.toml scripts
3. Builds a tailored security profile for the specific project
4. Caches the profile for subsequent runs
5. Can re-analyze when project structure changes

The goal: Allow an AI developer to run any command that's legitimately
needed for the detected tech stack, while blocking dangerous operations.
"""

import hashlib
import json
import os
import re
import tomllib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


# =============================================================================
# COMMAND REGISTRIES - Maps technologies to their associated commands
# =============================================================================

# Commands that are ALWAYS safe regardless of project type
BASE_COMMANDS = {
    # Core shell
    "echo", "printf", "cat", "head", "tail", "less", "more",
    "ls", "pwd", "cd", "pushd", "popd",
    "cp", "mv", "mkdir", "rmdir", "touch", "ln",
    "find", "fd", "grep", "egrep", "fgrep", "rg", "ag",
    "sort", "uniq", "cut", "tr", "sed", "awk", "gawk",
    "wc", "diff", "cmp", "comm",
    "tee", "xargs", "read",
    "file", "stat", "tree", "du", "df",
    "which", "whereis", "type", "command",
    "date", "time", "sleep", "timeout", "watch",
    "true", "false", "test", "[", "[[",
    "env", "printenv", "export", "unset", "set", "source", ".",
    "eval", "exec", "exit", "return", "break", "continue",
    "sh", "bash", "zsh",
    # Archives
    "tar", "zip", "unzip", "gzip", "gunzip",
    # Network (read-only)
    "curl", "wget", "ping", "host", "dig",
    # Git (always needed)
    "git", "gh",
    # Process management (with validation in security.py)
    "ps", "pgrep", "lsof", "jobs",
    "kill", "pkill", "killall",  # Validated for safe targets only
    # File operations (with validation in security.py)
    "rm", "chmod",  # Validated for safe operations only
    # Text tools
    "paste", "join", "split", "fold", "fmt", "nl", "rev", "shuf",
    "column", "expand", "unexpand", "iconv",
    # Misc safe
    "clear", "reset", "man", "help", "uname", "whoami", "id",
    "basename", "dirname", "realpath", "readlink", "mktemp",
    "bc", "expr", "let", "seq", "yes",
    "jq", "yq",
}

# Commands that need extra validation even when allowed
VALIDATED_COMMANDS = {
    "rm": "validate_rm",
    "chmod": "validate_chmod",
    "pkill": "validate_pkill",
    "kill": "validate_kill",
    "killall": "validate_killall",
}

# Language-specific commands
LANGUAGE_COMMANDS = {
    "python": {
        "python", "python3", "pip", "pip3", "pipx",
        "ipython", "jupyter", "notebook",
        "pdb", "pudb",  # debuggers
    },
    "javascript": {
        "node", "npm", "npx",
    },
    "typescript": {
        "tsc", "ts-node", "tsx",
    },
    "rust": {
        "cargo", "rustc", "rustup", "rustfmt", "clippy",
        "rust-analyzer",
    },
    "go": {
        "go", "gofmt", "golint", "gopls",
        "go-outline", "gocode", "gotests",
    },
    "ruby": {
        "ruby", "gem", "irb", "erb",
    },
    "php": {
        "php", "composer",
    },
    "java": {
        "java", "javac", "jar",
        "mvn", "maven", "gradle", "gradlew", "ant",
    },
    "kotlin": {
        "kotlin", "kotlinc",
    },
    "scala": {
        "scala", "scalac", "sbt",
    },
    "csharp": {
        "dotnet", "nuget", "msbuild",
    },
    "c": {
        "gcc", "g++", "clang", "clang++",
        "make", "cmake", "ninja", "meson",
        "ld", "ar", "nm", "objdump", "strip",
    },
    "cpp": {
        "gcc", "g++", "clang", "clang++",
        "make", "cmake", "ninja", "meson",
        "ld", "ar", "nm", "objdump", "strip",
    },
    "elixir": {
        "elixir", "mix", "iex",
    },
    "haskell": {
        "ghc", "ghci", "cabal", "stack",
    },
    "lua": {
        "lua", "luac", "luarocks",
    },
    "perl": {
        "perl", "cpan", "cpanm",
    },
    "swift": {
        "swift", "swiftc", "xcodebuild",
    },
    "zig": {
        "zig",
    },
}

# Package manager commands
PACKAGE_MANAGER_COMMANDS = {
    "npm": {"npm", "npx"},
    "yarn": {"yarn"},
    "pnpm": {"pnpm", "pnpx"},
    "bun": {"bun", "bunx"},
    "deno": {"deno"},
    "pip": {"pip", "pip3"},
    "poetry": {"poetry"},
    "uv": {"uv", "uvx"},
    "pdm": {"pdm"},
    "hatch": {"hatch"},
    "pipenv": {"pipenv"},
    "conda": {"conda", "mamba"},
    "cargo": {"cargo"},
    "go_mod": {"go"},
    "gem": {"gem", "bundle", "bundler"},
    "composer": {"composer"},
    "maven": {"mvn", "maven"},
    "gradle": {"gradle", "gradlew"},
    "nuget": {"nuget", "dotnet"},
    "brew": {"brew"},
    "apt": {"apt", "apt-get", "dpkg"},
    "nix": {"nix", "nix-shell", "nix-build", "nix-env"},
}

# Framework-specific commands
FRAMEWORK_COMMANDS = {
    # Python web frameworks
    "flask": {"flask", "gunicorn", "waitress", "gevent"},
    "django": {"django-admin", "gunicorn", "daphne", "uvicorn"},
    "fastapi": {"uvicorn", "gunicorn", "hypercorn"},
    "starlette": {"uvicorn", "gunicorn"},
    "tornado": {"tornado"},
    "bottle": {"bottle"},
    "pyramid": {"pserve", "pyramid"},
    "sanic": {"sanic"},
    "aiohttp": {"aiohttp"},

    # Python data/ML
    "celery": {"celery"},
    "dramatiq": {"dramatiq"},
    "rq": {"rq", "rqworker"},
    "airflow": {"airflow"},
    "prefect": {"prefect"},
    "dagster": {"dagster", "dagit"},
    "dbt": {"dbt"},
    "streamlit": {"streamlit"},
    "gradio": {"gradio"},
    "panel": {"panel"},
    "dash": {"dash"},

    # Python testing/linting
    "pytest": {"pytest", "py.test"},
    "unittest": {"python", "python3"},
    "nose": {"nosetests"},
    "tox": {"tox"},
    "nox": {"nox"},
    "mypy": {"mypy"},
    "pyright": {"pyright"},
    "ruff": {"ruff"},
    "black": {"black"},
    "isort": {"isort"},
    "flake8": {"flake8"},
    "pylint": {"pylint"},
    "bandit": {"bandit"},
    "coverage": {"coverage"},
    "pre-commit": {"pre-commit"},

    # Python DB migrations
    "alembic": {"alembic"},
    "flask-migrate": {"flask"},
    "django-migrations": {"django-admin"},

    # Node.js frameworks
    "nextjs": {"next"},
    "nuxt": {"nuxt", "nuxi"},
    "react": {"react-scripts"},
    "vue": {"vue-cli-service", "vite"},
    "angular": {"ng"},
    "svelte": {"svelte-kit", "vite"},
    "astro": {"astro"},
    "remix": {"remix"},
    "gatsby": {"gatsby"},
    "express": {"express"},
    "nestjs": {"nest"},
    "fastify": {"fastify"},
    "koa": {"koa"},
    "hapi": {"hapi"},
    "adonis": {"adonis", "ace"},
    "strapi": {"strapi"},
    "keystone": {"keystone"},
    "payload": {"payload"},
    "directus": {"directus"},
    "medusa": {"medusa"},
    "blitz": {"blitz"},
    "redwood": {"rw", "redwood"},
    "sails": {"sails"},
    "meteor": {"meteor"},
    "electron": {"electron", "electron-builder"},
    "tauri": {"tauri"},
    "capacitor": {"cap", "capacitor"},
    "expo": {"expo", "eas"},
    "react-native": {"react-native", "npx"},

    # Node.js build tools
    "vite": {"vite"},
    "webpack": {"webpack", "webpack-cli"},
    "rollup": {"rollup"},
    "esbuild": {"esbuild"},
    "parcel": {"parcel"},
    "turbo": {"turbo"},
    "nx": {"nx"},
    "lerna": {"lerna"},
    "rush": {"rush"},
    "changesets": {"changeset"},

    # Node.js testing/linting
    "jest": {"jest"},
    "vitest": {"vitest"},
    "mocha": {"mocha"},
    "jasmine": {"jasmine"},
    "ava": {"ava"},
    "playwright": {"playwright"},
    "cypress": {"cypress"},
    "puppeteer": {"puppeteer"},
    "eslint": {"eslint"},
    "prettier": {"prettier"},
    "biome": {"biome"},
    "oxlint": {"oxlint"},
    "stylelint": {"stylelint"},
    "tslint": {"tslint"},
    "standard": {"standard"},
    "xo": {"xo"},

    # Node.js ORMs/Database tools (also in DATABASE_COMMANDS for when detected via DB)
    "prisma": {"prisma", "npx"},
    "drizzle": {"drizzle-kit", "npx"},
    "typeorm": {"typeorm", "npx"},
    "sequelize": {"sequelize", "npx"},
    "knex": {"knex", "npx"},

    # Ruby frameworks
    "rails": {"rails", "rake", "spring"},
    "sinatra": {"sinatra", "rackup"},
    "hanami": {"hanami"},
    "rspec": {"rspec"},
    "minitest": {"rake"},
    "rubocop": {"rubocop"},

    # PHP frameworks
    "laravel": {"artisan", "sail"},
    "symfony": {"symfony", "console"},
    "wordpress": {"wp"},
    "drupal": {"drush"},
    "phpunit": {"phpunit"},
    "phpstan": {"phpstan"},
    "psalm": {"psalm"},

    # Rust frameworks
    "actix": {"cargo"},
    "rocket": {"cargo"},
    "axum": {"cargo"},
    "warp": {"cargo"},
    "tokio": {"cargo"},

    # Go frameworks
    "gin": {"go"},
    "echo": {"go"},
    "fiber": {"go"},
    "chi": {"go"},
    "buffalo": {"buffalo"},

    # Elixir/Erlang
    "phoenix": {"mix", "iex"},
    "ecto": {"mix"},
}

# Database commands
DATABASE_COMMANDS = {
    "postgresql": {
        "psql", "pg_dump", "pg_restore", "pg_dumpall",
        "createdb", "dropdb", "createuser", "dropuser",
        "pg_ctl", "postgres", "initdb", "pg_isready",
    },
    "mysql": {
        "mysql", "mysqldump", "mysqlimport", "mysqladmin",
        "mysqlcheck", "mysqlshow",
    },
    "mariadb": {
        "mysql", "mariadb", "mysqldump", "mariadb-dump",
    },
    "mongodb": {
        "mongosh", "mongo", "mongod", "mongos",
        "mongodump", "mongorestore", "mongoexport", "mongoimport",
    },
    "redis": {
        "redis-cli", "redis-server", "redis-benchmark",
    },
    "sqlite": {
        "sqlite3", "sqlite",
    },
    "cassandra": {
        "cqlsh", "cassandra", "nodetool",
    },
    "elasticsearch": {
        "elasticsearch", "curl",  # ES uses REST API
    },
    "neo4j": {
        "cypher-shell", "neo4j", "neo4j-admin",
    },
    "dynamodb": {
        "aws",  # DynamoDB uses AWS CLI
    },
    "cockroachdb": {
        "cockroach",
    },
    "clickhouse": {
        "clickhouse-client", "clickhouse-local",
    },
    "influxdb": {
        "influx", "influxd",
    },
    "timescaledb": {
        "psql",  # TimescaleDB uses PostgreSQL
    },
    "prisma": {
        "prisma", "npx",
    },
    "drizzle": {
        "drizzle-kit", "npx",
    },
    "typeorm": {
        "typeorm", "npx",
    },
    "sequelize": {
        "sequelize", "npx",
    },
    "knex": {
        "knex", "npx",
    },
    "sqlalchemy": {
        "alembic", "python", "python3",
    },
}

# Infrastructure/DevOps commands
INFRASTRUCTURE_COMMANDS = {
    "docker": {
        "docker", "docker-compose", "docker-buildx",
        "dockerfile", "dive",  # Dockerfile analysis
    },
    "podman": {
        "podman", "podman-compose", "buildah",
    },
    "kubernetes": {
        "kubectl", "k9s", "kubectx", "kubens",
        "kustomize", "kubeseal", "kubeadm",
    },
    "helm": {
        "helm", "helmfile",
    },
    "terraform": {
        "terraform", "terragrunt", "tflint", "tfsec",
    },
    "pulumi": {
        "pulumi",
    },
    "ansible": {
        "ansible", "ansible-playbook", "ansible-galaxy",
        "ansible-vault", "ansible-lint",
    },
    "vagrant": {
        "vagrant",
    },
    "packer": {
        "packer",
    },
    "minikube": {
        "minikube",
    },
    "kind": {
        "kind",
    },
    "k3d": {
        "k3d",
    },
    "skaffold": {
        "skaffold",
    },
    "argocd": {
        "argocd",
    },
    "flux": {
        "flux",
    },
    "istio": {
        "istioctl",
    },
    "linkerd": {
        "linkerd",
    },
}

# Cloud provider CLIs
CLOUD_COMMANDS = {
    "aws": {
        "aws", "sam", "cdk", "amplify", "eb",  # AWS CLI, SAM, CDK, Amplify, Elastic Beanstalk
    },
    "gcp": {
        "gcloud", "gsutil", "bq", "firebase",
    },
    "azure": {
        "az", "func",  # Azure CLI, Azure Functions
    },
    "vercel": {
        "vercel", "vc",
    },
    "netlify": {
        "netlify", "ntl",
    },
    "heroku": {
        "heroku",
    },
    "railway": {
        "railway",
    },
    "fly": {
        "fly", "flyctl",
    },
    "render": {
        "render",
    },
    "cloudflare": {
        "wrangler", "cloudflared",
    },
    "digitalocean": {
        "doctl",
    },
    "linode": {
        "linode-cli",
    },
    "supabase": {
        "supabase",
    },
    "planetscale": {
        "pscale",
    },
    "neon": {
        "neonctl",
    },
}

# Code quality tools
CODE_QUALITY_COMMANDS = {
    "shellcheck": {"shellcheck"},
    "hadolint": {"hadolint"},
    "actionlint": {"actionlint"},
    "yamllint": {"yamllint"},
    "jsonlint": {"jsonlint"},
    "markdownlint": {"markdownlint", "markdownlint-cli"},
    "vale": {"vale"},
    "cspell": {"cspell"},
    "codespell": {"codespell"},
    "cloc": {"cloc"},
    "scc": {"scc"},
    "tokei": {"tokei"},
    "git-secrets": {"git-secrets"},
    "gitleaks": {"gitleaks"},
    "trufflehog": {"trufflehog"},
    "detect-secrets": {"detect-secrets"},
    "semgrep": {"semgrep"},
    "snyk": {"snyk"},
    "trivy": {"trivy"},
    "grype": {"grype"},
    "syft": {"syft"},
    "dockle": {"dockle"},
}

# Version managers
VERSION_MANAGER_COMMANDS = {
    "asdf": {"asdf"},
    "mise": {"mise"},
    "nvm": {"nvm"},
    "fnm": {"fnm"},
    "n": {"n"},
    "pyenv": {"pyenv"},
    "rbenv": {"rbenv"},
    "rvm": {"rvm"},
    "goenv": {"goenv"},
    "rustup": {"rustup"},
    "sdkman": {"sdk"},
    "jabba": {"jabba"},
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class TechnologyStack:
    """Detected technologies in a project."""
    languages: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)
    infrastructure: list[str] = field(default_factory=list)
    cloud_providers: list[str] = field(default_factory=list)
    code_quality_tools: list[str] = field(default_factory=list)
    version_managers: list[str] = field(default_factory=list)


@dataclass
class CustomScripts:
    """Detected custom scripts in the project."""
    npm_scripts: list[str] = field(default_factory=list)
    make_targets: list[str] = field(default_factory=list)
    poetry_scripts: list[str] = field(default_factory=list)
    cargo_aliases: list[str] = field(default_factory=list)
    shell_scripts: list[str] = field(default_factory=list)


@dataclass
class SecurityProfile:
    """Complete security profile for a project."""
    # Command sets
    base_commands: set[str] = field(default_factory=set)
    stack_commands: set[str] = field(default_factory=set)
    script_commands: set[str] = field(default_factory=set)
    custom_commands: set[str] = field(default_factory=set)

    # Detected info
    detected_stack: TechnologyStack = field(default_factory=TechnologyStack)
    custom_scripts: CustomScripts = field(default_factory=CustomScripts)

    # Metadata
    project_dir: str = ""
    created_at: str = ""
    project_hash: str = ""

    def get_all_allowed_commands(self) -> set[str]:
        """Get the complete set of allowed commands."""
        return (
            self.base_commands |
            self.stack_commands |
            self.script_commands |
            self.custom_commands
        )

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "base_commands": sorted(self.base_commands),
            "stack_commands": sorted(self.stack_commands),
            "script_commands": sorted(self.script_commands),
            "custom_commands": sorted(self.custom_commands),
            "detected_stack": asdict(self.detected_stack),
            "custom_scripts": asdict(self.custom_scripts),
            "project_dir": self.project_dir,
            "created_at": self.created_at,
            "project_hash": self.project_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SecurityProfile":
        """Load from dict."""
        profile = cls(
            base_commands=set(data.get("base_commands", [])),
            stack_commands=set(data.get("stack_commands", [])),
            script_commands=set(data.get("script_commands", [])),
            custom_commands=set(data.get("custom_commands", [])),
            project_dir=data.get("project_dir", ""),
            created_at=data.get("created_at", ""),
            project_hash=data.get("project_hash", ""),
        )

        if "detected_stack" in data:
            profile.detected_stack = TechnologyStack(**data["detected_stack"])
        if "custom_scripts" in data:
            profile.custom_scripts = CustomScripts(**data["custom_scripts"])

        return profile


# =============================================================================
# PROJECT ANALYZER
# =============================================================================

class ProjectAnalyzer:
    """
    Analyzes a project's structure to determine safe commands.

    Detection methods:
    1. File extensions and patterns
    2. Config file presence (package.json, pyproject.toml, etc.)
    3. Dependency parsing (frameworks, libraries)
    4. Script detection (npm scripts, Makefile targets)
    5. Infrastructure files (Dockerfile, k8s manifests)
    """

    PROFILE_FILENAME = ".auto-build-security.json"
    CUSTOM_ALLOWLIST_FILENAME = ".auto-build-allowlist"

    def __init__(self, project_dir: Path, spec_dir: Optional[Path] = None):
        """
        Initialize analyzer.

        Args:
            project_dir: Root directory of the project
            spec_dir: Optional spec directory for storing profile
        """
        self.project_dir = Path(project_dir).resolve()
        self.spec_dir = Path(spec_dir).resolve() if spec_dir else None
        self.profile = SecurityProfile()

    def get_profile_path(self) -> Path:
        """Get the path where profile should be stored."""
        if self.spec_dir:
            return self.spec_dir / self.PROFILE_FILENAME
        return self.project_dir / self.PROFILE_FILENAME

    def load_profile(self) -> Optional[SecurityProfile]:
        """Load existing profile if it exists."""
        profile_path = self.get_profile_path()
        if not profile_path.exists():
            return None

        try:
            with open(profile_path, "r") as f:
                data = json.load(f)
            return SecurityProfile.from_dict(data)
        except (json.JSONDecodeError, IOError, KeyError):
            return None

    def save_profile(self, profile: SecurityProfile) -> None:
        """Save profile to disk."""
        profile_path = self.get_profile_path()
        profile_path.parent.mkdir(parents=True, exist_ok=True)

        with open(profile_path, "w") as f:
            json.dump(profile.to_dict(), f, indent=2)

    def compute_project_hash(self) -> str:
        """
        Compute a hash of key project files to detect changes.

        This allows us to know when to re-analyze.
        """
        hash_files = [
            "package.json",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "pyproject.toml",
            "requirements.txt",
            "Pipfile",
            "poetry.lock",
            "Cargo.toml",
            "Cargo.lock",
            "go.mod",
            "go.sum",
            "Gemfile",
            "Gemfile.lock",
            "composer.json",
            "composer.lock",
            "Makefile",
            "Dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
        ]

        hasher = hashlib.md5()
        files_found = 0

        for filename in hash_files:
            filepath = self.project_dir / filename
            if filepath.exists():
                try:
                    stat = filepath.stat()
                    hasher.update(f"{filename}:{stat.st_mtime}:{stat.st_size}".encode())
                    files_found += 1
                except OSError:
                    pass

        # If no config files found, hash the project directory structure
        # to at least detect when files are added/removed
        if files_found == 0:
            # Count Python, JS, and other source files as a proxy for project structure
            for ext in ["*.py", "*.js", "*.ts", "*.go", "*.rs"]:
                count = len(list(self.project_dir.glob(f"**/{ext}")))
                hasher.update(f"{ext}:{count}".encode())
            # Also include the project directory name for uniqueness
            hasher.update(self.project_dir.name.encode())

        return hasher.hexdigest()

    def should_reanalyze(self, profile: SecurityProfile) -> bool:
        """Check if project has changed since last analysis."""
        current_hash = self.compute_project_hash()
        return current_hash != profile.project_hash

    def analyze(self, force: bool = False) -> SecurityProfile:
        """
        Perform full project analysis.

        Args:
            force: Force re-analysis even if profile exists

        Returns:
            SecurityProfile with all detected commands
        """
        # Check for existing profile
        existing = self.load_profile()
        if existing and not force and not self.should_reanalyze(existing):
            print(f"Using cached security profile (hash: {existing.project_hash[:8]})")
            return existing

        print("Analyzing project structure for security profile...")

        # Start fresh
        self.profile = SecurityProfile()
        self.profile.base_commands = BASE_COMMANDS.copy()
        self.profile.project_dir = str(self.project_dir)

        # Run all detection methods
        self._detect_languages()
        self._detect_package_managers()
        self._detect_frameworks()
        self._detect_databases()
        self._detect_infrastructure()
        self._detect_cloud_providers()
        self._detect_code_quality_tools()
        self._detect_version_managers()
        self._detect_custom_scripts()
        self._load_custom_allowlist()

        # Build stack commands from detected technologies
        self._build_stack_commands()

        # Finalize
        self.profile.created_at = datetime.now().isoformat()
        self.profile.project_hash = self.compute_project_hash()

        # Save
        self.save_profile(self.profile)

        # Print summary
        self._print_summary()

        return self.profile

    def _file_exists(self, *paths: str) -> bool:
        """Check if any of the given files/patterns exist."""
        for p in paths:
            # Handle glob patterns
            if "*" in p:
                if list(self.project_dir.glob(p)):
                    return True
            else:
                if (self.project_dir / p).exists():
                    return True
        return False

    def _read_json(self, filename: str) -> Optional[dict]:
        """Read a JSON file from project root."""
        try:
            with open(self.project_dir / filename, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _read_toml(self, filename: str) -> Optional[dict]:
        """Read a TOML file from project root."""
        try:
            with open(self.project_dir / filename, "rb") as f:
                return tomllib.load(f)
        except (FileNotFoundError, tomllib.TOMLDecodeError):
            return None

    def _glob_files(self, pattern: str) -> list[Path]:
        """Find files matching a pattern."""
        return list(self.project_dir.glob(pattern))

    def _detect_languages(self) -> None:
        """Detect programming languages used."""
        stack = self.profile.detected_stack

        # Python
        if self._file_exists("*.py", "**/*.py", "pyproject.toml", "requirements.txt", "setup.py", "Pipfile"):
            stack.languages.append("python")

        # JavaScript
        if self._file_exists("*.js", "**/*.js", "package.json"):
            stack.languages.append("javascript")

        # TypeScript
        if self._file_exists("*.ts", "*.tsx", "**/*.ts", "**/*.tsx", "tsconfig.json"):
            stack.languages.append("typescript")

        # Rust
        if self._file_exists("Cargo.toml", "*.rs", "**/*.rs"):
            stack.languages.append("rust")

        # Go
        if self._file_exists("go.mod", "*.go", "**/*.go"):
            stack.languages.append("go")

        # Ruby
        if self._file_exists("Gemfile", "*.rb", "**/*.rb"):
            stack.languages.append("ruby")

        # PHP
        if self._file_exists("composer.json", "*.php", "**/*.php"):
            stack.languages.append("php")

        # Java
        if self._file_exists("pom.xml", "build.gradle", "*.java", "**/*.java"):
            stack.languages.append("java")

        # Kotlin
        if self._file_exists("*.kt", "**/*.kt"):
            stack.languages.append("kotlin")

        # Scala
        if self._file_exists("build.sbt", "*.scala", "**/*.scala"):
            stack.languages.append("scala")

        # C#
        if self._file_exists("*.csproj", "*.sln", "*.cs", "**/*.cs"):
            stack.languages.append("csharp")

        # C/C++
        if self._file_exists("*.c", "*.h", "**/*.c", "**/*.h", "CMakeLists.txt", "Makefile"):
            stack.languages.append("c")
        if self._file_exists("*.cpp", "*.hpp", "*.cc", "**/*.cpp", "**/*.hpp"):
            stack.languages.append("cpp")

        # Elixir
        if self._file_exists("mix.exs", "*.ex", "**/*.ex"):
            stack.languages.append("elixir")

        # Swift
        if self._file_exists("Package.swift", "*.swift", "**/*.swift"):
            stack.languages.append("swift")

    def _detect_package_managers(self) -> None:
        """Detect package managers used."""
        stack = self.profile.detected_stack

        # Node.js package managers
        if self._file_exists("package-lock.json"):
            stack.package_managers.append("npm")
        if self._file_exists("yarn.lock"):
            stack.package_managers.append("yarn")
        if self._file_exists("pnpm-lock.yaml"):
            stack.package_managers.append("pnpm")
        if self._file_exists("bun.lockb"):
            stack.package_managers.append("bun")
        if self._file_exists("deno.json", "deno.jsonc"):
            stack.package_managers.append("deno")

        # Python package managers
        if self._file_exists("requirements.txt", "requirements-dev.txt"):
            stack.package_managers.append("pip")
        if self._file_exists("pyproject.toml"):
            toml = self._read_toml("pyproject.toml")
            if toml:
                if "tool" in toml and "poetry" in toml["tool"]:
                    stack.package_managers.append("poetry")
                elif "project" in toml:
                    # Modern pyproject.toml - could be pip, uv, hatch, pdm
                    if self._file_exists("uv.lock"):
                        stack.package_managers.append("uv")
                    elif self._file_exists("pdm.lock"):
                        stack.package_managers.append("pdm")
                    else:
                        stack.package_managers.append("pip")
        if self._file_exists("Pipfile"):
            stack.package_managers.append("pipenv")

        # Other package managers
        if self._file_exists("Cargo.toml"):
            stack.package_managers.append("cargo")
        if self._file_exists("go.mod"):
            stack.package_managers.append("go_mod")
        if self._file_exists("Gemfile"):
            stack.package_managers.append("gem")
        if self._file_exists("composer.json"):
            stack.package_managers.append("composer")
        if self._file_exists("pom.xml"):
            stack.package_managers.append("maven")
        if self._file_exists("build.gradle", "build.gradle.kts"):
            stack.package_managers.append("gradle")

    def _detect_frameworks(self) -> None:
        """Detect frameworks from dependencies."""
        stack = self.profile.detected_stack

        # Parse package.json for Node.js frameworks
        pkg = self._read_json("package.json")
        if pkg:
            deps = {
                **pkg.get("dependencies", {}),
                **pkg.get("devDependencies", {}),
            }

            # Detect Node.js frameworks
            framework_deps = {
                "next": "nextjs",
                "nuxt": "nuxt",
                "react": "react",
                "vue": "vue",
                "@angular/core": "angular",
                "svelte": "svelte",
                "@sveltejs/kit": "svelte",
                "astro": "astro",
                "@remix-run/react": "remix",
                "gatsby": "gatsby",
                "express": "express",
                "@nestjs/core": "nestjs",
                "fastify": "fastify",
                "koa": "koa",
                "@hapi/hapi": "hapi",
                "@adonisjs/core": "adonis",
                "strapi": "strapi",
                "@keystonejs/core": "keystone",
                "payload": "payload",
                "@directus/sdk": "directus",
                "@medusajs/medusa": "medusa",
                "blitz": "blitz",
                "@redwoodjs/core": "redwood",
                "sails": "sails",
                "meteor": "meteor",
                "electron": "electron",
                "@tauri-apps/api": "tauri",
                "@capacitor/core": "capacitor",
                "expo": "expo",
                "react-native": "react-native",
                # Build tools
                "vite": "vite",
                "webpack": "webpack",
                "rollup": "rollup",
                "esbuild": "esbuild",
                "parcel": "parcel",
                "turbo": "turbo",
                "nx": "nx",
                "lerna": "lerna",
                # Testing
                "jest": "jest",
                "vitest": "vitest",
                "mocha": "mocha",
                "@playwright/test": "playwright",
                "cypress": "cypress",
                "puppeteer": "puppeteer",
                # Linting
                "eslint": "eslint",
                "prettier": "prettier",
                "@biomejs/biome": "biome",
                "oxlint": "oxlint",
                # Database
                "prisma": "prisma",
                "drizzle-orm": "drizzle",
                "typeorm": "typeorm",
                "sequelize": "sequelize",
                "knex": "knex",
            }

            for dep, framework in framework_deps.items():
                if dep in deps:
                    stack.frameworks.append(framework)

        # Parse pyproject.toml / requirements.txt for Python frameworks
        python_deps = set()

        toml = self._read_toml("pyproject.toml")
        if toml:
            # Poetry style
            if "tool" in toml and "poetry" in toml.get("tool", {}):
                poetry = toml["tool"]["poetry"]
                python_deps.update(poetry.get("dependencies", {}).keys())
                python_deps.update(poetry.get("dev-dependencies", {}).keys())
                if "group" in poetry:
                    for group in poetry["group"].values():
                        python_deps.update(group.get("dependencies", {}).keys())

            # Modern pyproject.toml style
            if "project" in toml:
                for dep in toml["project"].get("dependencies", []):
                    # Parse "package>=1.0" style
                    match = re.match(r'^([a-zA-Z0-9_-]+)', dep)
                    if match:
                        python_deps.add(match.group(1).lower())

            # Optional dependencies
            if "project" in toml and "optional-dependencies" in toml["project"]:
                for group_deps in toml["project"]["optional-dependencies"].values():
                    for dep in group_deps:
                        match = re.match(r'^([a-zA-Z0-9_-]+)', dep)
                        if match:
                            python_deps.add(match.group(1).lower())

        # Parse requirements.txt
        for req_file in ["requirements.txt", "requirements-dev.txt", "requirements/dev.txt"]:
            req_path = self.project_dir / req_file
            if req_path.exists():
                try:
                    with open(req_path) as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and not line.startswith("-"):
                                match = re.match(r'^([a-zA-Z0-9_-]+)', line)
                                if match:
                                    python_deps.add(match.group(1).lower())
                except IOError:
                    pass

        # Detect Python frameworks from dependencies
        python_framework_deps = {
            "flask": "flask",
            "django": "django",
            "fastapi": "fastapi",
            "starlette": "starlette",
            "tornado": "tornado",
            "bottle": "bottle",
            "pyramid": "pyramid",
            "sanic": "sanic",
            "aiohttp": "aiohttp",
            "celery": "celery",
            "dramatiq": "dramatiq",
            "rq": "rq",
            "airflow": "airflow",
            "prefect": "prefect",
            "dagster": "dagster",
            "dbt-core": "dbt",
            "streamlit": "streamlit",
            "gradio": "gradio",
            "panel": "panel",
            "dash": "dash",
            "pytest": "pytest",
            "tox": "tox",
            "nox": "nox",
            "mypy": "mypy",
            "pyright": "pyright",
            "ruff": "ruff",
            "black": "black",
            "isort": "isort",
            "flake8": "flake8",
            "pylint": "pylint",
            "bandit": "bandit",
            "coverage": "coverage",
            "pre-commit": "pre-commit",
            "alembic": "alembic",
            "sqlalchemy": "sqlalchemy",
        }

        for dep, framework in python_framework_deps.items():
            if dep in python_deps:
                stack.frameworks.append(framework)

        # Ruby frameworks (Gemfile)
        if self._file_exists("Gemfile"):
            try:
                with open(self.project_dir / "Gemfile") as f:
                    content = f.read().lower()
                    if "rails" in content:
                        stack.frameworks.append("rails")
                    if "sinatra" in content:
                        stack.frameworks.append("sinatra")
                    if "rspec" in content:
                        stack.frameworks.append("rspec")
                    if "rubocop" in content:
                        stack.frameworks.append("rubocop")
            except IOError:
                pass

        # PHP frameworks (composer.json)
        composer = self._read_json("composer.json")
        if composer:
            deps = {
                **composer.get("require", {}),
                **composer.get("require-dev", {}),
            }
            if "laravel/framework" in deps:
                stack.frameworks.append("laravel")
            if "symfony/framework-bundle" in deps:
                stack.frameworks.append("symfony")
            if "phpunit/phpunit" in deps:
                stack.frameworks.append("phpunit")

    def _detect_databases(self) -> None:
        """Detect databases from config files and dependencies."""
        stack = self.profile.detected_stack

        # Check for database config files
        if self._file_exists(".env", ".env.local", ".env.development"):
            for env_file in [".env", ".env.local", ".env.development"]:
                env_path = self.project_dir / env_file
                if env_path.exists():
                    try:
                        with open(env_path) as f:
                            content = f.read().lower()
                            if "postgres" in content or "postgresql" in content:
                                stack.databases.append("postgresql")
                            if "mysql" in content:
                                stack.databases.append("mysql")
                            if "mongodb" in content or "mongo_" in content:
                                stack.databases.append("mongodb")
                            if "redis" in content:
                                stack.databases.append("redis")
                            if "sqlite" in content:
                                stack.databases.append("sqlite")
                    except IOError:
                        pass

        # Check for Prisma schema
        if self._file_exists("prisma/schema.prisma"):
            try:
                with open(self.project_dir / "prisma/schema.prisma") as f:
                    content = f.read().lower()
                    if "postgresql" in content:
                        stack.databases.append("postgresql")
                    if "mysql" in content:
                        stack.databases.append("mysql")
                    if "mongodb" in content:
                        stack.databases.append("mongodb")
                    if "sqlite" in content:
                        stack.databases.append("sqlite")
            except IOError:
                pass

        # Check Docker Compose for database services
        for compose_file in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
            compose_path = self.project_dir / compose_file
            if compose_path.exists():
                try:
                    with open(compose_path) as f:
                        content = f.read().lower()
                        if "postgres" in content:
                            stack.databases.append("postgresql")
                        if "mysql" in content or "mariadb" in content:
                            stack.databases.append("mysql")
                        if "mongo" in content:
                            stack.databases.append("mongodb")
                        if "redis" in content:
                            stack.databases.append("redis")
                        if "elasticsearch" in content:
                            stack.databases.append("elasticsearch")
                except IOError:
                    pass

        # Deduplicate
        stack.databases = list(set(stack.databases))

    def _detect_infrastructure(self) -> None:
        """Detect infrastructure tools."""
        stack = self.profile.detected_stack

        # Docker
        if self._file_exists("Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"):
            stack.infrastructure.append("docker")

        # Podman
        if self._file_exists("Containerfile"):
            stack.infrastructure.append("podman")

        # Kubernetes
        if self._file_exists("k8s/", "kubernetes/", "*.yaml") or self._glob_files("**/deployment.yaml"):
            # Check if YAML files contain k8s resources
            for yaml_file in self._glob_files("**/*.yaml") + self._glob_files("**/*.yml"):
                try:
                    with open(yaml_file) as f:
                        content = f.read()
                        if "apiVersion:" in content and "kind:" in content:
                            stack.infrastructure.append("kubernetes")
                            break
                except IOError:
                    pass

        # Helm
        if self._file_exists("Chart.yaml", "charts/"):
            stack.infrastructure.append("helm")

        # Terraform
        if self._glob_files("**/*.tf"):
            stack.infrastructure.append("terraform")

        # Ansible
        if self._file_exists("ansible.cfg", "playbook.yml", "playbooks/"):
            stack.infrastructure.append("ansible")

        # Vagrant
        if self._file_exists("Vagrantfile"):
            stack.infrastructure.append("vagrant")

        # Minikube
        if self._file_exists(".minikube/"):
            stack.infrastructure.append("minikube")

        # Deduplicate
        stack.infrastructure = list(set(stack.infrastructure))

    def _detect_cloud_providers(self) -> None:
        """Detect cloud provider usage."""
        stack = self.profile.detected_stack

        # AWS
        if self._file_exists("aws/", ".aws/", "serverless.yml", "sam.yaml", "template.yaml", "cdk.json", "amplify.yml"):
            stack.cloud_providers.append("aws")

        # GCP
        if self._file_exists("app.yaml", ".gcloudignore", "firebase.json", ".firebaserc"):
            stack.cloud_providers.append("gcp")

        # Azure
        if self._file_exists("azure-pipelines.yml", ".azure/", "host.json"):
            stack.cloud_providers.append("azure")

        # Vercel
        if self._file_exists("vercel.json", ".vercel/"):
            stack.cloud_providers.append("vercel")

        # Netlify
        if self._file_exists("netlify.toml", "_redirects"):
            stack.cloud_providers.append("netlify")

        # Heroku
        if self._file_exists("Procfile", "app.json"):
            stack.cloud_providers.append("heroku")

        # Railway
        if self._file_exists("railway.json", "railway.toml"):
            stack.cloud_providers.append("railway")

        # Fly.io
        if self._file_exists("fly.toml"):
            stack.cloud_providers.append("fly")

        # Cloudflare
        if self._file_exists("wrangler.toml", "wrangler.json"):
            stack.cloud_providers.append("cloudflare")

        # Supabase
        if self._file_exists("supabase/"):
            stack.cloud_providers.append("supabase")

    def _detect_code_quality_tools(self) -> None:
        """Detect code quality tools from config files."""
        stack = self.profile.detected_stack

        # Check for config files
        tool_configs = {
            ".shellcheckrc": "shellcheck",
            ".hadolint.yaml": "hadolint",
            ".yamllint": "yamllint",
            ".vale.ini": "vale",
            "cspell.json": "cspell",
            ".codespellrc": "codespell",
            ".semgrep.yml": "semgrep",
            ".snyk": "snyk",
            ".trivyignore": "trivy",
        }

        for config, tool in tool_configs.items():
            if self._file_exists(config):
                stack.code_quality_tools.append(tool)

    def _detect_version_managers(self) -> None:
        """Detect version managers."""
        stack = self.profile.detected_stack

        if self._file_exists(".tool-versions"):
            stack.version_managers.append("asdf")
        if self._file_exists(".mise.toml", "mise.toml"):
            stack.version_managers.append("mise")
        if self._file_exists(".nvmrc", ".node-version"):
            stack.version_managers.append("nvm")
        if self._file_exists(".python-version"):
            stack.version_managers.append("pyenv")
        if self._file_exists(".ruby-version"):
            stack.version_managers.append("rbenv")
        if self._file_exists("rust-toolchain.toml", "rust-toolchain"):
            stack.version_managers.append("rustup")

    def _detect_custom_scripts(self) -> None:
        """Detect custom scripts (npm scripts, Makefile targets, etc.)."""
        scripts = self.profile.custom_scripts

        # npm scripts from package.json
        pkg = self._read_json("package.json")
        if pkg and "scripts" in pkg:
            scripts.npm_scripts = list(pkg["scripts"].keys())

            # Add commands to run these scripts
            for script in scripts.npm_scripts:
                self.profile.script_commands.add(f"npm")
                self.profile.script_commands.add(f"yarn")
                self.profile.script_commands.add(f"pnpm")
                self.profile.script_commands.add(f"bun")

        # Makefile targets
        if self._file_exists("Makefile"):
            try:
                with open(self.project_dir / "Makefile") as f:
                    for line in f:
                        # Match target definitions like "target:" or "target: deps"
                        match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:', line)
                        if match:
                            target = match.group(1)
                            # Skip common internal targets
                            if not target.startswith('.'):
                                scripts.make_targets.append(target)

                if scripts.make_targets:
                    self.profile.script_commands.add("make")
            except IOError:
                pass

        # Poetry scripts from pyproject.toml
        toml = self._read_toml("pyproject.toml")
        if toml:
            # Poetry scripts
            if "tool" in toml and "poetry" in toml["tool"]:
                poetry_scripts = toml["tool"]["poetry"].get("scripts", {})
                scripts.poetry_scripts = list(poetry_scripts.keys())

            # PEP 621 scripts
            if "project" in toml and "scripts" in toml["project"]:
                scripts.poetry_scripts.extend(list(toml["project"]["scripts"].keys()))

        # Shell scripts in root
        for ext in ["*.sh", "*.bash"]:
            for script_path in self._glob_files(ext):
                script_name = script_path.name
                scripts.shell_scripts.append(script_name)
                # Allow executing these scripts
                self.profile.script_commands.add(f"./{script_name}")

    def _load_custom_allowlist(self) -> None:
        """Load user-defined custom allowlist."""
        allowlist_path = self.project_dir / self.CUSTOM_ALLOWLIST_FILENAME
        if not allowlist_path.exists():
            return

        try:
            with open(allowlist_path) as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if line and not line.startswith("#"):
                        self.profile.custom_commands.add(line)
        except IOError:
            pass

    def _build_stack_commands(self) -> None:
        """Build the set of allowed commands from detected stack."""
        stack = self.profile.detected_stack
        commands = self.profile.stack_commands

        # Add language commands
        for lang in stack.languages:
            if lang in LANGUAGE_COMMANDS:
                commands.update(LANGUAGE_COMMANDS[lang])

        # Add package manager commands
        for pm in stack.package_managers:
            if pm in PACKAGE_MANAGER_COMMANDS:
                commands.update(PACKAGE_MANAGER_COMMANDS[pm])

        # Add framework commands
        for fw in stack.frameworks:
            if fw in FRAMEWORK_COMMANDS:
                commands.update(FRAMEWORK_COMMANDS[fw])

        # Add database commands
        for db in stack.databases:
            if db in DATABASE_COMMANDS:
                commands.update(DATABASE_COMMANDS[db])

        # Add infrastructure commands
        for infra in stack.infrastructure:
            if infra in INFRASTRUCTURE_COMMANDS:
                commands.update(INFRASTRUCTURE_COMMANDS[infra])

        # Add cloud commands
        for cloud in stack.cloud_providers:
            if cloud in CLOUD_COMMANDS:
                commands.update(CLOUD_COMMANDS[cloud])

        # Add code quality commands
        for tool in stack.code_quality_tools:
            if tool in CODE_QUALITY_COMMANDS:
                commands.update(CODE_QUALITY_COMMANDS[tool])

        # Add version manager commands
        for vm in stack.version_managers:
            if vm in VERSION_MANAGER_COMMANDS:
                commands.update(VERSION_MANAGER_COMMANDS[vm])

    def _print_summary(self) -> None:
        """Print a summary of what was detected."""
        stack = self.profile.detected_stack
        scripts = self.profile.custom_scripts

        print("\n" + "=" * 60)
        print("  SECURITY PROFILE ANALYSIS")
        print("=" * 60)

        if stack.languages:
            print(f"\nLanguages: {', '.join(stack.languages)}")

        if stack.package_managers:
            print(f"Package Managers: {', '.join(stack.package_managers)}")

        if stack.frameworks:
            print(f"Frameworks: {', '.join(stack.frameworks)}")

        if stack.databases:
            print(f"Databases: {', '.join(stack.databases)}")

        if stack.infrastructure:
            print(f"Infrastructure: {', '.join(stack.infrastructure)}")

        if stack.cloud_providers:
            print(f"Cloud Providers: {', '.join(stack.cloud_providers)}")

        if scripts.npm_scripts:
            print(f"NPM Scripts: {len(scripts.npm_scripts)} detected")

        if scripts.make_targets:
            print(f"Make Targets: {len(scripts.make_targets)} detected")

        total_commands = len(self.profile.get_all_allowed_commands())
        print(f"\nTotal Allowed Commands: {total_commands}")

        print("-" * 60)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_or_create_profile(
    project_dir: Path,
    spec_dir: Optional[Path] = None,
    force_reanalyze: bool = False,
) -> SecurityProfile:
    """
    Get existing profile or create a new one.

    This is the main entry point for the security system.

    Args:
        project_dir: Project root directory
        spec_dir: Optional spec directory for storing profile
        force_reanalyze: Force re-analysis even if profile exists

    Returns:
        SecurityProfile for the project
    """
    analyzer = ProjectAnalyzer(project_dir, spec_dir)
    return analyzer.analyze(force=force_reanalyze)


def is_command_allowed(
    command: str,
    profile: SecurityProfile,
) -> tuple[bool, str]:
    """
    Check if a command is allowed by the profile.

    Args:
        command: The command name (base command, not full command line)
        profile: The security profile to check against

    Returns:
        (is_allowed, reason) tuple
    """
    allowed = profile.get_all_allowed_commands()

    if command in allowed:
        return True, ""

    # Check for script commands (e.g., "./script.sh")
    if command.startswith("./") or command.startswith("/"):
        basename = os.path.basename(command)
        if basename in profile.custom_scripts.shell_scripts:
            return True, ""
        if command in profile.script_commands:
            return True, ""

    return False, f"Command '{command}' is not in the allowed commands for this project"


def needs_validation(command: str) -> Optional[str]:
    """
    Check if a command needs extra validation.

    Returns:
        Validation function name or None
    """
    return VALIDATED_COMMANDS.get(command)


# =============================================================================
# CLI for testing
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python project_analyzer.py <project_dir> [--force]")
        sys.exit(1)

    project_dir = Path(sys.argv[1])
    force = "--force" in sys.argv

    if not project_dir.exists():
        print(f"Error: {project_dir} does not exist")
        sys.exit(1)

    profile = get_or_create_profile(project_dir, force_reanalyze=force)

    print("\nAllowed commands:")
    for cmd in sorted(profile.get_all_allowed_commands()):
        print(f"  {cmd}")
