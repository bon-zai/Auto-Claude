/**
 * Checkpoint IPC handlers for Semi-Auto execution mode.
 *
 * Story Reference: Story 5.4 - Implement Checkpoint Approval Flow
 * Story Reference: Story 5.6 - Implement Checkpoint Notifications
 * Architecture Source: architecture.md#Checkpoint-Service
 *
 * These handlers manage communication between the renderer process
 * (CheckpointDialog) and the backend CheckpointService.
 */

import { ipcMain, BrowserWindow } from 'electron';
import { IPC_CHANNELS } from '../../shared/constants';
import type { IPCResult } from '../../shared/types';
import type {
  CheckpointApprovalResult,
  CheckpointRevisionResult,
  CheckpointCancelResult,
} from '../../preload/api/modules/checkpoint-api';
import type { CheckpointInfo, FeedbackAttachment } from '../../renderer/components/checkpoints/types';
import { AgentManager } from '../agent';
import { safeSendToRenderer } from './utils';
import { findTaskAndProject } from './task/shared';
import { debugLog, debugError } from '../../shared/utils/debug-logger';
import { notificationService } from '../notification-service';

/**
 * Register all checkpoint-related IPC handlers.
 *
 * @param agentManager - The agent manager instance for task communication
 * @param getMainWindow - Function to get the main BrowserWindow
 */
export function registerCheckpointHandlers(
  agentManager: AgentManager,
  getMainWindow: () => BrowserWindow | null
): void {
  // ============================================
  // Checkpoint Decision Handlers (Renderer → Main)
  // ============================================

  /**
   * Handle checkpoint approval.
   * Story 5.4 FR25: Records approval and resumes execution.
   */
  ipcMain.handle(
    IPC_CHANNELS.CHECKPOINT_APPROVE,
    async (
      _event,
      taskId: string,
      checkpointId: string,
      feedback?: string,
      attachments?: FeedbackAttachment[]
    ): Promise<IPCResult<CheckpointApprovalResult>> => {
      debugLog(`[CHECKPOINT_APPROVE] taskId: ${taskId}, checkpointId: ${checkpointId}, hasFeedback: ${!!feedback}`);

      try {
        const { task, project } = findTaskAndProject(taskId);
        if (!task || !project) {
          return {
            success: false,
            error: 'Task or project not found',
          };
        }

        // Resume checkpoint in backend via agent manager
        // Story 5.4: decision is 'approve', feedback is optional guidance
        const result = await agentManager.resumeCheckpoint(taskId, checkpointId, 'approve', feedback, attachments);

        if (result.success) {
          // Emit resumed event to renderer
          safeSendToRenderer(
            getMainWindow,
            IPC_CHANNELS.CHECKPOINT_RESUMED,
            taskId,
            checkpointId,
            'approve'
          );

          return {
            success: true,
            data: {
              success: true,
              message: 'Checkpoint approved',
              resumed: true,
            },
          };
        }

        return {
          success: false,
          error: result.error || 'Failed to approve checkpoint',
        };
      } catch (error) {
        debugError('[CHECKPOINT_APPROVE] Error:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : 'Unknown error approving checkpoint',
        };
      }
    }
  );

  /**
   * Handle checkpoint revision request.
   * Story 5.4: Revision requires feedback explaining what changes are needed.
   */
  ipcMain.handle(
    IPC_CHANNELS.CHECKPOINT_REVISE,
    async (
      _event,
      taskId: string,
      checkpointId: string,
      feedback: string,
      attachments?: FeedbackAttachment[]
    ): Promise<IPCResult<CheckpointRevisionResult>> => {
      debugLog(`[CHECKPOINT_REVISE] taskId: ${taskId}, checkpointId: ${checkpointId}`);

      try {
        const { task, project } = findTaskAndProject(taskId);
        if (!task || !project) {
          return {
            success: false,
            error: 'Task or project not found',
          };
        }

        if (!feedback || !feedback.trim()) {
          return {
            success: false,
            error: 'Feedback is required for revision requests',
          };
        }

        // Resume checkpoint in backend via agent manager with revise decision
        const result = await agentManager.resumeCheckpoint(taskId, checkpointId, 'revise', feedback, attachments);

        if (result.success) {
          // Emit resumed event to renderer
          safeSendToRenderer(
            getMainWindow,
            IPC_CHANNELS.CHECKPOINT_RESUMED,
            taskId,
            checkpointId,
            'revise'
          );

          return {
            success: true,
            data: {
              success: true,
              message: 'Revision requested',
              resumed: true,
            },
          };
        }

        return {
          success: false,
          error: result.error || 'Failed to request revision',
        };
      } catch (error) {
        debugError('[CHECKPOINT_REVISE] Error:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : 'Unknown error requesting revision',
        };
      }
    }
  );

  /**
   * Handle checkpoint cancellation (cancel task at checkpoint).
   */
  ipcMain.handle(
    IPC_CHANNELS.CHECKPOINT_CANCEL,
    async (
      _event,
      taskId: string,
      checkpointId: string
    ): Promise<IPCResult<CheckpointCancelResult>> => {
      debugLog(`[CHECKPOINT_CANCEL] taskId: ${taskId}, checkpointId: ${checkpointId}`);

      try {
        const { task, project } = findTaskAndProject(taskId);
        if (!task || !project) {
          return {
            success: false,
            error: 'Task or project not found',
          };
        }

        // Resume checkpoint with reject decision to cancel task
        const result = await agentManager.resumeCheckpoint(taskId, checkpointId, 'reject');

        if (result.success) {
          // Emit resumed event to renderer with cancel decision
          safeSendToRenderer(
            getMainWindow,
            IPC_CHANNELS.CHECKPOINT_RESUMED,
            taskId,
            checkpointId,
            'reject'
          );

          return {
            success: true,
            data: {
              success: true,
              message: 'Task cancelled at checkpoint',
              stopped: true,
            },
          };
        }

        return {
          success: false,
          error: result.error || 'Failed to cancel task',
        };
      } catch (error) {
        debugError('[CHECKPOINT_CANCEL] Error:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : 'Unknown error cancelling task',
        };
      }
    }
  );

  // ============================================
  // Checkpoint Event Forwarding (Agent Manager → Renderer)
  // ============================================

  /**
   * Forward checkpoint reached events from agent manager to renderer.
   * This event is emitted when the backend CheckpointService pauses at a checkpoint.
   *
   * Story 5.6: Send system notification when checkpoint is reached.
   */
  agentManager.on('checkpoint-reached', (taskId: string, checkpoint: CheckpointInfo) => {
    debugLog(`[checkpoint-reached] taskId: ${taskId}, checkpointId: ${checkpoint.checkpointId}`);

    // Get project ID for multi-project filtering
    const { project } = findTaskAndProject(taskId);

    // Forward to renderer
    safeSendToRenderer(
      getMainWindow,
      IPC_CHANNELS.CHECKPOINT_REACHED,
      taskId,
      checkpoint,
      project?.id
    );

    // Story 5.6: Send system notification
    // AC1: Notification sent via Electron IPC + system notification
    // AC2: System tray/dock shows indicator (handled in notificationService)
    // AC3: Sound plays if enabled in settings (handled in notificationService)
    notificationService.notifyCheckpointReached(taskId, checkpoint, project?.id);
  });

  /**
   * Clear badge when checkpoint is resumed.
   * Story 5.6 Task 3: Clear when checkpoint resolved.
   */
  agentManager.on('checkpoint-resumed', (taskId: string, checkpointId: string) => {
    debugLog(`[checkpoint-resumed] taskId: ${taskId}, checkpointId: ${checkpointId}`);
    notificationService.clearCheckpointBadge();
  });

  debugLog('[IPC] Checkpoint handlers registered');
}
