"""
Prompt Generator
================

Generates minimal, focused prompts for each chunk.
Instead of a 900-line mega-prompt, each chunk gets a tailored ~100-line prompt
with only the context it needs.

This approach:
- Reduces token usage by ~80%
- Keeps the agent focused on ONE task
- Moves bookkeeping to Python orchestration
"""

import json
from pathlib import Path
from typing import Optional

from linear_integration import (
    is_linear_enabled,
    prepare_planner_linear_instructions,
    prepare_coder_linear_instructions,
)


def generate_chunk_prompt(
    spec_dir: Path,
    project_dir: Path,
    chunk: dict,
    phase: dict,
    attempt_count: int = 0,
    recovery_hints: Optional[list[str]] = None,
) -> str:
    """
    Generate a minimal, focused prompt for implementing a single chunk.

    Args:
        spec_dir: Directory containing spec files
        project_dir: Root project directory
        chunk: The chunk to implement
        phase: The phase containing this chunk
        attempt_count: Number of previous attempts (for retry context)
        recovery_hints: Hints from previous failed attempts

    Returns:
        A focused prompt string (~100 lines instead of 900)
    """
    chunk_id = chunk.get("id", "unknown")
    description = chunk.get("description", "No description")
    service = chunk.get("service", "all")
    files_to_modify = chunk.get("files_to_modify", [])
    files_to_create = chunk.get("files_to_create", [])
    patterns_from = chunk.get("patterns_from", [])
    verification = chunk.get("verification", {})

    # Build the prompt
    sections = []

    # Header
    sections.append(f"""# Chunk Implementation Task

**Chunk ID:** `{chunk_id}`
**Phase:** {phase.get('name', phase.get('id', 'Unknown'))}
**Service:** {service}

## Description

{description}
""")

    # Recovery context if this is a retry
    if attempt_count > 0:
        sections.append(f"""
## ⚠️ RETRY ATTEMPT ({attempt_count + 1})

This chunk has been attempted {attempt_count} time(s) before without success.
You MUST use a DIFFERENT approach than previous attempts.
""")
        if recovery_hints:
            sections.append("**Previous attempt insights:**")
            for hint in recovery_hints:
                sections.append(f"- {hint}")
            sections.append("")

    # Files section
    sections.append("## Files\n")

    if files_to_modify:
        sections.append("**Files to Modify:**")
        for f in files_to_modify:
            sections.append(f"- `{f}`")
        sections.append("")

    if files_to_create:
        sections.append("**Files to Create:**")
        for f in files_to_create:
            sections.append(f"- `{f}`")
        sections.append("")

    if patterns_from:
        sections.append("**Pattern Files (study these first):**")
        for f in patterns_from:
            sections.append(f"- `{f}`")
        sections.append("")

    # Verification
    sections.append("## Verification\n")
    v_type = verification.get("type", "manual")

    if v_type == "command":
        sections.append(f"""Run this command to verify:
```bash
{verification.get('command', 'echo "No command specified"')}
```
Expected: {verification.get('expected', 'Success')}
""")
    elif v_type == "api":
        method = verification.get("method", "GET")
        url = verification.get("url", "http://localhost")
        body = verification.get("body", {})
        expected_status = verification.get("expected_status", 200)
        sections.append(f"""Test the API endpoint:
```bash
curl -X {method} {url} -H "Content-Type: application/json" {f'-d \'{json.dumps(body)}\'' if body else ''}
```
Expected status: {expected_status}
""")
    elif v_type == "browser":
        url = verification.get("url", "http://localhost:3000")
        checks = verification.get("checks", [])
        sections.append(f"""Open in browser: {url}

Verify:""")
        for check in checks:
            sections.append(f"- [ ] {check}")
        sections.append("")
    elif v_type == "e2e":
        steps = verification.get("steps", [])
        sections.append("End-to-end verification steps:")
        for i, step in enumerate(steps, 1):
            sections.append(f"{i}. {step}")
        sections.append("")
    else:
        instructions = verification.get("instructions", "Manual verification required")
        sections.append(f"**Manual Verification:**\n{instructions}\n")

    # Instructions
    sections.append("""## Instructions

1. **Read the pattern files** to understand code style and conventions
2. **Read the files to modify** (if any) to understand current implementation
3. **Implement the chunk** following the patterns exactly
4. **Run verification** and fix any issues
5. **Commit your changes:**
   ```bash
   git add .
   git commit -m "auto-build: {chunk_id} - {short_description}"
   ```
6. **Update the plan** - set this chunk's status to "completed" in implementation_plan.json

## Quality Checklist

Before marking complete, verify:
- [ ] Follows patterns from reference files
- [ ] No console.log/print debugging statements
- [ ] Error handling in place
- [ ] Verification passes
- [ ] Clean commit with descriptive message

## Important

- Focus ONLY on this chunk - don't modify unrelated code
- If verification fails, FIX IT before committing
- If you encounter a blocker, document it in build-progress.txt
""".format(chunk_id=chunk_id, short_description=description[:50]))

    # Add Linear instructions if enabled
    linear_instructions = prepare_coder_linear_instructions(spec_dir, chunk_id)
    if linear_instructions:
        sections.append(linear_instructions)

    return "\n".join(sections)


def generate_planner_prompt(spec_dir: Path) -> str:
    """
    Generate the planner prompt (used only once at start).
    This is a simplified version that focuses on plan creation.

    Args:
        spec_dir: Directory containing spec.md

    Returns:
        Planner prompt string
    """
    # Load the full planner prompt from file
    prompts_dir = Path(__file__).parent / "prompts"
    planner_file = prompts_dir / "planner.md"

    if planner_file.exists():
        prompt = planner_file.read_text()
    else:
        prompt = "Read spec.md and create implementation_plan.json with phases and chunks."

    # Inject spec location
    header = f"""## SPEC LOCATION

Your spec file is located at: `{spec_dir}/spec.md`

Store all build artifacts in this spec directory:
- `{spec_dir}/implementation_plan.json` - Chunk-based implementation plan
- `{spec_dir}/build-progress.txt` - Progress notes
- `{spec_dir}/init.sh` - Environment setup script
- `{spec_dir}/.linear_project.json` - Linear integration state (if enabled)

The project root is the parent of auto-build/. Implement code in the project root, not in the spec directory.

---

"""
    # Add Linear integration instructions if enabled
    linear_instructions = prepare_planner_linear_instructions(spec_dir)
    if linear_instructions:
        header += linear_instructions + "\n\n---\n\n"

    return header + prompt


def load_chunk_context(
    spec_dir: Path,
    project_dir: Path,
    chunk: dict,
    max_file_lines: int = 200,
) -> dict:
    """
    Load minimal context needed for a chunk.

    Args:
        spec_dir: Spec directory
        project_dir: Project root
        chunk: The chunk being implemented
        max_file_lines: Maximum lines to include per file

    Returns:
        Dict with file contents and relevant context
    """
    context = {
        "patterns": {},
        "files_to_modify": {},
        "spec_excerpt": None,
    }

    # Load pattern files (truncated)
    for pattern_path in chunk.get("patterns_from", []):
        full_path = project_dir / pattern_path
        if full_path.exists():
            try:
                lines = full_path.read_text().split("\n")
                if len(lines) > max_file_lines:
                    content = "\n".join(lines[:max_file_lines])
                    content += f"\n\n... (truncated, {len(lines) - max_file_lines} more lines)"
                else:
                    content = "\n".join(lines)
                context["patterns"][pattern_path] = content
            except Exception:
                context["patterns"][pattern_path] = "(Could not read file)"

    # Load files to modify (truncated)
    for file_path in chunk.get("files_to_modify", []):
        full_path = project_dir / file_path
        if full_path.exists():
            try:
                lines = full_path.read_text().split("\n")
                if len(lines) > max_file_lines:
                    content = "\n".join(lines[:max_file_lines])
                    content += f"\n\n... (truncated, {len(lines) - max_file_lines} more lines)"
                else:
                    content = "\n".join(lines)
                context["files_to_modify"][file_path] = content
            except Exception:
                context["files_to_modify"][file_path] = "(Could not read file)"

    return context


def format_context_for_prompt(context: dict) -> str:
    """
    Format loaded context into a prompt section.

    Args:
        context: Dict from load_chunk_context

    Returns:
        Formatted string to append to prompt
    """
    sections = []

    if context.get("patterns"):
        sections.append("## Reference Files (Patterns to Follow)\n")
        for path, content in context["patterns"].items():
            sections.append(f"### `{path}`\n```\n{content}\n```\n")

    if context.get("files_to_modify"):
        sections.append("## Current File Contents (To Modify)\n")
        for path, content in context["files_to_modify"].items():
            sections.append(f"### `{path}`\n```\n{content}\n```\n")

    return "\n".join(sections)
