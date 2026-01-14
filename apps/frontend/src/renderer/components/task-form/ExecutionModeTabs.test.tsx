/**
 * @vitest-environment jsdom
 */
/**
 * Tests for ExecutionModeTabs component
 */
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { ExecutionModeTabs } from './ExecutionModeTabs';

// Mock i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'tasks:executionMode.fullAuto.title': 'Full Auto',
        'tasks:executionMode.fullAuto.description': 'Tasks run autonomously without interruption. The AI handles planning, coding, and validation automatically.',
        'tasks:executionMode.semiAuto.title': 'Semi-Auto',
        'tasks:executionMode.semiAuto.description': 'Review and approve at key checkpoints.',
        'tasks:executionMode.semiAuto.checkpoints.planning': 'After planning - Review the implementation plan',
        'tasks:executionMode.semiAuto.checkpoints.coding': 'After coding - Review the implemented code',
        'tasks:executionMode.semiAuto.checkpoints.validation': 'After validation - Review QA results'
      };
      return translations[key] || key;
    }
  })
}));

describe('ExecutionModeTabs', () => {
  it('renders both Full Auto and Semi-Auto tabs', () => {
    const onChange = vi.fn();
    render(<ExecutionModeTabs value="full_auto" onChange={onChange} />);

    expect(screen.getByRole('tab', { name: /full auto/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /semi-auto/i })).toBeInTheDocument();
  });

  it('defaults to Full Auto tab selected', () => {
    const onChange = vi.fn();
    render(<ExecutionModeTabs value="full_auto" onChange={onChange} />);

    const fullAutoTab = screen.getByRole('tab', { name: /full auto/i });
    expect(fullAutoTab).toHaveAttribute('data-state', 'active');
  });

  it('shows Full Auto description when Full Auto is selected', () => {
    const onChange = vi.fn();
    render(<ExecutionModeTabs value="full_auto" onChange={onChange} />);

    expect(screen.getByText(/tasks run autonomously/i)).toBeInTheDocument();
  });

  it('calls onChange when Semi-Auto tab is selected via keyboard', () => {
    const onChange = vi.fn();
    render(<ExecutionModeTabs value="full_auto" onChange={onChange} />);

    const semiAutoTab = screen.getByRole('tab', { name: /semi-auto/i });
    // Focus the tab first, then trigger keyboard event (Radix pattern)
    semiAutoTab.focus();
    expect(semiAutoTab).toHaveFocus();
    fireEvent.keyDown(semiAutoTab, { key: 'Enter' });

    expect(onChange).toHaveBeenCalledWith('semi_auto');
  });

  it('tabs are clickable and not disabled by default', () => {
    const onChange = vi.fn();
    render(<ExecutionModeTabs value="full_auto" onChange={onChange} />);

    const semiAutoTab = screen.getByRole('tab', { name: /semi-auto/i });
    const fullAutoTab = screen.getByRole('tab', { name: /full auto/i });

    // Verify tabs are not disabled and are interactive
    expect(semiAutoTab).not.toBeDisabled();
    expect(fullAutoTab).not.toBeDisabled();
    expect(semiAutoTab).toHaveAttribute('data-state', 'inactive');
    expect(fullAutoTab).toHaveAttribute('data-state', 'active');
  });

  it('shows Semi-Auto description with checkpoints when Semi-Auto is selected', () => {
    const onChange = vi.fn();
    render(<ExecutionModeTabs value="semi_auto" onChange={onChange} />);

    expect(screen.getByText(/review and approve at key checkpoints/i)).toBeInTheDocument();
    expect(screen.getByText(/after planning/i)).toBeInTheDocument();
    expect(screen.getByText(/after coding/i)).toBeInTheDocument();
    expect(screen.getByText(/after validation/i)).toBeInTheDocument();
  });

  it('updates form state when tab changes', () => {
    const onChange = vi.fn();
    const { rerender } = render(<ExecutionModeTabs value="full_auto" onChange={onChange} />);

    // Initially Full Auto is selected
    expect(screen.getByRole('tab', { name: /full auto/i })).toHaveAttribute('data-state', 'active');

    // Simulate parent state update
    rerender(<ExecutionModeTabs value="semi_auto" onChange={onChange} />);

    // Now Semi-Auto should be active
    expect(screen.getByRole('tab', { name: /semi-auto/i })).toHaveAttribute('data-state', 'active');
  });

  it('respects disabled state', () => {
    const onChange = vi.fn();
    render(<ExecutionModeTabs value="full_auto" onChange={onChange} disabled />);

    const fullAutoTab = screen.getByRole('tab', { name: /full auto/i });
    const semiAutoTab = screen.getByRole('tab', { name: /semi-auto/i });

    expect(fullAutoTab).toBeDisabled();
    expect(semiAutoTab).toBeDisabled();
  });
});
