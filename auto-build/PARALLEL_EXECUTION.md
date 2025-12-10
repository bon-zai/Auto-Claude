# Parallel Execution with Git Worktrees

Auto-Build supports parallel execution of independent chunks using Git worktrees for complete worker isolation.

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SwarmCoordinator                              │
│  - Runs planner session first (if needed)                       │
│  - Manages worker pool                                          │
│  - Assigns chunks respecting dependencies                       │
│  - Serializes merges back to base branch                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    WorktreeManager                               │
│  - Creates .worktrees/ directory                                │
│  - Each worker gets its own worktree + branch                   │
│  - Handles cleanup and merge operations                         │
└─────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│    Worker 1     │  │    Worker 2     │  │    Worker 3     │
│ .worktrees/     │  │ .worktrees/     │  │ .worktrees/     │
│   worker-1/     │  │   worker-2/     │  │   worker-3/     │
│ Branch:         │  │ Branch:         │  │ Branch:         │
│ worker-1/chunk  │  │ worker-2/chunk  │  │ worker-3/chunk  │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
                    Sequential Merges
                    (with asyncio.Lock)
```

### Git Worktrees

Each worker operates in a completely isolated environment:

1. **Separate working directory**: `.worktrees/worker-N/`
2. **Unique branch**: `worker-N/chunk-id`
3. **Independent git index**: No race conditions on `git add`/`git commit`

This is the gold standard for parallel git operations and eliminates all race conditions.

## Usage

```bash
# Run with 2 parallel workers
python auto-build/run.py --spec 001 --parallel 2

# Run with 3 parallel workers
python auto-build/run.py --spec 001 --parallel 3
```

## Execution Flow

### 1. Planner Phase (Sequential)

If `implementation_plan.json` doesn't exist, the coordinator runs a planner session first:

```
======================================================================
  PLANNER SESSION
  Creating implementation plan from spec...
======================================================================
```

The planner:
- Reads your spec.md
- Analyzes the codebase structure
- Creates chunk-based implementation_plan.json
- Initializes Linear integration (if enabled)

### 2. Parallel Phase

Once the plan exists, parallel workers start:

```
======================================================================
  PARALLEL EXECUTION MODE
  Max Workers: 2
  Using Git worktrees for isolation
======================================================================

Base branch: auto-build/feature-name
Worktrees directory: /path/to/project/.worktrees

Assigned chunk backend-models to worker 1
Assigned chunk frontend-components to worker 2

======================================================================
  WORKER 1: Starting backend-models
  Phase: Backend Implementation
  Description: Add database models for new feature
======================================================================

Created worktree: worker-1 on branch worker-1/backend-models
Worker 1: Running in worktree worker-1...
```

### 3. Merge Phase (Serialized)

As workers complete, their branches are merged sequentially:

```
Worker 1: Merging worker-1/backend-models into auto-build/feature-name...
  Successfully merged worker-1/backend-models
Removed worktree: worker-1

Worker 1 completed: SUCCESS
```

## File Claiming

Even with worktrees, we prevent logical conflicts through file claiming:

- Before starting, each chunk's files are "claimed"
- No two workers can work on the same files simultaneously
- This prevents merge conflicts at the content level

## When to Use Parallel Mode

### Good candidates for parallelism:
- Independent chunks in different services (backend + frontend)
- Chunks that modify completely different files
- Multiple features that don't interact

### Sequential is better for:
- Chunks with dependencies (one must complete before another)
- Chunks modifying the same files
- Very small specs (overhead of worktrees not worth it)

## Performance

| Scenario | Sequential | Parallel (2) | Parallel (3) |
|----------|------------|--------------|--------------|
| 4 independent chunks | ~40 min | ~20 min | ~15 min |
| 2 independent + 2 dependent | ~40 min | ~30 min | ~30 min |
| All sequential dependencies | ~40 min | ~40 min | ~40 min |

Rule of thumb: **Parallelism helps when you have independent work**

## Troubleshooting

### Stale Worktrees

If a previous run crashed, you might see:
```
Pruning stale worktree: worker-1
Removing stale worktree directory: worker-2
```

This is automatic cleanup - worktrees from crashed runs are removed.

### Merge Conflicts

If a merge conflict occurs:
```
Worker 1: Merge conflict! Aborting merge...
Worker 1: Merge failed for chunk-id
```

The chunk will be marked as failed. You can:
1. Run again with `--parallel 1` to complete sequentially
2. Manually resolve and retry

### Worktree Creation Fails

```
Worker 1: Failed to create worktree: ...
```

Common causes:
- Branch name already exists (from previous attempt)
- Git version < 2.5 (worktrees require modern git)

Fix:
```bash
# Clean up stale branches
git branch -D worker-1/chunk-id

# Prune worktree list
git worktree prune
```

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Required for all modes |
| `AUTO_BUILD_MODEL` | Model override (default: claude-opus-4-5-20251101) |
| `LINEAR_API_KEY` | Optional: Enable Linear integration |

### Recommended Worker Count

| CPU Cores | Recommended Workers |
|-----------|---------------------|
| 2-4 | 2 |
| 4-8 | 2-3 |
| 8+ | 3 |

More workers doesn't always mean faster - each worker uses significant API resources.

## Cleanup

Worktrees are automatically cleaned up:
- After successful completion
- After failures
- At the end of the run (in the `finally` block)

The `.worktrees/` directory should be empty after a clean run. If not:

```bash
# Manual cleanup
git worktree prune
rm -rf .worktrees/
```

## Integration with Linear

When Linear integration is enabled:
1. Planner creates Linear project and issues
2. Each chunk maps to a Linear issue
3. Worker progress is tracked in Linear comments
4. Failed chunks can be escalated in Linear

This works identically in parallel mode - Linear updates are thread-safe.
