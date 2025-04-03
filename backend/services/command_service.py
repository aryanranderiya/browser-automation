import os
import json
from typing import Dict, List
from openai import OpenAI
from dotenv import load_dotenv

from utils.logger import setup_logger
from prompts.system_prompt import system_prompt

load_dotenv()
logger = setup_logger("command_service")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1", api_key=os.environ.get("GROQ_API_KEY")
)


def get_browser_commands(
    user_input: str, page_structure=None, previous_commands=None
) -> List[Dict]:
    """Convert natural language to a SINGLE structured browser command using LLM"""
    logger.info(f"Generating browser command for input: {user_input}")

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

First navigate to an appropriate website. Return ONLY the NEXT SINGLE command to execute."""

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

Based on the current page state and previous actions, determine the NEXT SINGLE command to execute.
IMPORTANT: 
1. Return ONLY the NEXT SINGLE command to execute 
2. Only use selectors that exist in the page structure
3. Consider what has been done already before deciding the next action
4. Focus on making progress toward completing the user's task"""

        # Add previous command context to the user content
        if task_progress_context:
            user_content += f"\n\nCHRONOLOGICAL HISTORY OF PREVIOUS ACTIONS:\n{task_progress_context}"
            user_content += "\nBased on the above history and current page state, determine the next logical step."

        # Check if we need to determine task completion
        is_task_completion_check = False
        if previous_commands and len(previous_commands) > 0:
            # Add completion check instruction
            user_content += "\n\nTASK COMPLETION CHECK: Based on the user's original request and actions taken so far, is the task FULLY COMPLETED? If the task is complete, add 'task_completed': true to your command JSON and include a task_summary field explaining what was accomplished."
            is_task_completion_check = True

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        logger.info("Received JSON response from LLM")

        parsed_response = json.loads(content)
        commands = parsed_response.get("commands", [])

        if not commands:
            logger.warning("No commands generated from user input")
            return []

        # We're only interested in the first command
        if len(commands) > 1:
            logger.info("Multiple commands received, using only the first one")
            commands = [commands[0]]

        # For blank pages, enforce that the command must be navigation
        if is_blank_page and commands[0].get("command_type") != "navigate":
            # If no navigation command was provided, provide a default one
            logger.warning(
                "No navigation command provided for blank page, adding default navigation"
            )
            default_navigation = {
                "command_type": "navigate",
                "url": "https://www.google.com",
            }
            commands = [default_navigation]

        # Process the single command to ensure wait_for_page_load after navigation
        processed_commands = []
        cmd = commands[0]
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

        logger.info(f"Generated command: {processed_commands}")

        # Check for task completion signal
        task_completed = False
        task_summary = ""

        # Check if command indicates task completion
        if "task_completed" in cmd and cmd["task_completed"]:
            logger.info("LLM indicated task is complete!")
            task_completed = True
            if "task_summary" in cmd:
                task_summary = cmd["task_summary"]

        # Alternative check if task_completed is in the top-level response
        elif "task_completed" in parsed_response and parsed_response["task_completed"]:
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

        # Add task completion and summary to the first command
        if processed_commands and task_completed:
            processed_commands[0]["task_completed"] = True
            if task_summary:
                processed_commands[0]["task_summary"] = task_summary

        return processed_commands

    except Exception as e:
        logger.error(f"Error generating browser command: {str(e)}")
        raise Exception(f"Failed to generate browser command: {str(e)}")
