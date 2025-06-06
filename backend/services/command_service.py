import os
import json
from typing import Dict, List, Tuple
from openai import OpenAI
from dotenv import load_dotenv

from utils.logger import setup_logger
from prompts.system_prompt import system_prompt

load_dotenv()
logger = setup_logger("command_service")


def initialize_client() -> Tuple[OpenAI, str, str]:
    """Initialize the appropriate client based on available API keys.
    Returns a tuple of (client, api_provider, default_model)"""
    if os.environ.get("GROQ_API_KEY"):
        logger.info("Using Groq API")
        return (
            OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=os.environ.get("GROQ_API_KEY"),
            ),
            "groq",
            "llama-3.1-8b-instant",
        )
    elif os.environ.get("GEMINI_API_KEY"):
        logger.info("Using Gemini API")
        return (
            OpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/",
                api_key=os.environ.get("GEMINI_API_KEY"),
            ),
            "gemini",
            "gemini-2.5-pro-exp-03-25",
            # "gemini-1.5-flash",
            # "gemini-2.0-flash-lite",
        )
    else:
        logger.info("Using default OpenAI API")
        return (
            OpenAI(api_key=os.environ.get("OPENAI_API_KEY")),
            "openai",
            "gpt-3.5-turbo",
        )


client, API_PROVIDER, DEFAULT_MODEL = initialize_client()


def get_browser_commands(
    user_input: str, page_structure=None, previous_commands=None
) -> List[Dict]:
    """Convert natural language to structured browser commands using LLM.
    Can return multiple commands when they're related and on the same page."""
    logger.info(f"Generating browser commands for input: {user_input}")

    try:
        system_content = system_prompt
        user_content = user_input
        is_blank_page = False
        task_progress_context = ""

        # Add previous command results if available
        if previous_commands:
            task_progress_context = "\n\nPrevious actions performed:\n"
            for idx, cmd_result in enumerate(previous_commands):
                command_type = cmd_result.get("command", "unknown")
                success = cmd_result.get("success", False)
                message = cmd_result.get("message", "")

                # Add more detailed information about the command
                if "data" in cmd_result:
                    data_info = ""
                    if isinstance(cmd_result["data"], str):
                        # For text data, show a reasonable preview
                        data_preview = (
                            cmd_result["data"][:300] + "..."
                            if len(cmd_result["data"]) > 300
                            else cmd_result["data"]
                        )
                        data_info = f"\n   Extracted text: {data_preview}"
                    elif (
                        isinstance(cmd_result["data"], dict)
                        and "headers" in cmd_result["data"]
                        and "rows" in cmd_result["data"]
                    ):
                        # For table data, include summary
                        data_info = f"\n   Extracted table with {len(cmd_result['data']['headers'])} columns and {len(cmd_result['data']['rows'])} rows"
                    elif isinstance(cmd_result["data"], list):
                        # For list data (like links), include count
                        data_info = f"\n   Extracted {len(cmd_result['data'])} items"
                    else:
                        # For other data, include a summary
                        data_info = (
                            f"\n   Extracted data: {str(cmd_result['data'])[:200]}..."
                        )

                    # Include current state and result of action
                    if success:
                        task_progress_context += f"{idx + 1}. Successfully {command_type}: {message}{data_info}\n"
                    else:
                        task_progress_context += (
                            f"{idx + 1}. Failed {command_type}: {message}\n"
                        )
                else:
                    # For commands without data, just show status
                    if success:
                        task_progress_context += (
                            f"{idx + 1}. Successfully {command_type}: {message}\n"
                        )
                    else:
                        task_progress_context += (
                            f"{idx + 1}. Failed {command_type}: {message}\n"
                        )

        # Check if we're on a blank page
        if not page_structure or (
            page_structure and page_structure.get("url", "").startswith("about:")
        ):
            is_blank_page = True
            logger.info(
                "Page is blank or at about:blank. Will prioritize navigation commands."
            )
            # Add specific instructions to ensure navigation happens first
            user_content = f"""IMPORTANT: The page is currently blank or at about:blank. You MUST return a navigation command.

For the task: {user_input}

First navigate to an appropriate website. Return ONLY a navigation command."""

        elif page_structure:
            # Clean up page structure to focus on the most useful parts
            cleaned_page_structure = {
                "url": page_structure.get("url", ""),
                "title": page_structure.get("title", ""),
                "headings": page_structure.get("headings", {}),
                "pageFeatures": page_structure.get("pageFeatures", {}),
                "interactiveElements": page_structure.get("interactiveElements", {}),
            }

            page_info = json.dumps(cleaned_page_structure, indent=2)
            user_content = f"""Current page information:
```json
{page_info}
```

TASK: {user_input}

Based on the current page state and previous actions, determine the commands to execute.
IMPORTANT: 
1. You can group MULTIPLE RELATED COMMANDS when they operate on the same page (especially form filling)
2. Only use selectors that exist in the page structure
3. Consider what has been done already before deciding the next action
4. GROUP FORM FILLING operations into a single response with multiple commands"""

        # Add previous command context to the user content
        if task_progress_context:
            user_content += f"\n\nCHRONOLOGICAL HISTORY OF PREVIOUS ACTIONS:\n{task_progress_context}"
            user_content += "\nBased on the above history and current page state, determine the next logical step(s)."

        # Use the API_PROVIDER and DEFAULT_MODEL constants instead of checking base_url
        model = DEFAULT_MODEL
        response_format = {"type": "json_object"}

        logger.info(f"Using API provider: {API_PROVIDER} with model: {model}")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            response_format=response_format,
        )

        content = response.choices[0].message.content
        logger.info(f"Received JSON response from LLM: {content=} {page_structure=}")

        # Fix common JSON formatting issues before parsing
        try:
            parsed_response = json.loads(content)

        except json.JSONDecodeError as json_err:
            # Try to fix common issues with boolean values being strings
            if "Expecting ',' delimiter" in str(
                json_err
            ) or "Expecting property name" in str(json_err):
                logger.warning(
                    f"JSON parsing error: {str(json_err)}, attempting to fix..."
                )
                fixed_content = content.replace('": "true"', '": true').replace(
                    '": "false"', '": false'
                )
                try:
                    parsed_response = json.loads(fixed_content)
                    logger.info("Successfully fixed JSON format issues")
                except json.JSONDecodeError as retry_err:
                    logger.error(f"Failed to fix JSON format: {str(retry_err)}")
                    raise
            else:
                raise

        commands = parsed_response.get("commands", [])

        # Normalize command values - convert string booleans to actual booleans
        for cmd in commands:
            for key, value in cmd.items():
                if isinstance(value, str):
                    if value.lower() == "true":
                        cmd[key] = True
                    elif value.lower() == "false":
                        cmd[key] = False
                    # Also handle numeric strings
                    elif value.isdigit():
                        cmd[key] = int(value)

        if not commands:
            logger.warning("No commands generated from user input")
            return []

        # For blank pages, enforce that the command must be navigation and there's only one command
        if is_blank_page:
            if not commands or commands[0].get("command_type") != "navigate":
                # If no navigation command was provided, provide a default one
                logger.warning(
                    "No navigation command provided for blank page, adding default navigation"
                )
                commands = [
                    {
                        "command_type": "navigate",
                        "url": "https://www.google.com",
                    }
                ]
            # For blank pages, only allow the first command and it must be navigation
            commands = [commands[0]]

        # Process commands to add wait_for_page_load after navigation
        processed_commands = []
        for i, cmd in enumerate(commands):
            processed_commands.append(cmd)

            # If this is a navigation command, insert a wait_for_page_load command after it
            if cmd.get("command_type") == "navigate":
                wait_command = {
                    "command_type": "wait_for_page_load",
                    "timeout": 10000,  # 10 seconds timeout
                }
                processed_commands.append(wait_command)
                logger.info(
                    f"Added wait_for_page_load command after navigation to {cmd.get('url')}"
                )

                # If there are more commands after a navigation, remove them
                # (we should only execute commands after we've confirmed the page loaded)
                if i < len(commands) - 1:
                    logger.warning(
                        "Removing commands after navigation as they should be executed in the next iteration"
                    )
                    break

        logger.info(f"Generated {len(processed_commands)} commands")

        # Check for task completion signal
        task_completed = False
        task_summary = ""

        # Check if any command indicates task completion
        for cmd in commands:
            if "task_completed" in cmd and cmd["task_completed"]:
                logger.info("LLM indicated task is complete!")
                task_completed = True
                if "task_summary" in cmd:
                    task_summary = cmd["task_summary"]
                break

        # Alternative check if task_completed is in the top-level response
        if (
            not task_completed
            and "task_completed" in parsed_response
            and parsed_response["task_completed"]
        ):
            logger.info("LLM indicated task is complete in top-level response!")
            task_completed = True
            if "task_summary" in parsed_response:
                task_summary = parsed_response["task_summary"]
            # If no commands and task is completed, return special marker
            if not commands:
                return [
                    {
                        "command_type": "task_complete",
                        "message": task_summary
                        or "Task has been completed successfully",
                    }
                ]

        # Add task completion and summary to the last command if task is completed
        if processed_commands and task_completed:
            processed_commands[-1]["task_completed"] = True
            if task_summary:
                processed_commands[-1]["task_summary"] = task_summary

        return processed_commands

    except Exception as e:
        logger.error(f"Error generating browser command: {str(e)}")
        raise Exception(f"Failed to generate browser command: {str(e)}")
