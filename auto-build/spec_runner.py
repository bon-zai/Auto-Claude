#!/usr/bin/env python3
"""
Spec Creation Orchestrator
==========================

Manages the spec creation process with checkpoints, validation, and agent invocations.
This is the enforcement layer that ensures reliable spec creation.

The process:
1. Discovery (script) → project_index.json
2. Requirements (agent) → requirements.json
3. Context (script) → context.json
4. Spec Writing (agent) → spec.md
5. Planning (script/agent) → implementation_plan.json
6. Validation (script) → ensure all outputs valid

Usage:
    python auto-build/spec_runner.py --task "Add user authentication"
    python auto-build/spec_runner.py --interactive
    python auto-build/spec_runner.py --continue 001-feature
"""

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add auto-build to path
sys.path.insert(0, str(Path(__file__).parent))

from client import create_client
from validate_spec import SpecValidator, auto_fix_plan


# Configuration
MAX_RETRIES = 3
PROMPTS_DIR = Path(__file__).parent / "prompts"
SPECS_DIR = Path(__file__).parent / "specs"


@dataclass
class PhaseResult:
    """Result of a phase execution."""
    phase: str
    success: bool
    output_files: list[str]
    errors: list[str]
    retries: int


class SpecOrchestrator:
    """Orchestrates the spec creation process."""

    def __init__(
        self,
        project_dir: Path,
        task_description: Optional[str] = None,
        spec_name: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        self.project_dir = Path(project_dir)
        self.task_description = task_description
        self.model = model

        # Create spec directory
        if spec_name:
            self.spec_dir = SPECS_DIR / spec_name
        else:
            self.spec_dir = self._create_spec_dir()

        self.spec_dir.mkdir(parents=True, exist_ok=True)
        self.validator = SpecValidator(self.spec_dir)

    def _create_spec_dir(self) -> Path:
        """Create a new spec directory with incremented number."""
        existing = list(SPECS_DIR.glob("[0-9][0-9][0-9]-*"))
        next_num = len(existing) + 1

        # Generate name from task description
        if self.task_description:
            # Convert to kebab-case
            name = self.task_description.lower()
            name = "".join(c if c.isalnum() or c == " " else "" for c in name)
            name = "-".join(name.split()[:4])  # First 4 words
        else:
            name = "new-spec"

        return SPECS_DIR / f"{next_num:03d}-{name}"

    def _run_script(self, script: str, args: list[str]) -> tuple[bool, str]:
        """Run a Python script and return (success, output)."""
        script_path = Path(__file__).parent / script

        if not script_path.exists():
            return False, f"Script not found: {script_path}"

        cmd = [sys.executable, str(script_path)] + args

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr or result.stdout

        except subprocess.TimeoutExpired:
            return False, "Script timed out"
        except Exception as e:
            return False, str(e)

    async def _run_agent(
        self,
        prompt_file: str,
        additional_context: str = "",
        interactive: bool = False,
    ) -> tuple[bool, str]:
        """Run an agent with the given prompt."""
        prompt_path = PROMPTS_DIR / prompt_file

        if not prompt_path.exists():
            return False, f"Prompt not found: {prompt_path}"

        # Load prompt
        prompt = prompt_path.read_text()

        # Add context
        prompt += f"\n\n---\n\n**Spec Directory**: {self.spec_dir}\n"
        prompt += f"**Project Directory**: {self.project_dir}\n"

        if additional_context:
            prompt += f"\n{additional_context}\n"

        # Create client
        client = create_client(self.project_dir, self.spec_dir, self.model)

        try:
            async with client:
                await client.query(prompt)

                response_text = ""
                async for msg in client.receive_response():
                    msg_type = type(msg).__name__

                    if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                        for block in msg.content:
                            block_type = type(block).__name__
                            if block_type == "TextBlock" and hasattr(block, "text"):
                                response_text += block.text
                                print(block.text, end="", flush=True)
                            elif block_type == "ToolUseBlock" and hasattr(block, "name"):
                                print(f"\n[Tool: {block.name}]", flush=True)

                print()
                return True, response_text

        except Exception as e:
            return False, str(e)

    # === Phase Implementations ===

    async def phase_discovery(self) -> PhaseResult:
        """Phase 1: Analyze project structure."""
        print("\n" + "=" * 60)
        print("  PHASE 1: PROJECT DISCOVERY")
        print("=" * 60)

        errors = []
        retries = 0

        for attempt in range(MAX_RETRIES):
            retries = attempt

            # Check if project_index already exists
            auto_build_index = Path(__file__).parent / "project_index.json"
            spec_index = self.spec_dir / "project_index.json"

            if auto_build_index.exists() and not spec_index.exists():
                # Copy existing index
                import shutil
                shutil.copy(auto_build_index, spec_index)
                print(f"✓ Copied existing project_index.json")
                return PhaseResult("discovery", True, [str(spec_index)], [], 0)

            if spec_index.exists():
                print(f"✓ project_index.json already exists")
                return PhaseResult("discovery", True, [str(spec_index)], [], 0)

            # Run analyzer
            print("Running project analyzer...")
            success, output = self._run_script(
                "analyzer.py",
                ["--output", str(spec_index)]
            )

            if success and spec_index.exists():
                print(f"✓ Created project_index.json")
                return PhaseResult("discovery", True, [str(spec_index)], [], retries)

            errors.append(f"Attempt {attempt + 1}: {output}")
            print(f"✗ Attempt {attempt + 1} failed: {output[:200]}")

        return PhaseResult("discovery", False, [], errors, retries)

    async def phase_requirements(self, interactive: bool = True) -> PhaseResult:
        """Phase 2: Gather requirements."""
        print("\n" + "=" * 60)
        print("  PHASE 2: REQUIREMENTS GATHERING")
        print("=" * 60)

        requirements_file = self.spec_dir / "requirements.json"

        # If we have a task description, create requirements directly
        if self.task_description and not interactive:
            requirements = {
                "task_description": self.task_description,
                "workflow_type": "feature",  # Default, agent will refine
                "services_involved": [],  # Agent will determine
                "created_at": datetime.now().isoformat(),
            }
            with open(requirements_file, "w") as f:
                json.dump(requirements, f, indent=2)
            print(f"✓ Created requirements.json from task description")
            return PhaseResult("requirements", True, [str(requirements_file)], [], 0)

        # Interactive mode - run agent
        errors = []
        for attempt in range(MAX_RETRIES):
            print(f"\nRunning requirements gatherer (attempt {attempt + 1})...")

            context = f"**Task**: {self.task_description or 'Ask user what they want to build'}\n"
            success, output = await self._run_agent(
                "spec_gatherer.md",
                additional_context=context,
                interactive=True,
            )

            if success and requirements_file.exists():
                print(f"✓ Created requirements.json")
                return PhaseResult("requirements", True, [str(requirements_file)], [], attempt)

            errors.append(f"Attempt {attempt + 1}: Agent did not create requirements.json")

        return PhaseResult("requirements", False, [], errors, MAX_RETRIES)

    async def phase_context(self) -> PhaseResult:
        """Phase 3: Discover relevant files."""
        print("\n" + "=" * 60)
        print("  PHASE 3: CONTEXT DISCOVERY")
        print("=" * 60)

        context_file = self.spec_dir / "context.json"
        requirements_file = self.spec_dir / "requirements.json"

        if context_file.exists():
            print(f"✓ context.json already exists")
            return PhaseResult("context", True, [str(context_file)], [], 0)

        # Load requirements for task description
        task = self.task_description
        services = ""

        if requirements_file.exists():
            with open(requirements_file) as f:
                req = json.load(f)
                task = req.get("task_description", task)
                services = ",".join(req.get("services_involved", []))

        errors = []
        for attempt in range(MAX_RETRIES):
            print(f"Running context discovery (attempt {attempt + 1})...")

            args = [
                "--task", task or "unknown task",
                "--output", str(context_file),
            ]
            if services:
                args.extend(["--services", services])

            success, output = self._run_script("context.py", args)

            if success and context_file.exists():
                print(f"✓ Created context.json")
                return PhaseResult("context", True, [str(context_file)], [], attempt)

            errors.append(f"Attempt {attempt + 1}: {output}")
            print(f"✗ Attempt {attempt + 1} failed")

        # Create minimal context if script fails
        minimal_context = {
            "task_description": task or "unknown task",
            "scoped_services": services.split(",") if services else [],
            "files_to_modify": [],
            "files_to_reference": [],
            "created_at": datetime.now().isoformat(),
        }
        with open(context_file, "w") as f:
            json.dump(minimal_context, f, indent=2)
        print("✓ Created minimal context.json (script failed)")
        return PhaseResult("context", True, [str(context_file)], errors, MAX_RETRIES)

    async def phase_spec_writing(self) -> PhaseResult:
        """Phase 4: Write spec.md document."""
        print("\n" + "=" * 60)
        print("  PHASE 4: SPEC DOCUMENT CREATION")
        print("=" * 60)

        spec_file = self.spec_dir / "spec.md"

        if spec_file.exists():
            # Validate existing spec
            result = self.validator.validate_spec_document()
            if result.valid:
                print(f"✓ spec.md already exists and is valid")
                return PhaseResult("spec_writing", True, [str(spec_file)], [], 0)
            print(f"⚠ spec.md exists but has issues, regenerating...")

        errors = []
        for attempt in range(MAX_RETRIES):
            print(f"\nRunning spec writer (attempt {attempt + 1})...")

            success, output = await self._run_agent("spec_writer.md")

            if success and spec_file.exists():
                # Validate
                result = self.validator.validate_spec_document()
                if result.valid:
                    print(f"✓ Created valid spec.md")
                    return PhaseResult("spec_writing", True, [str(spec_file)], [], attempt)
                else:
                    errors.append(f"Attempt {attempt + 1}: Spec invalid - {result.errors}")
                    print(f"✗ Spec created but invalid: {result.errors}")
            else:
                errors.append(f"Attempt {attempt + 1}: Agent did not create spec.md")

        return PhaseResult("spec_writing", False, [], errors, MAX_RETRIES)

    async def phase_planning(self) -> PhaseResult:
        """Phase 5: Create implementation plan."""
        print("\n" + "=" * 60)
        print("  PHASE 5: IMPLEMENTATION PLANNING")
        print("=" * 60)

        plan_file = self.spec_dir / "implementation_plan.json"

        if plan_file.exists():
            # Validate existing plan
            result = self.validator.validate_implementation_plan()
            if result.valid:
                print(f"✓ implementation_plan.json already exists and is valid")
                return PhaseResult("planning", True, [str(plan_file)], [], 0)
            print(f"⚠ Plan exists but invalid, regenerating...")

        errors = []

        # Try Python script first (deterministic)
        print("Trying planner.py (deterministic)...")
        success, output = self._run_script(
            "planner.py",
            ["--spec-dir", str(self.spec_dir)]
        )

        if success and plan_file.exists():
            # Validate
            result = self.validator.validate_implementation_plan()
            if result.valid:
                print(f"✓ Created valid implementation_plan.json via script")
                return PhaseResult("planning", True, [str(plan_file)], [], 0)
            else:
                print(f"⚠ Script output invalid, trying auto-fix...")
                if auto_fix_plan(self.spec_dir):
                    result = self.validator.validate_implementation_plan()
                    if result.valid:
                        print(f"✓ Auto-fixed implementation_plan.json")
                        return PhaseResult("planning", True, [str(plan_file)], [], 0)

                errors.append(f"Script output invalid: {result.errors}")

        # Fall back to agent
        print("\nFalling back to planner agent...")
        for attempt in range(MAX_RETRIES):
            print(f"\nRunning planner agent (attempt {attempt + 1})...")

            success, output = await self._run_agent("planner.md")

            if success and plan_file.exists():
                # Validate
                result = self.validator.validate_implementation_plan()
                if result.valid:
                    print(f"✓ Created valid implementation_plan.json via agent")
                    return PhaseResult("planning", True, [str(plan_file)], [], attempt)
                else:
                    # Try auto-fix
                    if auto_fix_plan(self.spec_dir):
                        result = self.validator.validate_implementation_plan()
                        if result.valid:
                            print(f"✓ Auto-fixed implementation_plan.json")
                            return PhaseResult("planning", True, [str(plan_file)], [], attempt)

                    errors.append(f"Agent attempt {attempt + 1}: {result.errors}")
                    print(f"✗ Plan created but invalid")
            else:
                errors.append(f"Agent attempt {attempt + 1}: Did not create plan file")

        return PhaseResult("planning", False, [], errors, MAX_RETRIES)

    async def phase_validation(self) -> PhaseResult:
        """Phase 6: Final validation."""
        print("\n" + "=" * 60)
        print("  PHASE 6: FINAL VALIDATION")
        print("=" * 60)

        results = self.validator.validate_all()
        all_valid = all(r.valid for r in results)

        for result in results:
            status = "✓" if result.valid else "✗"
            print(f"{status} {result.checkpoint}: {'PASS' if result.valid else 'FAIL'}")
            for err in result.errors:
                print(f"    Error: {err}")

        if all_valid:
            print("\n✓ All validation checks passed")
            return PhaseResult("validation", True, [], [], 0)
        else:
            errors = [
                f"{r.checkpoint}: {err}"
                for r in results
                for err in r.errors
            ]
            return PhaseResult("validation", False, [], errors, 0)

    # === Main Orchestration ===

    async def run(self, interactive: bool = True) -> bool:
        """Run the full spec creation process."""
        print("\n" + "=" * 60)
        print("  SPEC CREATION ORCHESTRATOR")
        print("=" * 60)
        print(f"\nSpec Directory: {self.spec_dir}")
        print(f"Project: {self.project_dir}")
        if self.task_description:
            print(f"Task: {self.task_description}")
        print()

        phases = [
            ("discovery", lambda: self.phase_discovery()),
            ("requirements", lambda: self.phase_requirements(interactive)),
            ("context", lambda: self.phase_context()),
            ("spec_writing", lambda: self.phase_spec_writing()),
            ("planning", lambda: self.phase_planning()),
            ("validation", lambda: self.phase_validation()),
        ]

        results = []

        for phase_name, phase_fn in phases:
            result = await phase_fn()
            results.append(result)

            if not result.success:
                print(f"\n✗ Phase '{phase_name}' failed after {result.retries} retries")
                print("Errors:")
                for err in result.errors:
                    print(f"  - {err}")
                print(f"\nSpec creation incomplete. Fix errors and retry.")
                return False

        # Summary
        print("\n" + "=" * 60)
        print("  SPEC CREATION COMPLETE")
        print("=" * 60)
        print(f"\nSpec saved to: {self.spec_dir}")
        print("\nFiles created:")
        for result in results:
            for f in result.output_files:
                print(f"  - {Path(f).name}")

        print(f"\nTo start the build:")
        print(f"  python auto-build/run.py --spec {self.spec_dir.name}")

        return True


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Orchestrate spec creation with validation"
    )
    parser.add_argument(
        "--task",
        type=str,
        help="Task description (what to build)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive mode (gather requirements from user)",
    )
    parser.add_argument(
        "--continue",
        dest="continue_spec",
        type=str,
        help="Continue an existing spec",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Project directory (default: current directory)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="Model to use for agent phases",
    )

    args = parser.parse_args()

    # Find project root (look for auto-build folder)
    project_dir = args.project_dir
    if not (project_dir / "auto-build").exists():
        # Try parent directories
        for parent in project_dir.parents:
            if (parent / "auto-build").exists():
                project_dir = parent
                break

    orchestrator = SpecOrchestrator(
        project_dir=project_dir,
        task_description=args.task,
        spec_name=args.continue_spec,
        model=args.model,
    )

    try:
        success = asyncio.run(orchestrator.run(interactive=args.interactive or not args.task))
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nSpec creation interrupted.")
        print(f"To continue: python auto-build/spec_runner.py --continue {orchestrator.spec_dir.name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
