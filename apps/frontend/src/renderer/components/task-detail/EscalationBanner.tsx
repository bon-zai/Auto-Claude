/**
 * Escalation Banner Component
 * Story Reference: Story 4.5 - Implement Task Escalation Handling
 *
 * Displays escalation information for tasks that couldn't complete autonomously.
 * AC #5: Banner showing escalation reason and failure details
 * AC #6: Guidance input textarea
 * AC #7: Retry button that passes guidance to backend
 */

import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Play,
  ChevronDown,
  ChevronUp,
  MessageSquare
} from 'lucide-react';
import { useState } from 'react';
import { Button } from '../ui/button';
import { Textarea } from '../ui/textarea';
import { cn } from '../../lib/utils';
import type { EscalationInfo, EscalationReason } from '../../../shared/types';

interface EscalationBannerProps {
  escalationInfo: EscalationInfo;
  isRetrying: boolean;
  onRetry: (guidance?: string) => void;
}

/**
 * Get i18n key for escalation reason
 */
function getReasonKey(reason: EscalationReason): string {
  const reasonKeys: Record<EscalationReason, string> = {
    max_retries_exceeded: 'tasks:escalation.reasons.maxRetriesExceeded',
    unfixable_qa_issues: 'tasks:escalation.reasons.unfixableQaIssues',
    external_service_failure: 'tasks:escalation.reasons.externalServiceFailure',
    user_defined: 'tasks:escalation.reasons.userDefined',
    validation_failed: 'tasks:escalation.reasons.validationFailed',
    unknown: 'tasks:escalation.reasons.unknown',
  };
  return reasonKeys[reason] || reasonKeys.unknown;
}

/**
 * Get i18n key for failed phase
 */
function getPhaseKey(phase: string): string {
  const phaseKeys: Record<string, string> = {
    planning: 'tasks:execution.phases.planning',
    coding: 'tasks:execution.phases.coding',
    validation: 'tasks:execution.phases.reviewing',
    qa_review: 'tasks:execution.phases.reviewing',
    qa_fixing: 'tasks:execution.phases.fixing',
  };
  return phaseKeys[phase] || 'tasks:execution.phases.idle';
}

export function EscalationBanner({
  escalationInfo,
  isRetrying,
  onRetry
}: EscalationBannerProps) {
  const { t } = useTranslation(['tasks', 'common']);
  const [showDetails, setShowDetails] = useState(false);
  const [guidance, setGuidance] = useState('');

  const handleRetry = () => {
    onRetry(guidance.trim() || undefined);
  };

  return (
    <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          {/* Header */}
          <h3 className="font-medium text-sm text-foreground mb-1">
            {t('tasks:escalation.title')}
          </h3>

          {/* Reason */}
          <p className="text-sm text-muted-foreground mb-2">
            {t(getReasonKey(escalationInfo.reason))}
          </p>

          {/* Phase info */}
          <div className="text-xs text-muted-foreground mb-3">
            <span className="font-medium">{t('tasks:escalation.failedDuring')}: </span>
            <span className="text-foreground">{t(getPhaseKey(escalationInfo.failedPhase))}</span>
            {escalationInfo.subtaskId && (
              <span className="ml-2 text-muted-foreground">
                ({t('tasks:escalation.subtask')}: {escalationInfo.subtaskId})
              </span>
            )}
          </div>

          {/* Error message */}
          <div className="bg-card/50 border border-border rounded-lg p-3 mb-3">
            <p className="text-sm text-foreground break-words">
              {escalationInfo.errorMessage}
            </p>
          </div>

          {/* Expandable details */}
          <button
            type="button"
            onClick={() => setShowDetails(!showDetails)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors mb-3"
          >
            {showDetails ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
            {t('tasks:escalation.showDetails')}
          </button>

          {showDetails && (
            <div className="space-y-3 mb-4">
              {/* Attempted fixes */}
              {escalationInfo.attemptedFixes.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-foreground mb-1">
                    {t('tasks:escalation.attemptedFixes')}
                  </h4>
                  <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
                    {escalationInfo.attemptedFixes.map((fix, index) => (
                      <li key={index} className="truncate">{fix}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Stack trace */}
              {escalationInfo.errorTrace && (
                <div>
                  <h4 className="text-xs font-medium text-foreground mb-1">
                    {t('tasks:escalation.stackTrace')}
                  </h4>
                  <pre className="text-xs bg-card/50 border border-border rounded p-2 overflow-x-auto max-h-32 text-muted-foreground">
                    {escalationInfo.errorTrace}
                  </pre>
                </div>
              )}

              {/* Context */}
              {Object.keys(escalationInfo.context).length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-foreground mb-1">
                    {t('tasks:escalation.context')}
                  </h4>
                  <pre className="text-xs bg-card/50 border border-border rounded p-2 overflow-x-auto max-h-32 text-muted-foreground">
                    {JSON.stringify(escalationInfo.context, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}

          {/* Guidance input - AC #6 */}
          <div className="mb-3">
            <label className="flex items-center gap-2 text-xs font-medium text-foreground mb-2">
              <MessageSquare className="h-3 w-3" />
              {t('tasks:escalation.guidanceLabel')}
            </label>
            <Textarea
              value={guidance}
              onChange={(e) => setGuidance(e.target.value)}
              placeholder={t('tasks:escalation.guidancePlaceholder')}
              className="text-sm min-h-[80px] resize-y"
              disabled={isRetrying}
            />
            <p className="text-xs text-muted-foreground mt-1">
              {t('tasks:escalation.guidanceHint')}
            </p>
          </div>

          {/* Retry button - AC #7 */}
          <Button
            variant="default"
            size="sm"
            onClick={handleRetry}
            disabled={isRetrying}
            className={cn(
              "w-full",
              guidance.trim() && "bg-primary hover:bg-primary/90"
            )}
          >
            <Play className="mr-2 h-4 w-4" />
            {guidance.trim()
              ? t('tasks:escalation.retryWithGuidance')
              : t('tasks:escalation.retry')}
          </Button>
        </div>
      </div>
    </div>
  );
}
