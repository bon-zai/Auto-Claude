import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Workflow, Loader2, AlertCircle, Zap, Layers } from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent } from '../ui/card';
import { Badge } from '../ui/badge';
import { cn } from '../../lib/utils';
import { useSettingsStore } from '../../stores/settings-store';

interface MethodologyStepProps {
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}

/**
 * Methodology selection card component
 * Displays a methodology option with icon, description, phases, and use case
 */
interface MethodologyCardProps {
  name: 'native' | 'bmad';
  selected: boolean;
  onSelect: () => void;
  disabled?: boolean;
}

function MethodologyCard({ name, selected, onSelect, disabled }: MethodologyCardProps) {
  const { t } = useTranslation(['onboarding']);

  const icons = {
    native: Zap,
    bmad: Layers
  };

  const Icon = icons[name];

  // Get phases array from i18n (returnObjects: true for arrays)
  const phases = t(`onboarding:methodology.${name}.phases`, { returnObjects: true }) as string[];

  return (
    <Card
      className={cn(
        'cursor-pointer transition-all hover:border-primary/50',
        selected && 'border-primary border-2',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
      onClick={!disabled ? onSelect : undefined}
      role="radio"
      aria-checked={selected}
      tabIndex={disabled ? -1 : 0}
      onKeyDown={(e) => {
        if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onSelect();
        }
      }}
    >
      <CardContent className="p-5">
        <div className="flex items-start gap-4">
          <div className={cn(
            'flex h-10 w-10 shrink-0 items-center justify-center rounded-full',
            selected ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'
          )}>
            <Icon className="h-5 w-5" />
          </div>
          <div className="flex-1 space-y-3">
            <div>
              <h3 className="text-base font-semibold text-foreground">
                {t(`onboarding:methodology.${name}.title`)}
              </h3>
              <p className="text-sm text-muted-foreground mt-1">
                {t(`onboarding:methodology.${name}.description`)}
              </p>
            </div>

            {/* Phases as badges */}
            <div className="flex flex-wrap gap-1.5">
              {phases.map((phase) => (
                <Badge
                  key={phase}
                  variant="secondary"
                  className="text-xs font-normal"
                >
                  {phase}
                </Badge>
              ))}
            </div>

            <p className="text-xs text-muted-foreground italic">
              {t(`onboarding:methodology.${name}.bestFor`)}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Onboarding step for selecting default methodology.
 * Allows users to choose between Native and BMAD methodologies
 * during the initial onboarding flow.
 *
 * - AC1: Displays methodology options with descriptions
 * - AC2: Saves selection as default in settings
 * - AC3: Defaults to Native when skipped
 */
export function MethodologyStep({ onNext, onBack, onSkip }: MethodologyStepProps) {
  const { t } = useTranslation(['onboarding', 'common']);
  const { settings, updateSettings } = useSettingsStore();
  const [selectedMethodology, setSelectedMethodology] = useState<string>(
    settings.defaultMethodology || 'native'
  );
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSelect = (methodology: string) => {
    setSelectedMethodology(methodology);
    setError(null);
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    try {
      const result = await window.electronAPI.saveSettings({
        defaultMethodology: selectedMethodology
      });
      if (result?.success) {
        updateSettings({ defaultMethodology: selectedMethodology });
        onNext();
      } else {
        setError(result?.error || 'Failed to save methodology preference');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error occurred');
    } finally {
      setIsSaving(false);
    }
  };

  const handleSkip = async () => {
    // When skipping, default to 'native' methodology
    // Always update local store to ensure UI consistency (AC#3)
    setIsSaving(true);
    setError(null);
    try {
      const result = await window.electronAPI.saveSettings({
        defaultMethodology: 'native'
      });
      if (result?.success) {
        updateSettings({ defaultMethodology: 'native' });
        onSkip();
      } else {
        // Even if save to disk fails, update local store for UI consistency
        updateSettings({ defaultMethodology: 'native' });
        onSkip();
      }
    } catch {
      // Even if save throws, update local store for UI consistency
      updateSettings({ defaultMethodology: 'native' });
      onSkip();
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex h-full flex-col items-center justify-center px-8 py-6">
      <div className="w-full max-w-2xl">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Workflow className="h-7 w-7" />
            </div>
          </div>
          <h1 className="text-2xl font-bold text-foreground tracking-tight">
            {t('onboarding:methodology.title')}
          </h1>
          <p id="methodology-description" className="mt-2 text-muted-foreground">
            {t('onboarding:methodology.description')}
          </p>
        </div>

        {/* Methodology Cards */}
        <div
          className="grid grid-cols-1 gap-4"
          role="radiogroup"
          aria-label={t('onboarding:methodology.title')}
          aria-describedby="methodology-description"
        >
          <MethodologyCard
            name="native"
            selected={selectedMethodology === 'native'}
            onSelect={() => handleSelect('native')}
            disabled={isSaving}
          />
          <MethodologyCard
            name="bmad"
            selected={selectedMethodology === 'bmad'}
            onSelect={() => handleSelect('bmad')}
            disabled={isSaving}
          />
        </div>

        {/* Error Display */}
        {error && (
          <div className="flex items-start gap-2 p-3 mt-6 rounded-md bg-destructive/10 text-destructive text-sm">
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
            {error}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex justify-between items-center mt-10 pt-6 border-t border-border">
          <Button
            variant="ghost"
            onClick={onBack}
            disabled={isSaving}
            className="text-muted-foreground hover:text-foreground"
          >
            {t('onboarding:methodology.back')}
          </Button>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={handleSkip}
              disabled={isSaving}
            >
              {t('onboarding:methodology.skip')}
            </Button>
            <Button
              onClick={handleSave}
              disabled={isSaving}
            >
              {isSaving ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  {t('common:saving', 'Saving...')}
                </>
              ) : (
                t('onboarding:methodology.continue')
              )}
            </Button>
          </div>
        </div>

        {/* Skip hint */}
        <p className="text-center text-xs text-muted-foreground mt-4">
          {t('onboarding:methodology.skipDefault')}
        </p>
      </div>
    </div>
  );
}
