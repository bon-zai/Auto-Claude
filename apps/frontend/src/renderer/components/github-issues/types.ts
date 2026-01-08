/**
 * GitHub Issues Component Types
 *
 * This module exports TypeScript interfaces and types used by the
 * github-issues components, including Auto-PR-Review related types.
 *
 * Types are centralized here to:
 * 1. Avoid circular dependencies between components and hooks
 * 2. Provide a single source of truth for component props
 * 3. Enable easier refactoring and type reuse
 */

// =============================================================================
// Re-exports from Preload API
// =============================================================================

// Re-export core types from the preload API for convenience
export type {
  AutoPRReviewConfig,
  AutoPRReviewProgress,
  AutoPRReviewStatus,
  CICheckStatus,
  ExternalBotStatus,
  AutoPRReviewStartRequest,
  AutoPRReviewStartResponse,
  AutoPRReviewStopRequest,
  AutoPRReviewStopResponse,
  AutoPRReviewStatusRequest,
  AutoPRReviewStatusResponse,
} from '../../../preload/api/modules/github-api';

export {
  DEFAULT_AUTO_PR_REVIEW_CONFIG,
  isTerminalStatus,
  isInProgressStatus,
} from '../../../preload/api/modules/github-api';

// =============================================================================
// Auto-PR-Review Component Types
// =============================================================================

/**
 * Import types for local interface definitions
 */
import type {
  AutoPRReviewProgress,
  AutoPRReviewStatus,
} from '../../../preload/api/modules/github-api';

/**
 * Props for the AutoPRReviewProgressCard component.
 *
 * This component displays real-time progress of an autonomous PR review,
 * including CI check status, external bot reviews, and iteration progress.
 *
 * CRITICAL: The system NEVER auto-merges. Human approval is always required.
 */
export interface AutoPRReviewProgressCardProps {
  /** Progress data for the PR review operation */
  progress: AutoPRReviewProgress;

  /**
   * Callback invoked when user requests to cancel the review.
   * @param repository - Repository in "owner/repo" format
   * @param prNumber - Pull request number
   * @param reason - Optional reason for cancellation (for audit logging)
   */
  onCancel?: (repository: string, prNumber: number, reason?: string) => Promise<void>;

  /** Optional CSS class name for custom styling */
  className?: string;

  /**
   * Translation function for internationalization.
   * If not provided, falls back to returning the last segment of the key.
   * @param key - Translation key (e.g., "autoPRReview.status.idle")
   * @returns Translated string
   */
  t?: (key: string) => string;
}

/**
 * Configuration for status visual styling in the progress card.
 * Maps each status to consistent colors and labels.
 */
export interface StatusConfig {
  /** i18n key for the status label */
  label: string;

  /** Text color class (e.g., "text-blue-600") */
  color: string;

  /** Background color class (e.g., "bg-blue-50") */
  bgColor: string;

  /** Border color class (e.g., "border-blue-300") */
  borderColor: string;
}

/**
 * Status configuration mapping for all Auto-PR-Review states.
 * Used by AutoPRReviewProgressCard to determine visual styling.
 */
export type AutoPRReviewStatusConfigMap = Record<AutoPRReviewStatus, StatusConfig>;
