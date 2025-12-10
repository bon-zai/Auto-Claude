#!/usr/bin/env python3
"""
Tests for Security System
=========================

Tests the security.py module functionality including:
- Command extraction and parsing
- Command allowlist validation
- Sensitive command validators (rm, chmod, pkill, etc.)
- Security hook behavior
"""

import pytest

from security import (
    extract_commands,
    split_command_segments,
    validate_command,
    validate_pkill_command,
    validate_kill_command,
    validate_chmod_command,
    validate_rm_command,
    validate_git_commit,
    get_command_for_validation,
    reset_profile_cache,
)
from project_analyzer import SecurityProfile, BASE_COMMANDS


class TestCommandExtraction:
    """Tests for command extraction from shell strings."""

    def test_simple_command(self):
        """Extracts single command correctly."""
        commands = extract_commands("ls -la")
        assert commands == ["ls"]

    def test_command_with_path(self):
        """Extracts command from path."""
        commands = extract_commands("/usr/bin/python script.py")
        assert commands == ["python"]

    def test_piped_commands(self):
        """Extracts all commands from pipeline."""
        commands = extract_commands("cat file.txt | grep pattern | wc -l")
        assert commands == ["cat", "grep", "wc"]

    def test_chained_commands_and(self):
        """Extracts commands from && chain."""
        commands = extract_commands("cd /tmp && ls && pwd")
        assert commands == ["cd", "ls", "pwd"]

    def test_chained_commands_or(self):
        """Extracts commands from || chain."""
        commands = extract_commands("test -f file || echo 'not found'")
        assert commands == ["test", "echo"]

    def test_semicolon_separated(self):
        """Extracts commands separated by semicolons."""
        commands = extract_commands("echo hello; echo world; ls")
        assert commands == ["echo", "echo", "ls"]

    def test_mixed_operators(self):
        """Handles mixed operators correctly."""
        commands = extract_commands("cmd1 && cmd2 || cmd3; cmd4 | cmd5")
        assert commands == ["cmd1", "cmd2", "cmd3", "cmd4", "cmd5"]

    def test_skips_flags(self):
        """Doesn't include flags as commands."""
        commands = extract_commands("ls -la --color=auto")
        assert commands == ["ls"]

    def test_skips_variable_assignments(self):
        """Skips variable assignments."""
        commands = extract_commands("VAR=value echo $VAR")
        assert commands == ["echo"]

    def test_handles_quotes(self):
        """Handles quoted arguments."""
        commands = extract_commands('echo "hello world" && grep "pattern with spaces"')
        assert commands == ["echo", "grep"]

    def test_empty_string(self):
        """Returns empty list for empty string."""
        commands = extract_commands("")
        assert commands == []

    def test_malformed_command(self):
        """Returns empty list for malformed command (fail-safe)."""
        commands = extract_commands("echo 'unclosed quote")
        assert commands == []


class TestSplitCommandSegments:
    """Tests for splitting command strings into segments."""

    def test_single_command(self):
        """Single command returns one segment."""
        segments = split_command_segments("ls -la")
        assert segments == ["ls -la"]

    def test_and_chain(self):
        """Splits on &&."""
        segments = split_command_segments("cd /tmp && ls")
        assert segments == ["cd /tmp", "ls"]

    def test_or_chain(self):
        """Splits on ||."""
        segments = split_command_segments("test -f file || echo error")
        assert segments == ["test -f file", "echo error"]

    def test_semicolon(self):
        """Splits on semicolons."""
        segments = split_command_segments("echo a; echo b; echo c")
        assert segments == ["echo a", "echo b", "echo c"]


class TestPkillValidator:
    """Tests for pkill command validation."""

    def test_allowed_process_node(self):
        """Allows killing node processes."""
        allowed, reason = validate_pkill_command("pkill -f node")
        assert allowed is True

    def test_allowed_process_python(self):
        """Allows killing python processes."""
        allowed, reason = validate_pkill_command("pkill python")
        assert allowed is True

    def test_allowed_process_vite(self):
        """Allows killing vite processes."""
        allowed, reason = validate_pkill_command("pkill vite")
        assert allowed is True

    def test_blocked_system_process(self):
        """Blocks killing system processes."""
        allowed, reason = validate_pkill_command("pkill init")
        assert allowed is False
        assert "dev processes" in reason

    def test_blocked_arbitrary_process(self):
        """Blocks killing arbitrary processes."""
        allowed, reason = validate_pkill_command("pkill systemd")
        assert allowed is False


class TestKillValidator:
    """Tests for kill command validation."""

    def test_allowed_specific_pid(self):
        """Allows killing specific PID."""
        allowed, reason = validate_kill_command("kill 12345")
        assert allowed is True

    def test_allowed_with_signal(self):
        """Allows kill with signal."""
        allowed, reason = validate_kill_command("kill -9 12345")
        assert allowed is True

    def test_blocked_kill_all(self):
        """Blocks kill -1 (kill all)."""
        allowed, reason = validate_kill_command("kill -9 -1")
        assert allowed is False
        assert "all processes" in reason

    def test_blocked_kill_group_zero(self):
        """Blocks kill 0 (process group)."""
        allowed, reason = validate_kill_command("kill 0")
        assert allowed is False


class TestChmodValidator:
    """Tests for chmod command validation."""

    def test_allowed_plus_x(self):
        """Allows +x (make executable)."""
        allowed, reason = validate_chmod_command("chmod +x script.sh")
        assert allowed is True

    def test_allowed_755(self):
        """Allows 755 mode."""
        allowed, reason = validate_chmod_command("chmod 755 script.sh")
        assert allowed is True

    def test_allowed_644(self):
        """Allows 644 mode."""
        allowed, reason = validate_chmod_command("chmod 644 file.txt")
        assert allowed is True

    def test_allowed_user_executable(self):
        """Allows u+x."""
        allowed, reason = validate_chmod_command("chmod u+x script.sh")
        assert allowed is True

    def test_blocked_world_writable(self):
        """Blocks world-writable modes."""
        allowed, reason = validate_chmod_command("chmod 777 file.txt")
        assert allowed is False
        assert "executable modes" in reason

    def test_blocked_arbitrary_mode(self):
        """Blocks arbitrary chmod modes."""
        allowed, reason = validate_chmod_command("chmod 000 file.txt")
        assert allowed is False

    def test_requires_file(self):
        """Requires at least one file argument."""
        allowed, reason = validate_chmod_command("chmod +x")
        assert allowed is False
        assert "at least one file" in reason


class TestRmValidator:
    """Tests for rm command validation."""

    def test_allowed_specific_file(self):
        """Allows removing specific files."""
        allowed, reason = validate_rm_command("rm file.txt")
        assert allowed is True

    def test_allowed_directory(self):
        """Allows removing directory with -r."""
        allowed, reason = validate_rm_command("rm -rf build/")
        assert allowed is True

    def test_blocked_root(self):
        """Blocks rm /."""
        allowed, reason = validate_rm_command("rm -rf /")
        assert allowed is False
        assert "not allowed for safety" in reason

    def test_blocked_home(self):
        """Blocks rm ~."""
        allowed, reason = validate_rm_command("rm -rf ~")
        assert allowed is False

    def test_blocked_parent_escape(self):
        """Blocks rm ../."""
        allowed, reason = validate_rm_command("rm -rf ../")
        assert allowed is False

    def test_blocked_root_wildcard(self):
        """Blocks rm /*."""
        allowed, reason = validate_rm_command("rm -rf /*")
        assert allowed is False

    def test_blocked_system_dirs(self):
        """Blocks system directories."""
        for dir in ["/usr", "/etc", "/var", "/bin", "/lib"]:
            allowed, reason = validate_rm_command(f"rm -rf {dir}")
            assert allowed is False


class TestValidateCommand:
    """Tests for full command validation."""

    def test_base_commands_allowed(self, temp_dir):
        """Base commands are always allowed."""
        reset_profile_cache()

        for cmd in ["ls", "cat", "grep", "echo", "pwd"]:
            allowed, reason = validate_command(cmd, temp_dir)
            assert allowed is True, f"{cmd} should be allowed"

    def test_git_commands_allowed(self, temp_dir):
        """Git commands are allowed."""
        reset_profile_cache()

        allowed, reason = validate_command("git status", temp_dir)
        assert allowed is True

    def test_dangerous_command_blocked(self, temp_dir):
        """Dangerous commands not in allowlist are blocked."""
        reset_profile_cache()

        allowed, reason = validate_command("format c:", temp_dir)
        assert allowed is False

    def test_rm_safe_usage_allowed(self, temp_dir):
        """rm with safe arguments is allowed."""
        reset_profile_cache()

        allowed, reason = validate_command("rm file.txt", temp_dir)
        assert allowed is True

    def test_rm_dangerous_usage_blocked(self, temp_dir):
        """rm with dangerous arguments is blocked."""
        reset_profile_cache()

        allowed, reason = validate_command("rm -rf /", temp_dir)
        assert allowed is False

    def test_piped_commands_all_checked(self, temp_dir):
        """All commands in pipeline are validated."""
        reset_profile_cache()

        # All safe commands
        allowed, reason = validate_command("cat file | grep pattern | wc -l", temp_dir)
        assert allowed is True


class TestGetCommandForValidation:
    """Tests for finding command segment for validation."""

    def test_finds_correct_segment(self):
        """Finds the segment containing the command."""
        segments = ["cd /tmp", "rm -rf build", "ls"]
        segment = get_command_for_validation("rm", segments)
        assert segment == "rm -rf build"

    def test_returns_empty_when_not_found(self):
        """Returns empty string when command not found."""
        segments = ["ls", "pwd"]
        segment = get_command_for_validation("rm", segments)
        assert segment == ""


class TestSecurityProfileIntegration:
    """Tests for security profile integration."""

    def test_profile_detects_python_commands(self, python_project):
        """Profile includes Python commands for Python projects."""
        from project_analyzer import get_or_create_profile
        reset_profile_cache()

        profile = get_or_create_profile(python_project)

        assert "python" in profile.get_all_allowed_commands()
        assert "pip" in profile.get_all_allowed_commands()

    def test_profile_detects_node_commands(self, node_project):
        """Profile includes Node commands for Node projects."""
        from project_analyzer import get_or_create_profile
        reset_profile_cache()

        profile = get_or_create_profile(node_project)

        assert "npm" in profile.get_all_allowed_commands()
        assert "node" in profile.get_all_allowed_commands()

    def test_profile_detects_docker_commands(self, docker_project):
        """Profile includes Docker commands for Docker projects."""
        from project_analyzer import get_or_create_profile
        reset_profile_cache()

        profile = get_or_create_profile(docker_project)

        assert "docker" in profile.get_all_allowed_commands()
        assert "docker-compose" in profile.get_all_allowed_commands()

    def test_profile_caching(self, python_project):
        """Profile is cached after first analysis."""
        from project_analyzer import get_or_create_profile
        from security import get_security_profile, reset_profile_cache
        reset_profile_cache()

        # First call - analyzes
        profile1 = get_security_profile(python_project)

        # Second call - should use cache
        profile2 = get_security_profile(python_project)

        assert profile1 is profile2


class TestGitCommitValidator:
    """Tests for git commit validation (secret scanning)."""

    def test_allows_normal_commit(self, temp_git_repo, stage_files):
        """Allows commit without secrets."""
        stage_files({"normal.py": "x = 42\n"})

        allowed, reason = validate_git_commit("git commit -m 'test'")
        assert allowed is True

    def test_non_commit_commands_pass(self):
        """Non-commit git commands always pass."""
        allowed, reason = validate_git_commit("git status")
        assert allowed is True

        allowed, reason = validate_git_commit("git add .")
        assert allowed is True

        allowed, reason = validate_git_commit("git push")
        assert allowed is True
