"""
BMAD Two-Agent Conversation Loop

This module implements the conversation pattern between:
- BMAD Agent: Runs the BMAD methodology workflows
- Human Replacement Agent: Responds to BMAD's questions as a knowledgeable collaborator

The conversation loop detects when BMAD is asking for input and routes to the
Human Replacement agent to generate responses, creating an autonomous feedback loop.
"""

import re
from pathlib import Path
from typing import Callable

from apps.backend.core.client import create_client
from apps.backend.core.debug import debug, debug_section, debug_success, debug_error
from apps.backend.agents.session import run_agent_session
from apps.backend.task_logger import LogPhase


# Patterns that indicate BMAD is waiting for input
INPUT_PATTERNS = [
    # Menu patterns
    r"\[C\]\s*Continue",
    r"\[1\].*\[2\].*\[3\]",
    r"Your choice\s*\[",
    r"Select.*option",
    # Question patterns
    r"\?\s*$",  # Ends with question mark
    r"\(y/n\)",
    r"\(yes/no\)",
    r"What do you think",
    r"Should we",
    r"Would you like",
    r"Do you want",
    r"How should we",
    r"What.*prefer",
    # Confirmation patterns
    r"proceed\?",
    r"continue\?",
    r"agree\?",
    r"approve",
]

# Patterns that indicate the phase is complete
COMPLETION_PATTERNS = [
    r"workflow complete",
    r"phase complete",
    r"documentation.*complete",
    r"successfully.*created",
    r"finished.*step\s*11",  # PRD final step
    r"all.*steps.*complete",
]


def is_waiting_for_input(text: str) -> bool:
    """Check if the BMAD agent output indicates it's waiting for input.

    Args:
        text: The BMAD agent's output text

    Returns:
        True if the agent appears to be waiting for human input
    """
    text_lower = text.lower()

    for pattern in INPUT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            return True

    return False


def is_phase_complete(text: str) -> bool:
    """Check if the BMAD workflow indicates phase completion.

    Args:
        text: The BMAD agent's output text

    Returns:
        True if the phase appears to be complete
    """
    text_lower = text.lower()

    for pattern in COMPLETION_PATTERNS:
        if re.search(pattern, text_lower, re.MULTILINE):
            return True

    return False


def extract_question_context(text: str, max_chars: int = 2000) -> str:
    """Extract the relevant question/decision context from BMAD output.

    Takes the last portion of the output that contains the question or menu,
    providing enough context for the Human Replacement agent to respond.

    Args:
        text: Full BMAD agent output
        max_chars: Maximum characters to include

    Returns:
        The relevant context for the Human Replacement agent
    """
    # Get the last max_chars, but try to start at a paragraph boundary
    if len(text) <= max_chars:
        return text

    truncated = text[-max_chars:]

    # Try to find a good starting point (paragraph break)
    paragraph_break = truncated.find("\n\n")
    if paragraph_break > 0 and paragraph_break < max_chars // 2:
        truncated = truncated[paragraph_break + 2:]

    return truncated


def load_human_replacement_prompt(
    phase: str,
    task_description: str,
    project_context: str,
    bmad_message: str,
) -> str:
    """Load and populate the Human Replacement agent prompt for a phase.

    Args:
        phase: BMAD phase (analyze, prd, architecture, epics, dev, review)
        task_description: The original task description
        project_context: Context about the project
        bmad_message: The BMAD agent's message requiring response

    Returns:
        The populated prompt for the Human Replacement agent
    """
    # Map phase to prompt file
    phase_prompt_map = {
        "analyze": "bmad_human_analyze.md",
        "prd": "bmad_human_prd.md",
        "architecture": "bmad_human_architecture.md",
        "epics": "bmad_human_epics.md",
        "stories": "bmad_human_epics.md",  # Same as epics
        "dev": "bmad_human_dev.md",
        "review": "bmad_human_review.md",
    }

    prompt_file = phase_prompt_map.get(phase, "bmad_human_base.md")

    # Load the prompt template
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_path = prompts_dir / prompt_file

    # Fall back to base prompt if phase-specific doesn't exist
    if not prompt_path.exists():
        prompt_path = prompts_dir / "bmad_human_base.md"

    prompt_template = prompt_path.read_text(encoding="utf-8")

    # Substitute placeholders
    prompt = prompt_template.replace("{task_description}", task_description or "No task description provided")
    prompt = prompt.replace("{project_context}", project_context or "No additional project context")
    prompt = prompt.replace("{bmad_message}", bmad_message)

    return prompt


async def run_human_replacement_response(
    project_dir: Path,
    spec_dir: Path,
    phase: str,
    task_description: str,
    project_context: str,
    bmad_message: str,
    model: str = "claude-sonnet-4-5-20250929",
) -> str:
    """Run the Human Replacement agent to generate a response to BMAD.

    The Human Replacement agent gives SHORT, DECISIVE responses - typically
    just "C" for continue, "y" for yes, or brief one-line answers.

    Args:
        project_dir: Project directory path
        spec_dir: Spec directory path
        phase: Current BMAD phase
        task_description: Original task description
        project_context: Project context information
        bmad_message: The BMAD agent's message requiring response
        model: Model to use for the Human Replacement agent (ignored, uses Haiku)

    Returns:
        The Human Replacement agent's response
    """
    debug_section("bmad.human_replacement", f"GENERATING RESPONSE FOR {phase.upper()}")

    # Load the appropriate prompt
    prompt = load_human_replacement_prompt(
        phase=phase,
        task_description=task_description,
        project_context=project_context,
        bmad_message=bmad_message,
    )

    debug(
        "bmad.human_replacement",
        "Prompt prepared",
        phase=phase,
        prompt_length=len(prompt),
        bmad_message_preview=bmad_message[:200] + "..." if len(bmad_message) > 200 else bmad_message,
    )

    # Create a lightweight client for the Human Replacement agent
    # Use Haiku for speed - we just need short, decisive responses
    # No thinking tokens needed - responses should be immediate and brief
    client = create_client(
        project_dir,
        spec_dir,
        model="claude-haiku-3-5-20241022",  # Fast model for short responses
        agent_type="planner",  # Read-only permissions - no file writes
        max_thinking_tokens=None,  # No extended thinking - just respond
    )

    try:
        async with client:
            # Send the prompt and get response
            await client.query(prompt)

            response_text = ""
            async for msg in client.receive_response():
                if hasattr(msg, "content"):
                    for block in msg.content:
                        if hasattr(block, "text"):
                            response_text += block.text

            # Clean up response - remove any meta-commentary
            response_text = response_text.strip()

            debug_success(
                "bmad.human_replacement",
                "Response generated",
                response_length=len(response_text),
                response_preview=response_text[:200] + "..." if len(response_text) > 200 else response_text,
            )

            return response_text

    except Exception as e:
        debug_error("bmad.human_replacement", f"Failed to generate response: {e}")
        # Return a safe default response
        return "Continue"


async def run_bmad_conversation_loop(
    project_dir: Path,
    spec_dir: Path,
    phase: str,
    workflow_prompt: str,
    task_description: str,
    project_context: str = "",
    model: str = "claude-sonnet-4-5-20250929",
    max_turns: int = 20,
    progress_callback: Callable[[str, float], None] | None = None,
) -> tuple[str, str]:
    """Run the BMAD workflow with Human Replacement agent responses.

    This implements the two-agent conversation loop:
    1. BMAD agent runs and may ask questions
    2. Human Replacement agent responds to questions
    3. Loop continues until phase complete or max turns reached

    Args:
        project_dir: Project directory path
        spec_dir: Spec directory path
        phase: Current BMAD phase
        workflow_prompt: The BMAD workflow instructions
        task_description: Original task description
        project_context: Project context information
        model: Model to use for agents
        max_turns: Maximum conversation turns before stopping
        progress_callback: Optional callback for progress updates

    Returns:
        Tuple of (status, full_conversation_text)
    """
    debug_section("bmad.conversation", f"STARTING CONVERSATION LOOP - {phase.upper()}")

    conversation_history = []
    full_response = ""
    turn_count = 0

    # Start with the workflow prompt
    current_prompt = workflow_prompt

    while turn_count < max_turns:
        turn_count += 1

        debug(
            "bmad.conversation",
            f"Turn {turn_count}/{max_turns}",
            phase=phase,
            prompt_length=len(current_prompt),
        )

        if progress_callback:
            progress = 30 + (turn_count / max_turns) * 60  # Progress from 30% to 90%
            progress_callback(f"BMAD conversation turn {turn_count}", progress)

        # Create BMAD client
        bmad_client = create_client(
            project_dir,
            spec_dir,
            model=model,
            agent_type="coder",
            max_thinking_tokens=None,
        )

        try:
            # Run BMAD agent
            async with bmad_client:
                await bmad_client.query(current_prompt)

                bmad_response = ""
                async for msg in bmad_client.receive_response():
                    if hasattr(msg, "content"):
                        for block in msg.content:
                            if hasattr(block, "text"):
                                bmad_response += block.text
                                print(block.text, end="", flush=True)

                full_response += bmad_response + "\n"
                conversation_history.append({"role": "bmad", "content": bmad_response})

                debug(
                    "bmad.conversation",
                    "BMAD response received",
                    response_length=len(bmad_response),
                )

                # Check if phase is complete
                if is_phase_complete(bmad_response):
                    debug_success("bmad.conversation", "Phase complete detected")
                    return "complete", full_response

                # Check if BMAD is waiting for input
                if is_waiting_for_input(bmad_response):
                    debug("bmad.conversation", "Input request detected, invoking Human Replacement")

                    # Extract the relevant context for the Human Replacement
                    question_context = extract_question_context(bmad_response)

                    # Get Human Replacement response
                    human_response = await run_human_replacement_response(
                        project_dir=project_dir,
                        spec_dir=spec_dir,
                        phase=phase,
                        task_description=task_description,
                        project_context=project_context,
                        bmad_message=question_context,
                        model=model,
                    )

                    conversation_history.append({"role": "human", "content": human_response})
                    full_response += f"\n[Human Response]: {human_response}\n\n"
                    print(f"\n[Human Response]: {human_response}\n")

                    # Build context for next turn
                    # Include the BMAD question and human response
                    current_prompt = f"""
Continue the workflow. The previous exchange was:

BMAD Agent: {question_context}

Human Response: {human_response}

Please continue with the next step of the workflow based on this response.
"""
                else:
                    # BMAD completed without asking for input
                    debug_success("bmad.conversation", "BMAD completed turn without input request")
                    return "complete", full_response

        except Exception as e:
            debug_error("bmad.conversation", f"Error in conversation turn: {e}")
            return "error", full_response

    debug("bmad.conversation", f"Max turns ({max_turns}) reached")
    return "max_turns", full_response
