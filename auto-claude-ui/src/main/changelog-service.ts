import { EventEmitter } from 'events';
import path from 'path';
import { existsSync, readFileSync, writeFileSync } from 'fs';
import { spawn } from 'child_process';
import { app } from 'electron';
import { AUTO_BUILD_PATHS, DEFAULT_CHANGELOG_PATH } from '../shared/constants';
import type {
  ChangelogTask,
  TaskSpecContent,
  ChangelogGenerationRequest,
  ChangelogGenerationResult,
  ChangelogSaveRequest,
  ChangelogSaveResult,
  ChangelogGenerationProgress,
  ExistingChangelog,
  Task,
  ImplementationPlan
} from '../shared/types';

/**
 * Service for generating changelogs from completed tasks
 */
export class ChangelogService extends EventEmitter {
  private pythonPath: string = 'python3';
  private autoBuildSourcePath: string = '';
  private generationProcesses: Map<string, ReturnType<typeof spawn>> = new Map();

  constructor() {
    super();
  }

  /**
   * Configure paths for Python and auto-claude source
   */
  configure(pythonPath?: string, autoBuildSourcePath?: string): void {
    if (pythonPath) {
      this.pythonPath = pythonPath;
    }
    if (autoBuildSourcePath) {
      this.autoBuildSourcePath = autoBuildSourcePath;
    }
  }

  /**
   * Get the auto-claude source path (detects automatically if not configured)
   */
  private getAutoBuildSourcePath(): string | null {
    if (this.autoBuildSourcePath && existsSync(this.autoBuildSourcePath)) {
      return this.autoBuildSourcePath;
    }

    const possiblePaths = [
      path.resolve(__dirname, '..', '..', '..', 'auto-claude'),
      path.resolve(app.getAppPath(), '..', 'auto-claude'),
      path.resolve(process.cwd(), 'auto-claude')
    ];

    for (const p of possiblePaths) {
      if (existsSync(p) && existsSync(path.join(p, 'VERSION'))) {
        return p;
      }
    }
    return null;
  }

  /**
   * Load environment variables from auto-claude .env file
   */
  private loadAutoBuildEnv(): Record<string, string> {
    const autoBuildSource = this.getAutoBuildSourcePath();
    if (!autoBuildSource) return {};

    const envPath = path.join(autoBuildSource, '.env');
    if (!existsSync(envPath)) return {};

    try {
      const envContent = readFileSync(envPath, 'utf-8');
      const envVars: Record<string, string> = {};

      for (const line of envContent.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;

        const eqIndex = trimmed.indexOf('=');
        if (eqIndex > 0) {
          const key = trimmed.substring(0, eqIndex).trim();
          let value = trimmed.substring(eqIndex + 1).trim();

          if ((value.startsWith('"') && value.endsWith('"')) ||
              (value.startsWith("'") && value.endsWith("'"))) {
            value = value.slice(1, -1);
          }

          envVars[key] = value;
        }
      }

      return envVars;
    } catch {
      return {};
    }
  }

  /**
   * Get completed tasks from a project
   * @param projectPath - Project root path
   * @param tasks - List of tasks
   * @param specsBaseDir - Base specs directory (e.g., 'auto-claude/specs' or 'dev/auto-claude/specs')
   */
  getCompletedTasks(projectPath: string, tasks: Task[], specsBaseDir?: string): ChangelogTask[] {
    const specsDir = path.join(projectPath, specsBaseDir || AUTO_BUILD_PATHS.SPECS_DIR);

    return tasks
      .filter(task => task.status === 'done')
      .map(task => {
        const specDir = path.join(specsDir, task.specId);
        const hasSpecs = existsSync(specDir) && existsSync(path.join(specDir, AUTO_BUILD_PATHS.SPEC_FILE));

        return {
          id: task.id,
          specId: task.specId,
          title: task.title,
          description: task.description,
          completedAt: task.updatedAt,
          hasSpecs
        };
      })
      .sort((a, b) => new Date(b.completedAt).getTime() - new Date(a.completedAt).getTime());
  }

  /**
   * Load spec files for given tasks
   * @param projectPath - Project root path
   * @param taskIds - IDs of tasks to load specs for
   * @param tasks - List of all tasks
   * @param specsBaseDir - Base specs directory (e.g., 'auto-claude/specs' or 'dev/auto-claude/specs')
   */
  async loadTaskSpecs(projectPath: string, taskIds: string[], tasks: Task[], specsBaseDir?: string): Promise<TaskSpecContent[]> {
    const specsDir = path.join(projectPath, specsBaseDir || AUTO_BUILD_PATHS.SPECS_DIR);
    const results: TaskSpecContent[] = [];

    for (const taskId of taskIds) {
      const task = tasks.find(t => t.id === taskId);
      if (!task) continue;

      const specDir = path.join(specsDir, task.specId);
      const content: TaskSpecContent = {
        taskId,
        specId: task.specId
      };

      try {
        // Load spec.md
        const specPath = path.join(specDir, AUTO_BUILD_PATHS.SPEC_FILE);
        if (existsSync(specPath)) {
          content.spec = readFileSync(specPath, 'utf-8');
        }

        // Load requirements.json
        const requirementsPath = path.join(specDir, AUTO_BUILD_PATHS.REQUIREMENTS);
        if (existsSync(requirementsPath)) {
          content.requirements = JSON.parse(readFileSync(requirementsPath, 'utf-8'));
        }

        // Load qa_report.md
        const qaReportPath = path.join(specDir, AUTO_BUILD_PATHS.QA_REPORT);
        if (existsSync(qaReportPath)) {
          content.qaReport = readFileSync(qaReportPath, 'utf-8');
        }

        // Load implementation_plan.json
        const planPath = path.join(specDir, AUTO_BUILD_PATHS.IMPLEMENTATION_PLAN);
        if (existsSync(planPath)) {
          content.implementationPlan = JSON.parse(readFileSync(planPath, 'utf-8')) as ImplementationPlan;
        }
      } catch (error) {
        content.error = error instanceof Error ? error.message : 'Failed to load spec files';
      }

      results.push(content);
    }

    return results;
  }

  /**
   * Generate changelog using Claude AI
   */
  generateChangelog(
    projectId: string,
    projectPath: string,
    request: ChangelogGenerationRequest,
    specs: TaskSpecContent[]
  ): void {
    // Kill existing process if any
    this.cancelGeneration(projectId);

    // Emit initial progress
    this.emitProgress(projectId, {
      stage: 'loading_specs',
      progress: 10,
      message: 'Preparing changelog generation...'
    });

    // Build the prompt for Claude
    const prompt = this.buildChangelogPrompt(request, specs);

    // Use Claude Code SDK via subprocess
    const autoBuildSource = this.getAutoBuildSourcePath();
    if (!autoBuildSource) {
      this.emitError(projectId, 'Auto-build source path not found');
      return;
    }

    // Create a temporary Python script to call Claude
    const script = this.createGenerationScript(prompt, request);

    this.emitProgress(projectId, {
      stage: 'generating',
      progress: 30,
      message: 'Generating changelog with Claude AI...'
    });

    const autoBuildEnv = this.loadAutoBuildEnv();

    const childProcess = spawn(this.pythonPath, ['-c', script], {
      cwd: autoBuildSource,
      env: {
        ...process.env,
        ...autoBuildEnv,
        PYTHONUNBUFFERED: '1'
      }
    });

    this.generationProcesses.set(projectId, childProcess);

    let output = '';
    let errorOutput = '';

    childProcess.stdout?.on('data', (data: Buffer) => {
      output += data.toString();

      this.emitProgress(projectId, {
        stage: 'generating',
        progress: 50,
        message: 'Generating changelog content...'
      });
    });

    childProcess.stderr?.on('data', (data: Buffer) => {
      errorOutput += data.toString();
    });

    childProcess.on('exit', (code: number | null) => {
      this.generationProcesses.delete(projectId);

      if (code === 0 && output.trim()) {
        this.emitProgress(projectId, {
          stage: 'formatting',
          progress: 90,
          message: 'Formatting changelog...'
        });

        // Extract changelog from output
        const changelog = this.extractChangelog(output.trim());

        this.emitProgress(projectId, {
          stage: 'complete',
          progress: 100,
          message: 'Changelog generation complete'
        });

        const result: ChangelogGenerationResult = {
          success: true,
          changelog,
          version: request.version,
          tasksIncluded: request.taskIds.length
        };

        this.emit('generation-complete', projectId, result);
      } else {
        const error = errorOutput || `Generation failed with exit code ${code}`;
        this.emitError(projectId, error);
      }
    });

    childProcess.on('error', (err: Error) => {
      this.generationProcesses.delete(projectId);
      this.emitError(projectId, err.message);
    });
  }

  /**
   * Build the prompt for changelog generation
   */
  private buildChangelogPrompt(
    request: ChangelogGenerationRequest,
    specs: TaskSpecContent[]
  ): string {
    const audienceInstructions = {
      'technical': `You are a technical documentation specialist creating a changelog for software developers.
Use precise technical language. Include API changes, architecture details, affected modules.
Note any breaking changes explicitly. Include migration steps if needed.`,
      'user-facing': `You are a product manager writing release notes for end users who may not be technical.
Use clear, non-technical language. Focus on user benefits and value.
Explain "what" changed, not "how". Use active voice and positive framing.`,
      'marketing': `You are a marketing specialist writing release notes that emphasize value and benefits.
Focus on outcomes and user impact. Use compelling language that highlights improvements.
Emphasize competitive advantages and user success stories.`
    };

    const formatInstructions = {
      'keep-a-changelog': `Use Keep-a-Changelog format with these sections:
## [${request.version}] - ${request.date}

### Added
- [New features]

### Changed
- [Modifications]

### Fixed
- [Bug fixes]

### Removed
- [Deprecations/removals]`,
      'simple-list': `Use a simple, clean format:
# Release v${request.version} (${request.date})

**New Features:**
- [List features]

**Improvements:**
- [List improvements]

**Bug Fixes:**
- [List fixes]`,
      'github-release': `Use GitHub Release format with emojis:
## 🎉 What's New in v${request.version}

### ✨ New Features
- 🚀 **Feature Name**: Description

### 🔧 Improvements
- ⚡ **Improvement**: Description

### 🐛 Bug Fixes
- Fixed [issue description]`
    };

    // Build task context
    const taskContext = specs.map(spec => {
      let context = `## Task: ${spec.specId}\n`;

      if (spec.spec) {
        // Extract key parts from spec.md
        context += `### Specification:\n${spec.spec.substring(0, 2000)}...\n\n`;
      }

      if (spec.qaReport) {
        context += `### QA Validation:\n${spec.qaReport.substring(0, 500)}...\n\n`;
      }

      if (spec.implementationPlan) {
        context += `### Implementation: ${spec.implementationPlan.feature}\n`;
        context += `Type: ${spec.implementationPlan.workflow_type}\n`;
      }

      return context;
    }).join('\n---\n');

    return `${audienceInstructions[request.audience]}

Generate a changelog entry in the following format:
${formatInstructions[request.format]}

CONTEXT - The following tasks have been completed:
${taskContext}

${request.customInstructions ? `ADDITIONAL INSTRUCTIONS: ${request.customInstructions}` : ''}

Generate only the changelog content. Be comprehensive but concise. Do not include any explanation or preamble - just the formatted changelog.`;
  }

  /**
   * Create Python script for Claude generation
   */
  private createGenerationScript(prompt: string, _request: ChangelogGenerationRequest): string {
    // Escape the prompt for Python string
    const escapedPrompt = prompt
      .replace(/\\/g, '\\\\')
      .replace(/"/g, '\\"')
      .replace(/\n/g, '\\n');

    return `
import subprocess
import sys

prompt = """${escapedPrompt}"""

# Use Claude Code CLI to generate
result = subprocess.run(
    ['claude', '-p', prompt, '--output-format', 'text'],
    capture_output=True,
    text=True,
    timeout=120
)

if result.returncode == 0:
    print(result.stdout)
else:
    print(result.stderr, file=sys.stderr)
    sys.exit(1)
`;
  }

  /**
   * Extract changelog content from Claude output
   */
  private extractChangelog(output: string): string {
    // Claude output should be the changelog directly
    // Clean up any potential wrapper text
    let changelog = output.trim();

    // Remove any "Here's the changelog:" or similar prefixes
    const prefixes = [
      /^Here['']s the changelog[:\s]*/i,
      /^The changelog[:\s]*/i,
      /^Changelog[:\s]*/i
    ];

    for (const prefix of prefixes) {
      changelog = changelog.replace(prefix, '');
    }

    return changelog.trim();
  }

  /**
   * Save changelog to file
   */
  saveChangelog(
    projectPath: string,
    request: ChangelogSaveRequest
  ): ChangelogSaveResult {
    const filePath = request.filePath
      ? path.join(projectPath, request.filePath)
      : path.join(projectPath, DEFAULT_CHANGELOG_PATH);

    let finalContent = request.content;

    if (request.mode === 'prepend' && existsSync(filePath)) {
      const existing = readFileSync(filePath, 'utf-8');
      // Add separator between new and existing content
      finalContent = `${request.content}\n\n${existing}`;
    } else if (request.mode === 'append' && existsSync(filePath)) {
      const existing = readFileSync(filePath, 'utf-8');
      finalContent = `${existing}\n\n${request.content}`;
    }

    writeFileSync(filePath, finalContent, 'utf-8');

    return {
      filePath,
      bytesWritten: Buffer.byteLength(finalContent, 'utf-8')
    };
  }

  /**
   * Read existing changelog file
   */
  readExistingChangelog(projectPath: string): ExistingChangelog {
    const filePath = path.join(projectPath, DEFAULT_CHANGELOG_PATH);

    if (!existsSync(filePath)) {
      return { exists: false };
    }

    try {
      const content = readFileSync(filePath, 'utf-8');

      // Try to extract last version using common patterns
      const versionPatterns = [
        /##\s*\[(\d+\.\d+\.\d+)\]/,  // Keep-a-changelog format
        /v(\d+\.\d+\.\d+)/,           // v1.2.3 format
        /Version\s+(\d+\.\d+\.\d+)/i  // Version 1.2.3 format
      ];

      let lastVersion: string | undefined;
      for (const pattern of versionPatterns) {
        const match = content.match(pattern);
        if (match) {
          lastVersion = match[1];
          break;
        }
      }

      return {
        exists: true,
        content,
        lastVersion
      };
    } catch (error) {
      return {
        exists: true,
        error: error instanceof Error ? error.message : 'Failed to read changelog'
      };
    }
  }

  /**
   * Suggest next version based on task types
   */
  suggestVersion(specs: TaskSpecContent[], currentVersion?: string): string {
    // Default starting version
    if (!currentVersion) {
      return '1.0.0';
    }

    const parts = currentVersion.split('.').map(Number);
    if (parts.length !== 3 || parts.some(isNaN)) {
      return '1.0.0';
    }

    let [major, minor, patch] = parts;

    // Analyze specs for version increment decision
    let hasBreakingChanges = false;
    let hasNewFeatures = false;

    for (const spec of specs) {
      const content = (spec.spec || '').toLowerCase();

      if (content.includes('breaking change') || content.includes('breaking:')) {
        hasBreakingChanges = true;
      }

      if (spec.implementationPlan?.workflow_type === 'new_feature' ||
          content.includes('new feature') ||
          content.includes('## added')) {
        hasNewFeatures = true;
      }
    }

    if (hasBreakingChanges) {
      return `${major + 1}.0.0`;
    } else if (hasNewFeatures) {
      return `${major}.${minor + 1}.0`;
    } else {
      return `${major}.${minor}.${patch + 1}`;
    }
  }

  /**
   * Cancel ongoing generation
   */
  cancelGeneration(projectId: string): boolean {
    const process = this.generationProcesses.get(projectId);
    if (process) {
      process.kill('SIGTERM');
      this.generationProcesses.delete(projectId);
      return true;
    }
    return false;
  }

  /**
   * Emit progress update
   */
  private emitProgress(projectId: string, progress: ChangelogGenerationProgress): void {
    this.emit('generation-progress', projectId, progress);
  }

  /**
   * Emit error
   */
  private emitError(projectId: string, error: string): void {
    this.emit('generation-progress', projectId, {
      stage: 'error',
      progress: 0,
      message: error,
      error
    });
    this.emit('generation-error', projectId, error);
  }
}

// Export singleton instance
export const changelogService = new ChangelogService();
