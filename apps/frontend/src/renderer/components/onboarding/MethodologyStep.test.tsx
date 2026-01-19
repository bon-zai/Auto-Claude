/**
 * @vitest-environment jsdom
 */
/**
 * MethodologyStep tests
 *
 * Tests for the methodology selection step in the onboarding wizard.
 * Verifies:
 * - Component renders correctly with methodology options
 * - Selection updates state
 * - Skip defaults to Native methodology
 * - Continue saves selected methodology to settings
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MethodologyStep } from './MethodologyStep';

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { returnObjects?: boolean }) => {
      // Handle array returns for phases
      const arrayTranslations: Record<string, string[]> = {
        'onboarding:methodology.native.phases': ['Discovery', 'Spec', 'Plan', 'Code', 'Validate'],
        'onboarding:methodology.bmad.phases': ['PRD', 'Architecture', 'Epics', 'Stories', 'Dev', 'Review']
      };

      if (options?.returnObjects && arrayTranslations[key]) {
        return arrayTranslations[key];
      }

      const translations: Record<string, string> = {
        'onboarding:methodology.title': 'Choose Your Methodology',
        'onboarding:methodology.description': 'Select how you want Auto Claude to approach your tasks.',
        'onboarding:methodology.native.title': 'Native',
        'onboarding:methodology.native.description': 'Fast, focused execution with minimal overhead',
        'onboarding:methodology.native.bestFor': 'Best for: Quick fixes, small features, bug fixes',
        'onboarding:methodology.bmad.title': 'BMAD',
        'onboarding:methodology.bmad.description': 'Comprehensive planning with full documentation',
        'onboarding:methodology.bmad.bestFor': 'Best for: New projects, large features, team collaboration',
        'onboarding:methodology.back': 'Back',
        'onboarding:methodology.skip': 'Skip',
        'onboarding:methodology.continue': 'Continue',
        'onboarding:methodology.skipDefault': 'Skipping will set Native as your default methodology.',
        'common:saving': 'Saving...'
      };
      return translations[key] || key;
    },
    i18n: { language: 'en' }
  })
}));

// Mock settings store
const mockUpdateSettings = vi.fn();
vi.mock('../../stores/settings-store', () => ({
  useSettingsStore: vi.fn(() => ({
    settings: { defaultMethodology: undefined },
    updateSettings: mockUpdateSettings
  }))
}));

// Mock electronAPI
const mockSaveSettings = vi.fn().mockResolvedValue({ success: true });

Object.defineProperty(window, 'electronAPI', {
  value: {
    saveSettings: mockSaveSettings
  },
  writable: true
});

describe('MethodologyStep', () => {
  const defaultProps = {
    onNext: vi.fn(),
    onBack: vi.fn(),
    onSkip: vi.fn()
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders step with title and description', () => {
      render(<MethodologyStep {...defaultProps} />);

      expect(screen.getByText('Choose Your Methodology')).toBeInTheDocument();
      expect(screen.getByText(/Select how you want Auto Claude/)).toBeInTheDocument();
    });

    it('renders both methodology options', () => {
      render(<MethodologyStep {...defaultProps} />);

      expect(screen.getByText('Native')).toBeInTheDocument();
      expect(screen.getByText('BMAD')).toBeInTheDocument();
    });

    it('renders methodology descriptions', () => {
      render(<MethodologyStep {...defaultProps} />);

      expect(screen.getByText(/Fast, focused execution/)).toBeInTheDocument();
      expect(screen.getByText(/Comprehensive planning/)).toBeInTheDocument();
    });

    it('renders methodology phase badges', () => {
      render(<MethodologyStep {...defaultProps} />);

      // Native phases
      expect(screen.getByText('Discovery')).toBeInTheDocument();
      expect(screen.getByText('Spec')).toBeInTheDocument();
      expect(screen.getByText('Plan')).toBeInTheDocument();
      expect(screen.getByText('Code')).toBeInTheDocument();
      expect(screen.getByText('Validate')).toBeInTheDocument();

      // BMAD phases
      expect(screen.getByText('PRD')).toBeInTheDocument();
      expect(screen.getByText('Architecture')).toBeInTheDocument();
      expect(screen.getByText('Epics')).toBeInTheDocument();
      expect(screen.getByText('Stories')).toBeInTheDocument();
      expect(screen.getByText('Dev')).toBeInTheDocument();
      expect(screen.getByText('Review')).toBeInTheDocument();
    });

    it('renders use case recommendations', () => {
      render(<MethodologyStep {...defaultProps} />);

      expect(screen.getByText(/Quick fixes, small features/)).toBeInTheDocument();
      expect(screen.getByText(/New projects, large features/)).toBeInTheDocument();
    });

    it('renders navigation buttons', () => {
      render(<MethodologyStep {...defaultProps} />);

      expect(screen.getByRole('button', { name: /Back/ })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Skip/ })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Continue/ })).toBeInTheDocument();
    });

    it('renders skip hint text', () => {
      render(<MethodologyStep {...defaultProps} />);

      expect(screen.getByText(/Skipping will set Native as your default/)).toBeInTheDocument();
    });
  });

  describe('Selection Behavior', () => {
    it('defaults to Native methodology when no setting exists', () => {
      render(<MethodologyStep {...defaultProps} />);

      // Native card should have selected styling (border-primary)
      const nativeCard = screen.getByText('Native').closest('[role="radio"]');
      expect(nativeCard).toHaveAttribute('aria-checked', 'true');

      const bmadCard = screen.getByText('BMAD').closest('[role="radio"]');
      expect(bmadCard).toHaveAttribute('aria-checked', 'false');
    });

    it('updates selection when BMAD is clicked', () => {
      render(<MethodologyStep {...defaultProps} />);

      const bmadCard = screen.getByText('BMAD').closest('[role="radio"]');
      fireEvent.click(bmadCard!);

      expect(bmadCard).toHaveAttribute('aria-checked', 'true');

      const nativeCard = screen.getByText('Native').closest('[role="radio"]');
      expect(nativeCard).toHaveAttribute('aria-checked', 'false');
    });

    it('supports keyboard selection with Enter', () => {
      render(<MethodologyStep {...defaultProps} />);

      const bmadCard = screen.getByText('BMAD').closest('[role="radio"]');
      fireEvent.keyDown(bmadCard!, { key: 'Enter' });

      expect(bmadCard).toHaveAttribute('aria-checked', 'true');
    });

    it('supports keyboard selection with Space', () => {
      render(<MethodologyStep {...defaultProps} />);

      const bmadCard = screen.getByText('BMAD').closest('[role="radio"]');
      fireEvent.keyDown(bmadCard!, { key: ' ' });

      expect(bmadCard).toHaveAttribute('aria-checked', 'true');
    });
  });

  describe('Save Behavior', () => {
    it('saves selected methodology and calls onNext on Continue', async () => {
      render(<MethodologyStep {...defaultProps} />);

      // Select BMAD
      const bmadCard = screen.getByText('BMAD').closest('[role="radio"]');
      fireEvent.click(bmadCard!);

      // Click Continue
      const continueButton = screen.getByRole('button', { name: /Continue/ });
      fireEvent.click(continueButton);

      await waitFor(() => {
        expect(mockSaveSettings).toHaveBeenCalledWith({
          defaultMethodology: 'bmad'
        });
      });

      await waitFor(() => {
        expect(mockUpdateSettings).toHaveBeenCalledWith({
          defaultMethodology: 'bmad'
        });
      });

      await waitFor(() => {
        expect(defaultProps.onNext).toHaveBeenCalled();
      });
    });

    it('saves native methodology when Continue is clicked with default', async () => {
      render(<MethodologyStep {...defaultProps} />);

      // Click Continue without changing selection
      const continueButton = screen.getByRole('button', { name: /Continue/ });
      fireEvent.click(continueButton);

      await waitFor(() => {
        expect(mockSaveSettings).toHaveBeenCalledWith({
          defaultMethodology: 'native'
        });
      });

      await waitFor(() => {
        expect(defaultProps.onNext).toHaveBeenCalled();
      });
    });
  });

  describe('Skip Behavior', () => {
    it('saves native as default and calls onSkip when Skip is clicked', async () => {
      render(<MethodologyStep {...defaultProps} />);

      // Select BMAD first (to verify skip resets to native)
      const bmadCard = screen.getByText('BMAD').closest('[role="radio"]');
      fireEvent.click(bmadCard!);

      // Click Skip
      const skipButton = screen.getByRole('button', { name: /Skip/ });
      fireEvent.click(skipButton);

      await waitFor(() => {
        expect(mockSaveSettings).toHaveBeenCalledWith({
          defaultMethodology: 'native'
        });
      });

      await waitFor(() => {
        expect(defaultProps.onSkip).toHaveBeenCalled();
      });
    });

    it('updates local store and proceeds with skip even if save fails', async () => {
      mockSaveSettings.mockResolvedValueOnce({ success: false, error: 'Save failed' });

      render(<MethodologyStep {...defaultProps} />);

      const skipButton = screen.getByRole('button', { name: /Skip/ });
      fireEvent.click(skipButton);

      // AC#3: Even if save to disk fails, local store must be updated to 'native'
      await waitFor(() => {
        expect(mockUpdateSettings).toHaveBeenCalledWith({
          defaultMethodology: 'native'
        });
      });

      await waitFor(() => {
        expect(defaultProps.onSkip).toHaveBeenCalled();
      });
    });

    it('updates local store and proceeds with skip even if save throws', async () => {
      mockSaveSettings.mockRejectedValueOnce(new Error('Network error'));

      render(<MethodologyStep {...defaultProps} />);

      const skipButton = screen.getByRole('button', { name: /Skip/ });
      fireEvent.click(skipButton);

      // AC#3: Even if save throws exception, local store must be updated to 'native'
      await waitFor(() => {
        expect(mockUpdateSettings).toHaveBeenCalledWith({
          defaultMethodology: 'native'
        });
      });

      await waitFor(() => {
        expect(defaultProps.onSkip).toHaveBeenCalled();
      });
    });
  });

  describe('Back Button', () => {
    it('calls onBack when Back button is clicked', () => {
      render(<MethodologyStep {...defaultProps} />);

      const backButton = screen.getByRole('button', { name: /Back/ });
      fireEvent.click(backButton);

      expect(defaultProps.onBack).toHaveBeenCalled();
    });
  });

  describe('Error Handling', () => {
    it('displays error message when save fails', async () => {
      mockSaveSettings.mockResolvedValueOnce({ success: false, error: 'Failed to save' });

      render(<MethodologyStep {...defaultProps} />);

      const continueButton = screen.getByRole('button', { name: /Continue/ });
      fireEvent.click(continueButton);

      await waitFor(() => {
        expect(screen.getByText('Failed to save')).toBeInTheDocument();
      });

      // Should not call onNext on error
      expect(defaultProps.onNext).not.toHaveBeenCalled();
    });
  });

  describe('Accessibility', () => {
    it('has proper radiogroup role', () => {
      render(<MethodologyStep {...defaultProps} />);

      const radiogroup = screen.getByRole('radiogroup');
      expect(radiogroup).toBeInTheDocument();
    });

    it('methodology cards have radio role with aria-checked', () => {
      render(<MethodologyStep {...defaultProps} />);

      const radios = screen.getAllByRole('radio');
      expect(radios).toHaveLength(2);
    });

    it('radiogroup has aria-describedby linking to description', () => {
      render(<MethodologyStep {...defaultProps} />);

      const radiogroup = screen.getByRole('radiogroup');
      expect(radiogroup).toHaveAttribute('aria-describedby', 'methodology-description');

      // Verify the description element exists with correct id
      const description = document.getElementById('methodology-description');
      expect(description).toBeInTheDocument();
      expect(description?.textContent).toContain('Select how you want Auto Claude');
    });
  });
});
