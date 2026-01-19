import { Notification, shell, app } from 'electron';
import type { BrowserWindow } from 'electron';
import { projectStore } from './project-store';
import { IPC_CHANNELS } from '../shared/constants';

export type NotificationType = 'task-complete' | 'task-failed' | 'review-needed' | 'task-escalated' | 'checkpoint-reached';

/**
 * Minimal checkpoint info needed for notifications.
 * This is a subset of the full CheckpointInfo type to avoid circular dependencies.
 *
 * @property checkpointId - Unique identifier for the checkpoint (e.g., 'cp-uuid-1234')
 * @property phase - The phase name when checkpoint was reached (e.g., 'Planning', 'Coding', 'QA')
 * @property description - Optional human-readable description of what review is needed
 */
interface CheckpointNotificationInfo {
  /** Unique identifier for the checkpoint (e.g., 'cp-uuid-1234') */
  checkpointId: string;
  /** The phase name when checkpoint was reached (e.g., 'Planning', 'Coding', 'QA') */
  phase: string;
  /** Optional human-readable description of what review is needed */
  description?: string;
}

interface NotificationOptions {
  title: string;
  body: string;
  projectId?: string;
  taskId?: string;
  checkpointId?: string;
  /** Checkpoint phase name (stored separately to avoid parsing from title) */
  checkpointPhase?: string;
}

/**
 * Service for sending system notifications with optional sound
 */
class NotificationService {
  private mainWindow: (() => BrowserWindow | null) | null = null;

  /**
   * Initialize the notification service with the main window getter
   */
  initialize(getMainWindow: () => BrowserWindow | null): void {
    this.mainWindow = getMainWindow;
  }

  /**
   * Send a notification for task completion
   */
  notifyTaskComplete(taskTitle: string, projectId: string, taskId: string): void {
    this.sendNotification('task-complete', {
      title: 'Task Complete',
      body: `"${taskTitle}" has completed and is ready for review`,
      projectId,
      taskId
    });
  }

  /**
   * Send a notification for task failure
   */
  notifyTaskFailed(taskTitle: string, projectId: string, taskId: string): void {
    this.sendNotification('task-failed', {
      title: 'Task Failed',
      body: `"${taskTitle}" encountered an error`,
      projectId,
      taskId
    });
  }

  /**
   * Send a notification for review needed
   */
  notifyReviewNeeded(taskTitle: string, projectId: string, taskId: string): void {
    this.sendNotification('review-needed', {
      title: 'Review Needed',
      body: `"${taskTitle}" is ready for your review`,
      projectId,
      taskId
    });
  }

  /**
   * Send a notification when a task is escalated and needs attention
   * Story Reference: Story 4.5 Task 3 - Include task title and error summary
   */
  notifyTaskEscalated(
    taskTitle: string,
    projectId: string,
    taskId: string,
    errorSummary?: string
  ): void {
    const body = errorSummary
      ? `"${taskTitle}" needs attention: ${errorSummary}`
      : `"${taskTitle}" could not complete and needs your attention`;

    this.sendNotification('task-escalated', {
      title: 'Task Needs Attention',
      body,
      projectId,
      taskId
    });
  }

  /**
   * Send a notification when a checkpoint is reached in Semi-Auto mode.
   * Story Reference: Story 5.6 - Implement Checkpoint Notifications
   *
   * @param taskId - The task ID
   * @param checkpoint - The checkpoint information (uses minimal interface)
   * @param projectId - The project ID
   */
  notifyCheckpointReached(
    taskId: string,
    checkpoint: CheckpointNotificationInfo,
    projectId?: string
  ): void {
    const title = `Checkpoint: ${checkpoint.phase}`;
    const body = checkpoint.description || 'Your review is needed to continue';

    this.sendNotification('checkpoint-reached', {
      title,
      body,
      projectId,
      taskId,
      checkpointId: checkpoint.checkpointId,
      checkpointPhase: checkpoint.phase
    });

    // Set tray badge indicator (macOS dock badge)
    this.setTrayBadge(true);
  }

  /**
   * Clear the tray badge when checkpoint is resolved.
   * Story Reference: Story 5.6 Task 3 - Clear when checkpoint resolved
   */
  clearCheckpointBadge(): void {
    this.setTrayBadge(false);
  }

  /**
   * Set or clear the system tray/dock badge indicator.
   * Story Reference: Story 5.6 Task 3 - Badge/overlay on tray icon
   *
   * Platform support:
   * - macOS: Uses dock badge (shows '!' indicator)
   * - Linux: Uses app.setBadgeCount() for Unity/GNOME docks
   * - Windows: Not supported (would require native tray icon overlay module)
   */
  private setTrayBadge(show: boolean): void {
    if (process.platform === 'darwin') {
      // macOS: Use dock badge
      app.dock?.setBadge(show ? '!' : '');
    } else if (process.platform === 'linux') {
      // Linux: Use badge count for Unity/GNOME docks
      // Note: Requires Unity launcher or compatible dock
      app.setBadgeCount(show ? 1 : 0);
    }
    // Windows: Tray icon overlay requires native module (electron-windows-badge or similar)
    // Not implemented - would need additional dependencies
  }

  /**
   * Send a system notification with optional sound
   */
  private sendNotification(type: NotificationType, options: NotificationOptions): void {
    // Get notification settings
    const settings = this.getNotificationSettings(options.projectId);

    // Check if this notification type is enabled
    if (!this.isNotificationEnabled(type, settings)) {
      return;
    }

    // Create and show the notification
    if (Notification.isSupported()) {
      // Always set silent: true to prevent double sound (OS notification + shell.beep)
      // We handle sound ourselves via playNotificationSound() for consistent cross-platform behavior
      const notification = new Notification({
        title: options.title,
        body: options.body,
        silent: true
      });

      // Focus window when notification is clicked
      // Story 5.6 Task 6: Handle click to navigate to checkpoint
      notification.on('click', () => {
        const window = this.mainWindow?.();
        if (window) {
          if (window.isMinimized()) {
            window.restore();
          }
          window.focus();

          // For checkpoint notifications, send navigation event to renderer
          // Story 5.6 AC2: Clicking notification brings user to checkpoint dialog
          if (type === 'checkpoint-reached' && options.taskId && options.checkpointId && options.checkpointPhase) {
            window.webContents.send(
              IPC_CHANNELS.CHECKPOINT_REACHED,
              options.taskId,
              {
                checkpointId: options.checkpointId,
                phase: options.checkpointPhase,
                description: options.body,
                timestamp: new Date().toISOString()
              },
              options.projectId
            );
          }
        }
      });

      notification.show();
    }

    // Play sound if enabled (system beep)
    if (settings.sound) {
      this.playNotificationSound();
    }
  }

  /**
   * Play a notification sound
   */
  private playNotificationSound(): void {
    // Use system beep - works across all platforms
    shell.beep();
  }

  /**
   * Get notification settings for a project or fall back to defaults
   */
  private getNotificationSettings(projectId?: string): {
    onTaskComplete: boolean;
    onTaskFailed: boolean;
    onReviewNeeded: boolean;
    onTaskEscalated: boolean;
    onCheckpointReached: boolean;
    sound: boolean;
  } {
    // Try to get project-specific settings
    if (projectId) {
      const projects = projectStore.getProjects();
      const project = projects.find(p => p.id === projectId);
      if (project?.settings?.notifications) {
        // Handle optional fields (backward compatibility)
        return {
          ...project.settings.notifications,
          onTaskEscalated: project.settings.notifications.onTaskEscalated ?? true,
          onCheckpointReached: project.settings.notifications.onCheckpointReached ?? true,
        };
      }
    }

    // Fall back to defaults
    return {
      onTaskComplete: true,
      onTaskFailed: true,
      onReviewNeeded: true,
      onTaskEscalated: true,
      onCheckpointReached: true,
      sound: false
    };
  }

  /**
   * Check if a notification type is enabled in settings
   */
  private isNotificationEnabled(
    type: NotificationType,
    settings: {
      onTaskComplete: boolean;
      onTaskFailed: boolean;
      onReviewNeeded: boolean;
      onTaskEscalated: boolean;
      onCheckpointReached: boolean;
      sound: boolean;
    }
  ): boolean {
    switch (type) {
      case 'task-complete':
        return settings.onTaskComplete;
      case 'task-failed':
        return settings.onTaskFailed;
      case 'review-needed':
        return settings.onReviewNeeded;
      case 'task-escalated':
        return settings.onTaskEscalated;
      case 'checkpoint-reached':
        return settings.onCheckpointReached;
      default:
        return false;
    }
  }
}

// Export singleton instance
export const notificationService = new NotificationService();
