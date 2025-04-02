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


def get_browser_commands(user_input: str, page_structure=None) -> List[Dict]:
    """Convert natural language to a SINGLE structured browser command using LLM"""
    logger.info(f"Generating browser command for input: {user_input}")

    try:
        system_content = system_prompt
        user_content = user_input
        is_blank_page = False

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
            page_info = json.dumps(page_structure, indent=2)
            user_content = f"""Page structure information:
            ```json
            {page_info}
            ```

Based on the above page structure, please help with this task: {user_input}

IMPORTANT: 
1. Return ONLY the NEXT SINGLE command to execute 
2. Only use selectors that exist in the page structure
3. Focus only on the very next step needed, not the entire task"""

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
            logger.info(f"Multiple commands received, using only the first one")
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

        return processed_commands

    except Exception as e:
        logger.error(f"Error generating browser command: {str(e)}")
        raise Exception(f"Failed to generate browser command: {str(e)}")
