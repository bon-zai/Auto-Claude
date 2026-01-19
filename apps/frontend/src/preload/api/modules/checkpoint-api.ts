/**
 * Checkpoint API module for Semi-Auto execution mode.
 *
 * Story Reference: Story 5.4 - Implement Checkpoint Approval Flow
 * Architecture Source: architecture.md#Checkpoint-Service
 */

import { ipcRenderer } from 'electron';
import { IPC_CHANNELS } from '../../../shared/constants';
import type { IPCResult } from '../../../shared/types';
import type { CheckpointInfo, FeedbackAttachment } from '../../../renderer/components/checkpoints/types';

/**
 * Result of a checkpoint approval operation.
 */
export interface CheckpointApprovalResult {
  /** Whether the approval was successful */
  success: boolean;
  /** Status message */
  message?: string;
  /** Whether execution has resumed */
  resumed: boolean;
}

/**
 * Result of a checkpoint revision request.
 */
export interface CheckpointRevisionResult {
  /** Whether the revision request was successful */
  success: boolean;
  /** Status message */
  message?: string;
  /** Whether execution has resumed with revision */
  resumed: boolean;
}

/**
 * Result of a checkpoint cancellation.
 */
export interface CheckpointCancelResult {
  /** Whether the cancellation was successful */
  success: boolean;
  /** Status message */
  message?: string;
  /** Whether the task was stopped */
  stopped: boolean;
}

/**
 * Checkpoint API interface.
 */
export interface CheckpointAPI {
  /**
   * Approve a checkpoint and resume execution.
   * Story 5.4 FR25: Records approval and resumes execution.
   *
   * @param taskId - The task ID
   * @param checkpointId - The checkpoint ID
   * @param feedback - Optional feedback to include with approval
   * @param attachments - Optional attachments (Story 5.3)
   */
  approve: (
    taskId: string,
    checkpointId: string,
    feedback?: string,
    attachments?: FeedbackAttachment[]
  ) => Promise<IPCResult<CheckpointApprovalResult>>;

  /**
   * Request revision at a checkpoint.
   *
   * @param taskId - The task ID
   * @param checkpointId - The checkpoint ID
   * @param feedback - Required feedback explaining the revision request
   * @param attachments - Optional attachments (Story 5.3)
   */
  revise: (
    taskId: string,
    checkpointId: string,
    feedback: string,
    attachments?: FeedbackAttachment[]
  ) => Promise<IPCResult<CheckpointRevisionResult>>;

  /**
   * Cancel task execution at a checkpoint.
   *
   * @param taskId - The task ID
   * @param checkpointId - The checkpoint ID
   */
  cancel: (
    taskId: string,
    checkpointId: string
  ) => Promise<IPCResult<CheckpointCancelResult>>;

  /**
   * Listen for checkpoint reached events.
   *
   * @param callback - Called when a checkpoint is reached
   * @returns Unsubscribe function
   */
  onCheckpointReached: (
    callback: (taskId: string, checkpoint: CheckpointInfo) => void
  ) => () => void;

  /**
   * Listen for checkpoint resumed events.
   *
   * @param callback - Called when a checkpoint is resumed
   * @returns Unsubscribe function
   */
  onCheckpointResumed: (
    callback: (taskId: string, checkpointId: string, decision: string) => void
  ) => () => void;
}

/**
 * Create the Checkpoint API.
 */
export const createCheckpointAPI = (): CheckpointAPI => ({
  approve: (
    taskId: string,
    checkpointId: string,
    feedback?: string,
    attachments?: FeedbackAttachment[]
  ): Promise<IPCResult<CheckpointApprovalResult>> =>
    ipcRenderer.invoke(IPC_CHANNELS.CHECKPOINT_APPROVE, taskId, checkpointId, feedback, attachments),

  revise: (
    taskId: string,
    checkpointId: string,
    feedback: string,
    attachments?: FeedbackAttachment[]
  ): Promise<IPCResult<CheckpointRevisionResult>> =>
    ipcRenderer.invoke(IPC_CHANNELS.CHECKPOINT_REVISE, taskId, checkpointId, feedback, attachments),

  cancel: (
    taskId: string,
    checkpointId: string
  ): Promise<IPCResult<CheckpointCancelResult>> =>
    ipcRenderer.invoke(IPC_CHANNELS.CHECKPOINT_CANCEL, taskId, checkpointId),

  onCheckpointReached: (
    callback: (taskId: string, checkpoint: CheckpointInfo) => void
  ): (() => void) => {
    const handler = (
      _event: Electron.IpcRendererEvent,
      taskId: string,
      checkpoint: CheckpointInfo
    ): void => {
      callback(taskId, checkpoint);
    };
    ipcRenderer.on(IPC_CHANNELS.CHECKPOINT_REACHED, handler);
    return () => {
      ipcRenderer.removeListener(IPC_CHANNELS.CHECKPOINT_REACHED, handler);
    };
  },

  onCheckpointResumed: (
    callback: (taskId: string, checkpointId: string, decision: string) => void
  ): (() => void) => {
    const handler = (
      _event: Electron.IpcRendererEvent,
      taskId: string,
      checkpointId: string,
      decision: string
    ): void => {
      callback(taskId, checkpointId, decision);
    };
    ipcRenderer.on(IPC_CHANNELS.CHECKPOINT_RESUMED, handler);
    return () => {
      ipcRenderer.removeListener(IPC_CHANNELS.CHECKPOINT_RESUMED, handler);
    };
  }
});
