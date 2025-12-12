# Auto-Claude Recovery and Resumption System

## Overview

This document explains how Auto-Claude detects completed planning phases, identifies existing worktrees, and resumes execution after crashes or user interruptions.

## Key State Detection Mechanisms

### 1. Planning Phase Completion Detection

**Primary Indicator: `implementation_plan.json`**

The system determines if planning is complete by checking for the existence and validity of `implementation_plan.json`:

- **Location**: `.auto-claude/specs/{spec-name}/implementation_plan.json`
- **Detection Logic**: 
  - `prompts.py::is_first_run()` checks if `implementation_plan.json` exists
  - `coordinator.py::load_implementation_plan()` raises `FileNotFoundError` if missing
  - `agent.py::load_implementation_plan()` returns `None` if file doesn't exist

**Code References:**
```python
# auto-claude/prompts.py:181-192
def is_first_run(spec_dir: Path) -> bool:
    plan_file = spec_dir / "implementation_plan.json"
    return not plan_file.exists()

# auto-claude/coordinator.py:175-186
def load_implementation_plan(self) -> ImplementationPlan:
    plan_file = self.spec_dir / "implementation_plan.json"
    if not plan_file.exists():
        raise FileNotFoundError("Implementation plan not found")
    # ...
```

**Planning Phase Flow:**
1. `spec_runner.py` runs phases: discovery → requirements → complexity → context → spec → planning
2. `phase_planning()` creates `implementation_plan.json` via `planner.py` or planner agent
3. Once `implementation_plan.json` exists and is valid, planning is considered complete

### 2. Worktree Detection

**Staging Worktree Detection**

The system checks for existing worktrees using:

- **Location**: `.worktrees/auto-claude/` (staging worktree)
- **Detection Functions**:
  - `workspace.py::get_existing_build_worktree()` - checks if staging worktree exists
  - `worktree.py::get_or_create_staging()` - gets existing or creates new staging worktree
  - `worktree.py::staging_exists()` - boolean check for staging worktree

**Code References:**
```python
# auto-claude/workspace.py:88-93
def get_existing_build_worktree(project_dir: Path, spec_name: str) -> Optional[Path]:
    worktree_path = project_dir / ".worktrees" / STAGING_WORKTREE_NAME
    if worktree_path.exists():
        return worktree_path
    return None

# auto-claude/worktree.py:173-206
def get_or_create_staging(self, spec_name: str) -> WorktreeInfo:
    staging_path = self.worktrees_dir / STAGING_WORKTREE_NAME
    branch_name = f"auto-claude/{spec_name}"
    
    if staging_path.exists():
        # Load existing worktree info
        # ...
        return info
    # Create new staging worktree
    return self.create(STAGING_WORKTREE_NAME, branch_name)
```

**Worktree Persistence:**
- Worktrees persist across crashes and app restarts
- Git worktrees are stored in `.worktrees/` directory
- Each worktree has its own branch: `auto-claude/{spec-name}`
- Staging worktree is preserved until explicitly merged or discarded

### 3. Resumption Logic

**Entry Point: `run.py::main()`**

When `run.py` starts, it follows this resumption flow:

1. **Find Spec**: Locates spec directory via `find_spec()`
2. **Check Existing Build**: Calls `get_existing_build_worktree()` to detect staging worktree
3. **User Choice** (if not `--auto-continue`):
   - Continue where it left off
   - Review what was built
   - Merge existing build
   - Start fresh (discard)
4. **Workspace Setup**: 
   - If existing worktree found → uses it
   - If not → creates new staging worktree
5. **Execution**:
   - **Sequential Mode**: `run_autonomous_agent()` checks for `implementation_plan.json`
   - **Parallel Mode**: `SwarmCoordinator` checks for plan, runs planner if missing

**Code Flow:**
```python
# auto-claude/run.py:618-631
if get_existing_build_worktree(project_dir, spec_dir.name):
    if args.auto_continue:
        print("Auto-continue: Resuming existing build...")
    else:
        continue_existing = check_existing_build(project_dir, spec_dir.name)
        if continue_existing:
            # Continue with existing worktree
            pass
        else:
            # User chose to start fresh or merged existing
            pass
```

### 4. Planner vs Coder Detection

**Sequential Mode (`agent.py`):**

```python
# auto-claude/agent.py:547-691
async def run_autonomous_agent(...):
    # ...
    first_run = is_first_run(spec_dir)  # Checks for implementation_plan.json
    
    if first_run:
        # Run planner session
        prompt = generate_planner_prompt(spec_dir)
    else:
        # Run coder session
        next_chunk = get_next_chunk(spec_dir)
        prompt = generate_coder_prompt(spec_dir, next_chunk)
```

**Parallel Mode (`coordinator.py`):**

```python
# auto-claude/coordinator.py:304-350
async def run_planner_session(self) -> bool:
    """Run planner if implementation_plan.json doesn't exist"""
    plan_file = self.spec_dir / "implementation_plan.json"
    if not plan_file.exists():
        # Run planner agent session
        # ...
```

### 5. Chunk Progress Tracking

**State Storage: `implementation_plan.json`**

Chunk statuses are stored in the plan file:
- `pending` - Not started
- `in_progress` - Currently being worked on
- `completed` - Finished successfully
- `blocked` - Stuck, needs attention
- `failed` - Failed after attempts

**Resumption Logic:**
```python
# auto-claude/progress.py:399-452
def get_next_chunk(spec_dir: Path) -> dict | None:
    plan_file = spec_dir / "implementation_plan.json"
    # ...
    # Find first pending chunk in available phase
    for chunk in phase.get("chunks", []):
        if chunk.get("status") == "pending":
            return chunk
```

**Recovery Handling:**
- `in_progress` chunks are reset to `pending` on recovery (see `ipc-handlers.ts:926`)
- Completed chunks remain `completed` to preserve progress
- Failed chunks can be reset to `pending` for retry

## Recovery Scenarios

### Scenario 1: Planning Complete, No Worktree

**State:**
- ✅ `implementation_plan.json` exists
- ❌ No staging worktree exists

**Behavior:**
- System detects plan exists → skips planner
- Creates new staging worktree
- Starts coding phase with first pending chunk

### Scenario 2: Planning Complete, Worktree Exists

**State:**
- ✅ `implementation_plan.json` exists
- ✅ Staging worktree exists at `.worktrees/auto-claude/`

**Behavior:**
- System detects both exist
- Prompts user (or auto-continues) to resume
- Uses existing worktree
- Resumes from last incomplete chunk

### Scenario 3: Planning Incomplete

**State:**
- ❌ `implementation_plan.json` missing or invalid
- ❌ No staging worktree (or exists but no plan)

**Behavior:**
- System detects missing plan
- Runs planner session first
- Creates `implementation_plan.json`
- Then proceeds to coding phase

### Scenario 4: Crash During Coding

**State:**
- ✅ `implementation_plan.json` exists
- ✅ Staging worktree exists
- ⚠️ Some chunks `in_progress` or `failed`

**Behavior:**
- On restart, `in_progress` chunks are reset to `pending`
- System resumes from first `pending` chunk
- Worktree preserves all committed work
- Uncommitted changes may be lost (depends on git state)

## Frontend Integration

**UI State Detection (`auto-claude-ui`):**

The frontend tracks state via:
1. **File Watcher**: Monitors `implementation_plan.json` for changes
2. **Task Store**: Reads plan file to determine task status
3. **Agent Manager**: Parses logs to detect phase transitions

**Recovery Actions:**
- `ipc-handlers.ts::recoverTask()` - Resets stuck tasks
- Resets `in_progress` → `pending` for interrupted chunks
- Preserves `completed` chunks

## Key Files for State

**State Files:**
- `.auto-claude/specs/{spec}/implementation_plan.json` - Main state file
- `.auto-claude/specs/{spec}/memory/attempt_history.json` - Recovery history
- `.auto-claude/specs/{spec}/memory/build_commits.json` - Git commit tracking
- `.worktrees/auto-claude/` - Staging worktree (git-managed)

**Detection Functions:**
- `is_first_run()` - Checks if planning needed
- `get_existing_build_worktree()` - Checks for worktree
- `get_next_chunk()` - Finds next work item
- `load_implementation_plan()` - Loads plan state

## Summary

The system uses a **file-based state detection** approach:

1. **Planning Complete?** → Check for `implementation_plan.json`
2. **Worktree Exists?** → Check for `.worktrees/auto-claude/`
3. **What's Next?** → Read chunk statuses from `implementation_plan.json`
4. **Resume Point** → First `pending` chunk in available phase

This design ensures:
- ✅ No duplicate planning if plan already exists
- ✅ Work preservation via git worktrees
- ✅ Progress tracking via chunk statuses
- ✅ Safe resumption after crashes
- ✅ User control over continuation vs fresh start
