import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Brain, Scale, Zap, Check, Sparkles, ChevronDown, ChevronUp, RotateCcw } from 'lucide-react';
import { cn } from '../../lib/utils';
import { Label } from '../ui/label';
import { Button } from '../ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '../ui/select';
import {
  DEFAULT_AGENT_PROFILES,
  AVAILABLE_MODELS,
  THINKING_LEVELS,
  DEFAULT_PHASE_MODELS,
  DEFAULT_PHASE_THINKING,
  DEFAULT_BMAD_PHASE_MODELS,
  DEFAULT_BMAD_PHASE_THINKING,
  BMAD_PROFILE_PHASE_MODELS,
  BMAD_PROFILE_PHASE_THINKING,
} from '../../../shared/constants';
import type { ProjectSettings } from '../../../shared/types';
import type {
  AgentProfile,
  PhaseModelConfig,
  PhaseThinkingConfig,
  BmadPhaseModelConfig,
  BmadPhaseThinkingConfig,
  ModelTypeShort,
  ThinkingLevel
} from '../../../shared/types/settings';

interface AgentConfigSectionProps {
  settings: ProjectSettings;
  onUpdateSettings: (updates: Partial<ProjectSettings>) => void;
}

/**
 * Icon mapping for agent profile icons
 */
const iconMap: Record<string, React.ElementType> = {
  Brain,
  Scale,
  Zap,
  Sparkles,
};

// Native methodology phases
const NATIVE_PHASE_KEYS: Array<keyof PhaseModelConfig> = ['spec', 'planning', 'coding', 'qa'];

// BMAD methodology phases
const BMAD_PHASE_KEYS: Array<keyof BmadPhaseModelConfig> = [
  'analyze', 'prd', 'architecture', 'epics', 'stories', 'dev', 'review'
];

/**
 * Agent Configuration Section for Project Settings
 * Supports both Native and BMAD methodology phase configurations
 */
export function AgentConfigSection({ settings, onUpdateSettings }: AgentConfigSectionProps) {
  const { t } = useTranslation(['settings', 'artifacts']);
  const [showPhaseConfig, setShowPhaseConfig] = useState(true);

  const methodology = settings.methodology || 'native';
  const isBmad = methodology === 'bmad';
  const selectedProfileId = settings.selectedAgentProfile || 'auto';

  // Find the selected profile
  const selectedProfile = useMemo(() =>
    DEFAULT_AGENT_PROFILES.find(p => p.id === selectedProfileId) || DEFAULT_AGENT_PROFILES[0],
    [selectedProfileId]
  );

  // Get profile's default phase config based on methodology
  const profilePhaseModels = isBmad
    ? (BMAD_PROFILE_PHASE_MODELS[selectedProfileId] || DEFAULT_BMAD_PHASE_MODELS)
    : (selectedProfile.phaseModels || DEFAULT_PHASE_MODELS);
  const profilePhaseThinking = isBmad
    ? (BMAD_PROFILE_PHASE_THINKING[selectedProfileId] || DEFAULT_BMAD_PHASE_THINKING)
    : (selectedProfile.phaseThinking || DEFAULT_PHASE_THINKING);

  // Get current phase config from settings or fall back to profile defaults
  const currentPhaseModels = isBmad
    ? (settings.bmadPhaseModels || profilePhaseModels as BmadPhaseModelConfig)
    : (settings.customPhaseModels || profilePhaseModels as PhaseModelConfig);
  const currentPhaseThinking = isBmad
    ? (settings.bmadPhaseThinking || profilePhaseThinking as BmadPhaseThinkingConfig)
    : (settings.customPhaseThinking || profilePhaseThinking as PhaseThinkingConfig);

  // Check if current config differs from profile defaults
  const hasCustomConfig = useMemo((): boolean => {
    if (isBmad) {
      if (!settings.bmadPhaseModels && !settings.bmadPhaseThinking) return false;
      return BMAD_PHASE_KEYS.some(
        phase =>
          (currentPhaseModels as BmadPhaseModelConfig)[phase] !== (profilePhaseModels as BmadPhaseModelConfig)[phase] ||
          (currentPhaseThinking as BmadPhaseThinkingConfig)[phase] !== (profilePhaseThinking as BmadPhaseThinkingConfig)[phase]
      );
    } else {
      if (!settings.customPhaseModels && !settings.customPhaseThinking) return false;
      return NATIVE_PHASE_KEYS.some(
        phase =>
          (currentPhaseModels as PhaseModelConfig)[phase] !== (profilePhaseModels as PhaseModelConfig)[phase] ||
          (currentPhaseThinking as PhaseThinkingConfig)[phase] !== (profilePhaseThinking as PhaseThinkingConfig)[phase]
      );
    }
  }, [settings, currentPhaseModels, currentPhaseThinking, profilePhaseModels, profilePhaseThinking, isBmad]);

  const handleSelectProfile = (profileId: string) => {
    // When selecting a preset, reset to that preset's defaults
    if (isBmad) {
      onUpdateSettings({
        selectedAgentProfile: profileId,
        bmadPhaseModels: undefined,
        bmadPhaseThinking: undefined
      });
    } else {
      onUpdateSettings({
        selectedAgentProfile: profileId,
        customPhaseModels: undefined,
        customPhaseThinking: undefined
      });
    }
  };

  const handlePhaseModelChange = (phase: string, value: ModelTypeShort) => {
    if (isBmad) {
      const newPhaseModels = { ...currentPhaseModels, [phase]: value } as BmadPhaseModelConfig;
      onUpdateSettings({ bmadPhaseModels: newPhaseModels });
    } else {
      const newPhaseModels = { ...currentPhaseModels, [phase]: value } as PhaseModelConfig;
      onUpdateSettings({ customPhaseModels: newPhaseModels });
    }
  };

  const handlePhaseThinkingChange = (phase: string, value: ThinkingLevel) => {
    if (isBmad) {
      const newPhaseThinking = { ...currentPhaseThinking, [phase]: value } as BmadPhaseThinkingConfig;
      onUpdateSettings({ bmadPhaseThinking: newPhaseThinking });
    } else {
      const newPhaseThinking = { ...currentPhaseThinking, [phase]: value } as PhaseThinkingConfig;
      onUpdateSettings({ customPhaseThinking: newPhaseThinking });
    }
  };

  const handleResetToProfileDefaults = () => {
    if (isBmad) {
      onUpdateSettings({
        bmadPhaseModels: undefined,
        bmadPhaseThinking: undefined
      });
    } else {
      onUpdateSettings({
        customPhaseModels: undefined,
        customPhaseThinking: undefined
      });
    }
  };

  const getModelLabel = (modelValue: string): string => {
    const model = AVAILABLE_MODELS.find((m) => m.value === modelValue);
    return model?.label || modelValue;
  };

  const getThinkingLabel = (thinkingValue: string): string => {
    const level = THINKING_LEVELS.find((l) => l.value === thinkingValue);
    return level?.label || thinkingValue;
  };

  const renderProfileCard = (profile: AgentProfile) => {
    const isSelected = selectedProfileId === profile.id;
    const isCustomized = isSelected && hasCustomConfig;
    const Icon = iconMap[profile.icon || 'Brain'] || Brain;

    return (
      <button
        key={profile.id}
        onClick={() => handleSelectProfile(profile.id)}
        className={cn(
          'relative w-full rounded-lg border p-3 text-left transition-all duration-200',
          'hover:border-primary/50 hover:shadow-sm',
          isSelected
            ? 'border-primary bg-primary/5'
            : 'border-border bg-card'
        )}
      >
        {isSelected && (
          <div className="absolute right-2 top-2 flex h-4 w-4 items-center justify-center rounded-full bg-primary">
            <Check className="h-2.5 w-2.5 text-primary-foreground" />
          </div>
        )}

        <div className="flex items-start gap-2">
          <div
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded-md shrink-0',
              isSelected ? 'bg-primary/10' : 'bg-muted'
            )}
          >
            <Icon
              className={cn(
                'h-4 w-4',
                isSelected ? 'text-primary' : 'text-muted-foreground'
              )}
            />
          </div>

          <div className="flex-1 min-w-0 pr-4">
            <div className="flex items-center gap-1.5">
              <h3 className="font-medium text-xs text-foreground">{profile.name}</h3>
              {isCustomized && (
                <span className="inline-flex items-center rounded bg-amber-500/10 px-1 py-0.5 text-[8px] font-medium text-amber-600 dark:text-amber-400">
                  {t('settings:agentProfile.customized')}
                </span>
              )}
            </div>
            <p className="mt-0.5 text-[10px] text-muted-foreground line-clamp-1">
              {profile.description}
            </p>
            <div className="mt-1.5 flex flex-wrap gap-1">
              <span className="inline-flex items-center rounded bg-muted px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground">
                {getModelLabel(profile.model)}
              </span>
              <span className="inline-flex items-center rounded bg-muted px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground">
                {getThinkingLabel(profile.thinkingLevel)}
              </span>
            </div>
          </div>
        </div>
      </button>
    );
  };

  // Get phase keys and labels based on methodology
  const phaseKeys = isBmad ? BMAD_PHASE_KEYS : NATIVE_PHASE_KEYS;

  const getPhaseLabel = (phase: string): string => {
    if (isBmad) {
      return t(`artifacts:phases.bmad.${phase}`, { defaultValue: phase });
    }
    return t(`settings:agentProfile.phases.${phase}.label`, { defaultValue: phase });
  };

  const getPhaseDescription = (phase: string): string => {
    if (isBmad) {
      const descriptions: Record<string, string> = {
        analyze: 'Project analysis and documentation',
        prd: 'Product Requirements Document creation',
        architecture: 'System architecture design',
        epics: 'Epic and story breakdown',
        stories: 'Story preparation and refinement',
        dev: 'Development and implementation',
        review: 'Code review and validation'
      };
      return descriptions[phase] || '';
    }
    return t(`settings:agentProfile.phases.${phase}.description`, { defaultValue: '' });
  };

  return (
    <section className="space-y-4">
      <h3 className="text-sm font-semibold text-foreground">
        {t('settings:agentProfile.title')}
      </h3>

      {/* Methodology indicator */}
      <div className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
        <span className="font-medium">
          {isBmad ? 'BMAD Method' : 'Native Auto Claude'}
        </span>
        {' '} - {isBmad ? '7 phases' : '4 phases'}
      </div>

      {/* Profile cards - 2x2 grid */}
      <div className="grid grid-cols-2 gap-2">
        {DEFAULT_AGENT_PROFILES.map(renderProfileCard)}
      </div>

      {/* Phase Configuration */}
      <div className="rounded-lg border border-border bg-card">
        <button
          type="button"
          onClick={() => setShowPhaseConfig(!showPhaseConfig)}
          className="flex w-full items-center justify-between p-3 text-left hover:bg-muted/50 transition-colors rounded-t-lg"
        >
          <div>
            <h4 className="font-medium text-xs text-foreground">
              {t('settings:agentProfile.phaseConfiguration')}
            </h4>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              {isBmad
                ? 'Configure model and thinking for each BMAD phase'
                : t('settings:agentProfile.phaseConfigurationDescription')}
            </p>
          </div>
          {showPhaseConfig ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </button>

        {showPhaseConfig && (
          <div className="border-t border-border p-3 space-y-3">
            {/* Reset button */}
            {hasCustomConfig && (
              <div className="flex justify-end">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleResetToProfileDefaults}
                  className="text-[10px] h-6"
                >
                  <RotateCcw className="h-2.5 w-2.5 mr-1" />
                  {t('settings:agentProfile.resetToProfileDefaults', { profile: selectedProfile.name })}
                </Button>
              </div>
            )}

            {/* Phase Configuration Grid */}
            <div className="space-y-3">
              {phaseKeys.map((phase) => (
                <div key={phase} className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-medium text-foreground capitalize">
                      {getPhaseLabel(phase)}
                    </Label>
                    <span className="text-[9px] text-muted-foreground">
                      {getPhaseDescription(phase)}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {/* Model Select */}
                    <div className="space-y-0.5">
                      <Label className="text-[9px] text-muted-foreground">
                        {t('settings:agentProfile.model')}
                      </Label>
                      <Select
                        value={(currentPhaseModels as unknown as Record<string, string>)[phase]}
                        onValueChange={(value) => handlePhaseModelChange(phase, value as ModelTypeShort)}
                      >
                        <SelectTrigger className="h-7 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {AVAILABLE_MODELS.map((m) => (
                            <SelectItem key={m.value} value={m.value} className="text-xs">
                              {m.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    {/* Thinking Level Select */}
                    <div className="space-y-0.5">
                      <Label className="text-[9px] text-muted-foreground">
                        {t('settings:agentProfile.thinkingLevel')}
                      </Label>
                      <Select
                        value={(currentPhaseThinking as unknown as Record<string, string>)[phase]}
                        onValueChange={(value) => handlePhaseThinkingChange(phase, value as ThinkingLevel)}
                      >
                        <SelectTrigger className="h-7 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {THINKING_LEVELS.map((level) => (
                            <SelectItem key={level.value} value={level.value} className="text-xs">
                              {level.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <p className="text-[9px] text-muted-foreground mt-2 pt-2 border-t border-border">
              {t('settings:agentProfile.phaseConfigNote')}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
