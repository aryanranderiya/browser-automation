import json

from fastapi import APIRouter, HTTPException
from openai import OpenAI
from playwright.sync_api import sync_playwright
from prompts.system_prompt import system_prompt
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from utils.logger import setup_logger

load_dotenv()
router = APIRouter()
logger = setup_logger("automate")
client = OpenAI(
    base_url="https://api.groq.com/openai/v1", api_key=os.environ.get("GROQ_API_KEY")
)


class AutomationRequest(BaseModel):
    user_input: str


def get_chatgpt_commands(user_input):
    logger.info(f"Generating browser commands for input: {user_input}")
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        response_format={"type": "json_object"},
    )
    logger.info(f"API response: {response}")
    content = response.choices[0].message.content
    logger.info(f"Content: {content}")
    return content


def execute_browser_actions(commands):
    logger.info(f"Executing {len(commands)} browser actions")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        for command in commands:
            action = command["command_type"]

            try:
                if action == "navigate":
                    logger.info(f"Navigating to {command['url']}")
                    page.goto(command["url"])

                elif action == "search":
                    logger.info(
                        f"Searching {command['query']} in {command['selector']}"
                    )
                    page.fill(command["selector"], command["query"])
                    page.press(command["selector"], "Enter")
                    page.wait_for_load_state("networkidle")

                elif action == "click":
                    logger.info(f"Clicking element {command['selector']}")
                    page.wait_for_selector(command["selector"])
                    page.click(command["selector"])

                elif action == "fill":
                    logger.info(
                        f"Filling {command['selector']} with {command['value']}"
                    )
                    page.fill(command["selector"], command["value"])

                elif action == "wait":
                    logger.info(f"Waiting for {command['seconds']} seconds")
                    page.wait_for_timeout(command["seconds"] * 1000)

            except Exception as e:
                logger.error(f"Error executing {action}: {e}")

        browser.close()


@router.post("/automate")
def automate(request: AutomationRequest):
    try:
        logger.info(f"Received automation request: {request.user_input}")
        response_json = get_chatgpt_commands(request.user_input)
        # Parse the JSON string into a Python dictionary
        parsed_response = json.loads(response_json)
        commands = parsed_response["commands"]

        execute_browser_actions(commands)

        logger.info("Automation executed successfully")
        return {"status": "success", "message": "Automation executed successfully"}

    except Exception as e:
        logger.error(f"Error in automation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
