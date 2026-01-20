import { create } from 'zustand';
import type { ProjectEnvConfig } from '../../shared/types';

interface ProjectEnvState {
  // State
  envConfig: ProjectEnvConfig | null;
  projectId: string | null;
  isLoading: boolean;
  error: string | null;

  // Actions
  setEnvConfig: (projectId: string | null, config: ProjectEnvConfig | null) => void;
  updateEnvConfig: (updates: Partial<ProjectEnvConfig>) => void;
  clearEnvConfig: () => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  // Selectors
  isGitHubEnabled: () => boolean;
  isGitLabEnabled: () => boolean;
  isLinearEnabled: () => boolean;
  getGitHubRepo: () => string | null;
}

export const useProjectEnvStore = create<ProjectEnvState>((set, get) => ({
  // Initial state
  envConfig: null,
  projectId: null,
  isLoading: false,
  error: null,

  // Actions
  setEnvConfig: (projectId, envConfig) => set({
    projectId,
    envConfig,
    error: null
  }),

  updateEnvConfig: (updates) =>
    set((state) => ({
      envConfig: state.envConfig
        ? { ...state.envConfig, ...updates }
        : null
    })),

  clearEnvConfig: () => set({
    envConfig: null,
    projectId: null,
    error: null
  }),

  setLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),

  // Selectors
  isGitHubEnabled: () => {
    const { envConfig } = get();
    return envConfig?.githubEnabled ?? false;
  },

  isGitLabEnabled: () => {
    const { envConfig } = get();
    return envConfig?.gitlabEnabled ?? false;
  },

  isLinearEnabled: () => {
    const { envConfig } = get();
    return envConfig?.linearEnabled ?? false;
  },

  getGitHubRepo: () => {
    const { envConfig } = get();
    return envConfig?.githubRepo ?? null;
  }
}));

/**
 * Load project environment config from main process.
 * Updates the store with the loaded config.
 */
export async function loadProjectEnvConfig(projectId: string): Promise<ProjectEnvConfig | null> {
  const store = useProjectEnvStore.getState();
  store.setLoading(true);
  store.setError(null);

  try {
    const result = await window.electronAPI.getProjectEnv(projectId);
    if (result.success && result.data) {
      store.setEnvConfig(projectId, result.data);
      return result.data;
    } else {
      store.setError(result.error || 'Failed to load environment config');
      store.setEnvConfig(projectId, null);
      return null;
    }
  } catch (error) {
    store.setError(error instanceof Error ? error.message : 'Unknown error');
    store.setEnvConfig(projectId, null);
    return null;
  } finally {
    store.setLoading(false);
  }
}

/**
 * Set project env config directly (for use by useProjectSettings hook).
 * This is a standalone function for use outside React components.
 */
export function setProjectEnvConfig(projectId: string, config: ProjectEnvConfig | null): void {
  const store = useProjectEnvStore.getState();
  store.setEnvConfig(projectId, config);
}

/**
 * Clear the project env config (for use when switching projects or closing dialogs).
 * This is a standalone function for use outside React components.
 */
export function clearProjectEnvConfig(): void {
  const store = useProjectEnvStore.getState();
  store.clearEnvConfig();
}
