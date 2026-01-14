/**
 * ExecutionModeTabs - Tab selector for Full Auto vs Semi-Auto execution modes
 *
 * Allows users to choose between:
 * - Full Auto: Tasks run autonomously without interruption
 * - Semi-Auto: Review and approve at key checkpoints (planning, coding, validation)
 */
import { useTranslation } from 'react-i18next';
import { Zap, UserCheck } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/tabs';
import { cn } from '../../lib/utils';
import type { ExecutionMode } from '../../../shared/types/task';

// Re-export for convenience
export type { ExecutionMode };

interface ExecutionModeTabsProps {
  /** Currently selected execution mode */
  value: ExecutionMode;
  /** Callback when execution mode changes */
  onChange: (value: ExecutionMode) => void;
  /** Whether the tabs are disabled */
  disabled?: boolean;
}

export function ExecutionModeTabs({ value, onChange, disabled = false }: ExecutionModeTabsProps) {
  const { t } = useTranslation(['tasks']);

  return (
    <div className="space-y-3">
      <Tabs
        value={value}
        onValueChange={(v) => onChange(v as ExecutionMode)}
      >
        <TabsList className="grid w-full grid-cols-2 h-11">
          <TabsTrigger
            value="full_auto"
            disabled={disabled}
            className="gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            <Zap className="h-4 w-4" />
            {t('tasks:executionMode.fullAuto.title')}
          </TabsTrigger>
          <TabsTrigger
            value="semi_auto"
            disabled={disabled}
            className="gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            <UserCheck className="h-4 w-4" />
            {t('tasks:executionMode.semiAuto.title')}
          </TabsTrigger>
        </TabsList>

        <TabsContent
          value="full_auto"
          className="mt-4"
          aria-label={t('tasks:executionMode.fullAuto.title')}
        >
          <div className={cn(
            'p-4 rounded-lg border border-border bg-muted/30',
            'space-y-2'
          )}>
            <p className="text-sm text-muted-foreground">
              {t('tasks:executionMode.fullAuto.description')}
            </p>
          </div>
        </TabsContent>

        <TabsContent
          value="semi_auto"
          className="mt-4"
          aria-label={t('tasks:executionMode.semiAuto.title')}
        >
          <div className={cn(
            'p-4 rounded-lg border border-border bg-muted/30',
            'space-y-3'
          )}>
            <p className="text-sm text-muted-foreground">
              {t('tasks:executionMode.semiAuto.description')}
            </p>
            <ul className="space-y-2 text-sm" aria-label="Checkpoints">
              <li className="flex items-start gap-2">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-medium" aria-hidden="true">
                  1
                </span>
                <span className="text-muted-foreground">
                  {t('tasks:executionMode.semiAuto.checkpoints.planning')}
                </span>
              </li>
              <li className="flex items-start gap-2">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-medium" aria-hidden="true">
                  2
                </span>
                <span className="text-muted-foreground">
                  {t('tasks:executionMode.semiAuto.checkpoints.coding')}
                </span>
              </li>
              <li className="flex items-start gap-2">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-medium" aria-hidden="true">
                  3
                </span>
                <span className="text-muted-foreground">
                  {t('tasks:executionMode.semiAuto.checkpoints.validation')}
                </span>
              </li>
            </ul>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
