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
    """Convert natural language to structured browser commands using LLM"""
    logger.info(f"Generating browser commands for input: {user_input}")

    try:
        system_content = system_prompt
        user_content = user_input

        if page_structure:
            page_info = json.dumps(page_structure, indent=2)
            user_content = f"""Page structure information:
            ```json
            {page_info}
            ```

Based on the above page structure, please help with this task: {user_input}

IMPORTANT: Only use selectors that exist in the page structure for interaction commands."""

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

        return commands

    except Exception as e:
        logger.error(f"Error generating browser commands: {str(e)}")
        raise Exception(f"Failed to generate browser commands: {str(e)}")
