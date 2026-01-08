"""
Unit Tests for PermissionManager
=================================

Tests for the PermissionManager class covering:
- Allowlist-based authorization
- Wildcard (*) support for allowing all users
- Case-insensitive username matching
- Empty/unconfigured allowlist handling
- Permission denied scenarios
- Audit logging

Run with: pytest tests/test_permission_manager.py -v
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

# Add the backend directory to the path for imports
backend_path = Path(__file__).parent.parent / "apps" / "backend"
sys.path.insert(0, str(backend_path))

import pytest

from runners.github.security.permission_manager import (
    PermissionAction,
    PermissionCheckResult,
    PermissionDecision,
    PermissionError,
    PermissionManager,
    can_trigger_auto_pr_review,
    get_permission_manager,
    require_auto_pr_review_permission,
    reset_permission_manager,
)


class TestPermissionManager:
    """Tests for PermissionManager class."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        """Reset environment and module state before each test."""
        # Clear any cached state
        reset_permission_manager()

        # Save original env values
        self._original_env = os.environ.get(
            PermissionManager.ENV_ALLOWED_USERS
        )

        # Remove env var to start with clean slate
        if PermissionManager.ENV_ALLOWED_USERS in os.environ:
            del os.environ[PermissionManager.ENV_ALLOWED_USERS]

        yield

        # Restore original env values
        if self._original_env is not None:
            os.environ[PermissionManager.ENV_ALLOWED_USERS] = self._original_env
        elif PermissionManager.ENV_ALLOWED_USERS in os.environ:
            del os.environ[PermissionManager.ENV_ALLOWED_USERS]

        reset_permission_manager()

    @pytest.fixture
    def manager(self) -> PermissionManager:
        """Create a fresh PermissionManager instance for each test."""
        return PermissionManager(log_enabled=False)

    # =========================================================================
    # Initialization Tests
    # =========================================================================

    def test_default_initialization(self, manager: PermissionManager) -> None:
        """Test default configuration values."""
        assert manager._allowed_users_env == PermissionManager.ENV_ALLOWED_USERS
        assert manager._log_enabled is False

    def test_custom_env_var(self) -> None:
        """Test custom environment variable name."""
        custom_env = "CUSTOM_ALLOWED_USERS"
        manager = PermissionManager(
            allowed_users_env=custom_env, log_enabled=False
        )
        assert manager._allowed_users_env == custom_env

    # =========================================================================
    # Allowlist Tests - Basic
    # =========================================================================

    def test_allowlist_single_user(self, manager: PermissionManager) -> None:
        """Test allowlist with single user."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "testuser"
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("testuser") is True
        assert manager.can_trigger_auto_pr_review("otheruser") is False

    def test_allowlist_multiple_users(self, manager: PermissionManager) -> None:
        """Test allowlist with multiple users."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "user1,user2,user3"
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("user1") is True
        assert manager.can_trigger_auto_pr_review("user2") is True
        assert manager.can_trigger_auto_pr_review("user3") is True
        assert manager.can_trigger_auto_pr_review("user4") is False

    def test_allowlist_with_spaces(self, manager: PermissionManager) -> None:
        """Test allowlist with spaces around usernames."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = " user1 , user2 , user3 "
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("user1") is True
        assert manager.can_trigger_auto_pr_review("user2") is True
        assert manager.can_trigger_auto_pr_review("user3") is True

    # =========================================================================
    # Case Insensitivity Tests
    # =========================================================================

    def test_case_insensitive_allowlist(
        self, manager: PermissionManager
    ) -> None:
        """Test that username matching is case-insensitive."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "TestUser,ANOTHER"
        manager.clear_cache()

        # Various case combinations should all work
        assert manager.can_trigger_auto_pr_review("testuser") is True
        assert manager.can_trigger_auto_pr_review("TESTUSER") is True
        assert manager.can_trigger_auto_pr_review("TestUser") is True
        assert manager.can_trigger_auto_pr_review("tEsTuSeR") is True
        assert manager.can_trigger_auto_pr_review("another") is True
        assert manager.can_trigger_auto_pr_review("Another") is True

    def test_case_insensitive_input(
        self, manager: PermissionManager
    ) -> None:
        """Test that input username is normalized."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "lowercase"
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("LOWERCASE") is True
        assert manager.can_trigger_auto_pr_review("LowerCase") is True
        assert manager.can_trigger_auto_pr_review("lowercase") is True

    # =========================================================================
    # Wildcard Tests
    # =========================================================================

    def test_wildcard_allows_all(self, manager: PermissionManager) -> None:
        """Test that wildcard (*) allows all users."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "*"
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("anyuser") is True
        assert manager.can_trigger_auto_pr_review("another") is True
        assert manager.can_trigger_auto_pr_review("admin") is True
        assert manager.can_trigger_auto_pr_review("guest") is True

    def test_wildcard_with_other_users(
        self, manager: PermissionManager
    ) -> None:
        """Test that wildcard (*) works even with other users in list."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "user1,*,user2"
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("anyuser") is True
        assert manager.can_trigger_auto_pr_review("notinlist") is True

    def test_is_wildcard_enabled(self, manager: PermissionManager) -> None:
        """Test is_wildcard_enabled method."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "user1,user2"
        manager.clear_cache()
        assert manager.is_wildcard_enabled() is False

        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "*"
        manager.clear_cache()
        assert manager.is_wildcard_enabled() is True

        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "user1,*"
        manager.clear_cache()
        assert manager.is_wildcard_enabled() is True

    # =========================================================================
    # Deny Scenarios
    # =========================================================================

    def test_empty_allowlist_denies_all(
        self, manager: PermissionManager
    ) -> None:
        """Test that empty allowlist denies all users."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = ""
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("anyuser") is False

    def test_unset_allowlist_denies_all(
        self, manager: PermissionManager
    ) -> None:
        """Test that unset env var denies all users."""
        # Env var should already be unset from setup
        assert manager.can_trigger_auto_pr_review("anyuser") is False

    def test_whitespace_only_denies_all(
        self, manager: PermissionManager
    ) -> None:
        """Test that whitespace-only value denies all users."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "   \t\n  "
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("anyuser") is False

    def test_user_not_in_allowlist_denied(
        self, manager: PermissionManager
    ) -> None:
        """Test that user not in allowlist is denied."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "allowed1,allowed2"
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("notallowed") is False

    def test_empty_username_denied(self, manager: PermissionManager) -> None:
        """Test that empty username is denied."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "*"
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("") is False
        assert manager.can_trigger_auto_pr_review("   ") is False

    # =========================================================================
    # Permission Check Result Tests
    # =========================================================================

    def test_check_permission_allowed(
        self, manager: PermissionManager
    ) -> None:
        """Test check_permission returns correct result for allowed user."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "testuser"
        manager.clear_cache()

        result = manager.check_permission(
            "testuser", PermissionAction.AUTO_PR_REVIEW
        )

        assert result.decision == PermissionDecision.ALLOWED
        assert result.is_allowed is True
        assert result.username == "testuser"
        assert result.action == "auto_pr_review"
        assert "allowlist" in result.reason.lower()

    def test_check_permission_denied(
        self, manager: PermissionManager
    ) -> None:
        """Test check_permission returns correct result for denied user."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "otheruser"
        manager.clear_cache()

        result = manager.check_permission(
            "testuser", PermissionAction.AUTO_PR_REVIEW
        )

        assert result.decision == PermissionDecision.DENIED
        assert result.is_allowed is False
        assert result.username == "testuser"

    def test_check_permission_not_configured(
        self, manager: PermissionManager
    ) -> None:
        """Test check_permission returns NOT_CONFIGURED when no allowlist."""
        # Env var should already be unset from setup
        result = manager.check_permission(
            "testuser", PermissionAction.AUTO_PR_REVIEW
        )

        assert result.decision == PermissionDecision.NOT_CONFIGURED
        assert result.is_allowed is False
        assert "not set" in result.reason.lower() or "empty" in result.reason.lower()

    def test_check_permission_wildcard(
        self, manager: PermissionManager
    ) -> None:
        """Test check_permission returns correct result for wildcard."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "*"
        manager.clear_cache()

        result = manager.check_permission(
            "anyuser", PermissionAction.AUTO_PR_REVIEW
        )

        assert result.decision == PermissionDecision.ALLOWED
        assert result.is_allowed is True
        assert "wildcard" in result.reason.lower()

    def test_check_permission_with_string_action(
        self, manager: PermissionManager
    ) -> None:
        """Test check_permission works with string action."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "testuser"
        manager.clear_cache()

        result = manager.check_permission("testuser", "custom_action")

        assert result.decision == PermissionDecision.ALLOWED
        assert result.action == "custom_action"

    # =========================================================================
    # Require Permission Tests
    # =========================================================================

    def test_require_permission_success(
        self, manager: PermissionManager
    ) -> None:
        """Test require_permission doesn't raise for allowed user."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "testuser"
        manager.clear_cache()

        # Should not raise
        result = manager.require_permission(
            "testuser", PermissionAction.AUTO_PR_REVIEW
        )
        assert result.is_allowed is True

    def test_require_permission_raises_on_deny(
        self, manager: PermissionManager
    ) -> None:
        """Test require_permission raises PermissionError when denied."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "otheruser"
        manager.clear_cache()

        with pytest.raises(PermissionError) as exc_info:
            manager.require_permission(
                "testuser", PermissionAction.AUTO_PR_REVIEW
            )

        assert exc_info.value.result.decision == PermissionDecision.DENIED
        assert "Permission denied" in str(exc_info.value)

    def test_require_permission_raises_on_not_configured(
        self, manager: PermissionManager
    ) -> None:
        """Test require_permission raises when not configured."""
        # Env var should already be unset from setup
        with pytest.raises(PermissionError) as exc_info:
            manager.require_permission(
                "testuser", PermissionAction.AUTO_PR_REVIEW
            )

        assert (
            exc_info.value.result.decision == PermissionDecision.NOT_CONFIGURED
        )

    # =========================================================================
    # Get Allowed Users Tests
    # =========================================================================

    def test_get_allowed_users(self, manager: PermissionManager) -> None:
        """Test get_allowed_users returns correct set."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "User1,User2,User3"
        manager.clear_cache()

        users = manager.get_allowed_users()

        # Should be lowercase
        assert users == {"user1", "user2", "user3"}

    def test_get_allowed_users_empty(
        self, manager: PermissionManager
    ) -> None:
        """Test get_allowed_users returns empty set when not configured."""
        users = manager.get_allowed_users()
        assert users == set()

    def test_get_allowed_users_returns_copy(
        self, manager: PermissionManager
    ) -> None:
        """Test get_allowed_users returns a copy, not the internal set."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "user1"
        manager.clear_cache()

        users1 = manager.get_allowed_users()
        users1.add("user2")  # Modify the returned set

        users2 = manager.get_allowed_users()
        assert "user2" not in users2  # Should not affect internal state

    # =========================================================================
    # Caching Tests
    # =========================================================================

    def test_cache_clear(self, manager: PermissionManager) -> None:
        """Test that clear_cache refreshes from environment."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "user1"
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("user1") is True
        assert manager.can_trigger_auto_pr_review("user2") is False

        # Change env and clear cache
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "user2"
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("user1") is False
        assert manager.can_trigger_auto_pr_review("user2") is True

    def test_cache_auto_refresh_on_env_change(
        self, manager: PermissionManager
    ) -> None:
        """Test that cache auto-refreshes when env value changes."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "user1"

        # First call should cache
        assert manager.can_trigger_auto_pr_review("user1") is True

        # Change env - cache should detect and refresh
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "user2"

        assert manager.can_trigger_auto_pr_review("user1") is False
        assert manager.can_trigger_auto_pr_review("user2") is True


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        """Reset module state before each test."""
        reset_permission_manager()

        # Save original env values
        self._original_env = os.environ.get(
            PermissionManager.ENV_ALLOWED_USERS
        )

        yield

        # Restore original env values
        if self._original_env is not None:
            os.environ[PermissionManager.ENV_ALLOWED_USERS] = self._original_env
        elif PermissionManager.ENV_ALLOWED_USERS in os.environ:
            del os.environ[PermissionManager.ENV_ALLOWED_USERS]

        reset_permission_manager()

    def test_get_permission_manager_singleton(self) -> None:
        """Test that get_permission_manager returns same instance."""
        pm1 = get_permission_manager()
        pm2 = get_permission_manager()
        assert pm1 is pm2

    def test_can_trigger_auto_pr_review_function(self) -> None:
        """Test the can_trigger_auto_pr_review convenience function."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "testuser"

        assert can_trigger_auto_pr_review("testuser") is True
        assert can_trigger_auto_pr_review("otheruser") is False

    def test_require_auto_pr_review_permission_function(self) -> None:
        """Test the require_auto_pr_review_permission convenience function."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "testuser"

        # Should not raise
        result = require_auto_pr_review_permission("testuser")
        assert result.is_allowed is True

        # Should raise
        with pytest.raises(PermissionError):
            require_auto_pr_review_permission("otheruser")

    def test_reset_permission_manager(self) -> None:
        """Test reset_permission_manager clears singleton."""
        pm1 = get_permission_manager()
        reset_permission_manager()
        pm2 = get_permission_manager()

        # Should be different instances after reset
        assert pm1 is not pm2


class TestPermissionCheckResult:
    """Tests for PermissionCheckResult dataclass."""

    def test_is_allowed_property_allowed(self) -> None:
        """Test is_allowed returns True for ALLOWED decision."""
        result = PermissionCheckResult(
            decision=PermissionDecision.ALLOWED,
            username="testuser",
            action="test_action",
            reason="Allowed",
        )
        assert result.is_allowed is True

    def test_is_allowed_property_denied(self) -> None:
        """Test is_allowed returns False for DENIED decision."""
        result = PermissionCheckResult(
            decision=PermissionDecision.DENIED,
            username="testuser",
            action="test_action",
            reason="Denied",
        )
        assert result.is_allowed is False

    def test_is_allowed_property_not_configured(self) -> None:
        """Test is_allowed returns False for NOT_CONFIGURED decision."""
        result = PermissionCheckResult(
            decision=PermissionDecision.NOT_CONFIGURED,
            username="testuser",
            action="test_action",
            reason="Not configured",
        )
        assert result.is_allowed is False


class TestPermissionError:
    """Tests for PermissionError exception."""

    def test_permission_error_message(self) -> None:
        """Test PermissionError message formatting."""
        result = PermissionCheckResult(
            decision=PermissionDecision.DENIED,
            username="testuser",
            action="test_action",
            reason="User not in allowlist",
        )
        error = PermissionError(result)

        assert "Permission denied" in str(error)
        assert "User not in allowlist" in str(error)

    def test_permission_error_has_result(self) -> None:
        """Test PermissionError exposes the result."""
        result = PermissionCheckResult(
            decision=PermissionDecision.DENIED,
            username="testuser",
            action="test_action",
            reason="Denied",
        )
        error = PermissionError(result)

        assert error.result is result
        assert error.result.decision == PermissionDecision.DENIED


class TestEdgeCases:
    """Tests for edge cases and complex scenarios."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        """Reset environment before each test."""
        reset_permission_manager()

        self._original_env = os.environ.get(
            PermissionManager.ENV_ALLOWED_USERS
        )

        yield

        if self._original_env is not None:
            os.environ[PermissionManager.ENV_ALLOWED_USERS] = self._original_env
        elif PermissionManager.ENV_ALLOWED_USERS in os.environ:
            del os.environ[PermissionManager.ENV_ALLOWED_USERS]

        reset_permission_manager()

    @pytest.fixture
    def manager(self) -> PermissionManager:
        """Create a fresh PermissionManager instance."""
        return PermissionManager(log_enabled=False)

    def test_username_with_special_chars(
        self, manager: PermissionManager
    ) -> None:
        """Test usernames with special characters."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "user-name,user_name,user.name"
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("user-name") is True
        assert manager.can_trigger_auto_pr_review("user_name") is True
        assert manager.can_trigger_auto_pr_review("user.name") is True

    def test_unicode_username(self, manager: PermissionManager) -> None:
        """Test usernames with unicode characters."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "user1"
        manager.clear_cache()

        # Unicode should be handled gracefully
        assert manager.can_trigger_auto_pr_review("user\u200b1") is False  # Zero-width space

    def test_very_long_allowlist(self, manager: PermissionManager) -> None:
        """Test handling of very long allowlist."""
        users = [f"user{i}" for i in range(1000)]
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = ",".join(users)
        manager.clear_cache()

        assert manager.can_trigger_auto_pr_review("user500") is True
        assert manager.can_trigger_auto_pr_review("user999") is True
        assert manager.can_trigger_auto_pr_review("user1000") is False

    def test_empty_entries_in_allowlist(
        self, manager: PermissionManager
    ) -> None:
        """Test allowlist with empty entries between commas."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "user1,,user2,,,user3"
        manager.clear_cache()

        users = manager.get_allowed_users()
        assert users == {"user1", "user2", "user3"}
        assert "" not in users

    def test_duplicate_users_in_allowlist(
        self, manager: PermissionManager
    ) -> None:
        """Test allowlist with duplicate entries."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "user1,USER1,User1,user1"
        manager.clear_cache()

        users = manager.get_allowed_users()
        # Should dedupe to single entry
        assert users == {"user1"}

    def test_multiple_actions(self, manager: PermissionManager) -> None:
        """Test different permission actions."""
        os.environ[PermissionManager.ENV_ALLOWED_USERS] = "testuser"
        manager.clear_cache()

        # All actions should use same allowlist
        result1 = manager.check_permission(
            "testuser", PermissionAction.AUTO_PR_REVIEW
        )
        result2 = manager.check_permission(
            "testuser", PermissionAction.AUTO_FIX
        )
        result3 = manager.check_permission(
            "testuser", PermissionAction.MERGE
        )

        assert result1.is_allowed is True
        assert result2.is_allowed is True
        assert result3.is_allowed is True

    def test_concurrent_instances(self) -> None:
        """Test that multiple instances work independently."""
        os.environ["CUSTOM_ENV_1"] = "user1"
        os.environ["CUSTOM_ENV_2"] = "user2"

        try:
            manager1 = PermissionManager(
                allowed_users_env="CUSTOM_ENV_1", log_enabled=False
            )
            manager2 = PermissionManager(
                allowed_users_env="CUSTOM_ENV_2", log_enabled=False
            )

            assert manager1.can_trigger_auto_pr_review("user1") is True
            assert manager1.can_trigger_auto_pr_review("user2") is False

            assert manager2.can_trigger_auto_pr_review("user1") is False
            assert manager2.can_trigger_auto_pr_review("user2") is True
        finally:
            del os.environ["CUSTOM_ENV_1"]
            del os.environ["CUSTOM_ENV_2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
