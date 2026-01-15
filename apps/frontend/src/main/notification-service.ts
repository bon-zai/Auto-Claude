import { Notification, shell } from 'electron';
import type { BrowserWindow } from 'electron';
import { projectStore } from './project-store';

export type NotificationType = 'task-complete' | 'task-failed' | 'review-needed' | 'task-escalated';

interface NotificationOptions {
  title: string;
  body: string;
  projectId?: string;
  taskId?: string;
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
      const notification = new Notification({
        title: options.title,
        body: options.body,
        silent: !settings.sound // Let the OS handle sound if enabled
      });

      // Focus window when notification is clicked
      notification.on('click', () => {
        const window = this.mainWindow?.();
        if (window) {
          if (window.isMinimized()) {
            window.restore();
          }
          window.focus();
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
    sound: boolean;
  } {
    // Try to get project-specific settings
    if (projectId) {
      const projects = projectStore.getProjects();
      const project = projects.find(p => p.id === projectId);
      if (project?.settings?.notifications) {
        // Handle optional onTaskEscalated (backward compatibility)
        return {
          ...project.settings.notifications,
          onTaskEscalated: project.settings.notifications.onTaskEscalated ?? true,
        };
      }
    }

    // Fall back to defaults
    return {
      onTaskComplete: true,
      onTaskFailed: true,
      onReviewNeeded: true,
      onTaskEscalated: true,
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
      default:
        return false;
    }
  }
}

// Export singleton instance
export const notificationService = new NotificationService();
