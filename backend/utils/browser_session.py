import asyncio
import time
import uuid
from typing import Dict, List, Optional, Any
from playwright.async_api import async_playwright, Browser, Page
from pydantic import BaseModel
from utils.logger import setup_logger
from utils.browser_utils import extract_page_structure
from prompts.system_prompt import system_prompt
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
logger = setup_logger("browser_session")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1", api_key=os.environ.get("GROQ_API_KEY")
)


class BrowserCommand(BaseModel):
    """Command to be executed by the browser"""

    session_id: str
    command_id: str = ""
    user_input: str
    processed: bool = False
    result: Optional[Dict] = None
    timestamp: float = 0.0


class BrowserSession:
    """Manages a persistent browser session with command queue"""

    def __init__(
        self, browser_type: str = "chromium", headless: bool = False, timeout: int = 30
    ):
        self.session_id = str(uuid.uuid4())
        self.browser_type = browser_type
        self.headless = headless
        self.timeout = timeout
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.command_queue: List[BrowserCommand] = []
        self.current_command: Optional[BrowserCommand] = None
        self.is_processing: bool = False
        self.is_active: bool = False
        self.last_activity: float = time.time()
        self.session_data: Dict[str, Any] = {}  # Store session state like login info
        self.logger = setup_logger(f"session_{self.session_id[:8]}")
        self.screenshot_path: Optional[str] = None

    async def start(self):
        """Start the browser session"""
        if self.is_active:
            return False

        self.logger.info(
            f"Starting browser session {self.session_id} with {self.browser_type}"
        )
        playwright = await async_playwright().start()

        browser_types = {
            "chromium": playwright.chromium,
            "firefox": playwright.firefox,
            "webkit": playwright.webkit,
        }

        if self.browser_type.lower() not in browser_types:
            self.browser_type = "chromium"

        self.browser = await browser_types[self.browser_type.lower()].launch(
            headless=self.headless
        )
        self.page = await self.browser.new_page()
        self.is_active = True
        self.last_activity = time.time()

        # Start background command processor
        asyncio.create_task(self._process_command_queue())
        return True

    async def stop(self):
        """Stop the browser session"""
        if not self.is_active:
            return False

        self.logger.info(f"Stopping browser session {self.session_id}")
        self.is_active = False

        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None

        return True

    async def add_command(self, user_input: str) -> str:
        """Add a command to the queue and return command ID"""
        if not self.is_active:
            raise ValueError("Browser session is not active")

        command_id = str(uuid.uuid4())
        command = BrowserCommand(
            session_id=self.session_id,
            command_id=command_id,
            user_input=user_input,
            timestamp=time.time(),
        )

        self.command_queue.append(command)
        self.last_activity = time.time()
        self.logger.info(
            f"Added command {command_id} to queue: {user_input[:50]}{'...' if len(user_input) > 50 else ''}"
        )

        return command_id

    async def get_command_result(self, command_id: str) -> Dict:
        """Get the result of a specific command"""
        for command in self.command_queue:
            if command.command_id == command_id:
                if command.processed:
                    return {
                        "status": "completed",
                        "result": command.result,
                        "screenshot_path": self.screenshot_path,
                    }
                else:
                    return {
                        "status": "pending",
                        "message": "Command is waiting to be processed",
                    }

        return {"status": "error", "message": "Command not found"}

    async def get_session_status(self) -> Dict:
        """Get current session status"""
        return {
            "session_id": self.session_id,
            "is_active": self.is_active,
            "browser_type": self.browser_type,
            "headless": self.headless,
            "pending_commands": len(
                [cmd for cmd in self.command_queue if not cmd.processed]
            ),
            "last_activity": self.last_activity,
            "current_url": await self.page.url()
            if self.page and self.is_active
            else None,
            "screenshot_path": self.screenshot_path,
        }

    async def take_screenshot(self) -> str:
        """Take a screenshot of the current page"""
        if not self.is_active or not self.page:
            raise ValueError("Browser session is not active")

        filename = f"screenshot_{self.session_id}_{int(time.time())}.png"
        path = f"/tmp/{filename}"
        await self.page.screenshot(path=path)
        self.screenshot_path = path
        return path

    async def _execute_command(self, command: BrowserCommand) -> Dict:
        """Execute a browser command and return the result"""
        self.logger.info(
            f"Executing command: {command.user_input[:50]}{'...' if len(command.user_input) > 50 else ''}"
        )

        try:
            # Get current page context if we've loaded a page
            page_structure = None
            current_url = await self.page.url() if self.page else ""

            if current_url and not current_url.startswith("about:"):
                page_structure = await extract_page_structure(self.page)
                self.logger.info(f"Extracted page structure from {current_url}")

            # Get commands from LLM
            browser_commands = self._get_browser_commands(
                command.user_input, page_structure
            )
            results = []

            for cmd in browser_commands:
                action = cmd.get("command_type", "")
                self.logger.info(f"Processing action: {action}")

                try:
                    if action == "navigate":
                        url = cmd.get("url", "")
                        if not url.startswith(("http://", "https://")):
                            url = f"https://{url}"

                        self.logger.info(f"Navigating to {url}")
                        response = await self.page.goto(
                            url, timeout=self.timeout * 1000
                        )

                        if response and response.ok:
                            result = {
                                "success": True,
                                "message": f"Successfully navigated to {url}",
                                "command": action,
                            }
                        else:
                            result = {
                                "success": False,
                                "message": f"Navigation to {url} failed or timed out",
                                "command": action,
                            }

                    elif action == "click":
                        selector = cmd.get("selector")
                        self.logger.info(f"Clicking element {selector}")

                        await self.page.wait_for_selector(
                            selector, timeout=self.timeout * 1000
                        )
                        await self.page.click(selector)

                        result = {
                            "success": True,
                            "message": f"Clicked on element: {selector}",
                            "command": action,
                        }

                    elif action == "fill":
                        selector = cmd.get("selector")
                        value = cmd.get("value")
                        self.logger.info(f"Filling {selector} with value")

                        await self.page.wait_for_selector(
                            selector, timeout=self.timeout * 1000
                        )
                        await self.page.fill(selector, value)

                        result = {
                            "success": True,
                            "message": f"Filled {selector} with text",
                            "command": action,
                        }

                    elif action == "wait":
                        seconds = cmd.get("seconds", 2)
                        self.logger.info(f"Waiting for {seconds} seconds")

                        await self.page.wait_for_timeout(seconds * 1000)

                        result = {
                            "success": True,
                            "message": f"Waited for {seconds} seconds",
                            "command": action,
                        }

                    elif action == "extract_text":
                        selector = cmd.get("selector", "body")
                        self.logger.info(f"Extracting text from {selector}")

                        text = await self.page.text_content(selector)

                        result = {
                            "success": True,
                            "message": f"Extracted text from {selector}",
                            "data": text,
                            "command": action,
                        }

                    else:
                        result = {
                            "success": False,
                            "message": f"Unsupported command type: {action}",
                            "command": action,
                        }

                except Exception as e:
                    self.logger.error(f"Error executing action {action}: {str(e)}")
                    result = {
                        "success": False,
                        "message": f"Error executing {action}: {str(e)}",
                        "command": action,
                    }

                results.append(result)

                # If this action failed and it's critical (like navigation), stop processing
                if not result["success"] and action in ["navigate", "click", "fill"]:
                    self.logger.warning(
                        f"Critical action {action} failed, stopping command execution"
                    )
                    break

            # Take a screenshot after command execution
            screenshot_path = await self.take_screenshot()

            # If we didn't have page structure before but we do now, extract it
            if (
                not page_structure
                and await self.page.url()
                and not (await self.page.url()).startswith("about:")
            ):
                page_structure = await extract_page_structure(self.page)

            # Generate an explanation of what was done
            explanation = self._generate_explanation(
                command.user_input, results, page_structure
            )

            return {
                "status": "success",
                "results": results,
                "explanation": explanation,
                "screenshot_path": screenshot_path,
            }

        except Exception as e:
            self.logger.error(f"Error executing command: {str(e)}")
            return {
                "status": "error",
                "message": f"Error during browser interaction: {str(e)}",
            }

    def _get_browser_commands(self, user_input: str, page_structure=None) -> List[Dict]:
        """Convert natural language to structured browser commands using LLM"""
        self.logger.info(f"Generating browser commands for input: {user_input}")

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
            self.logger.info("Received JSON response from LLM")

            parsed_response = json.loads(content)
            commands = parsed_response.get("commands", [])

            if not commands:
                self.logger.warning("No commands generated from user input")

            return commands

        except Exception as e:
            self.logger.error(f"Error generating browser commands: {str(e)}")
            return []

    def _generate_explanation(
        self, user_input: str, results: List[Dict], page_structure=None
    ) -> str:
        """Generate a human-readable explanation of what was done"""
        try:
            if not results:
                return "No actions were performed."

            successful_actions = [r for r in results if r.get("success", False)]
            failed_actions = [r for r in results if not r.get("success", False)]

            summary = f"Based on your request to '{user_input}', I "

            if successful_actions:
                action_descriptions = []
                for action in successful_actions:
                    cmd_type = action.get("command", "unknown")

                    if cmd_type == "navigate":
                        action_descriptions.append("navigated to the website")
                    elif cmd_type == "click":
                        action_descriptions.append("clicked on an element")
                    elif cmd_type == "fill":
                        action_descriptions.append("entered text into a field")
                    elif cmd_type == "wait":
                        action_descriptions.append("waited for the page to load")
                    elif cmd_type == "extract_text":
                        action_descriptions.append("extracted text content")

                summary += f"{', '.join(action_descriptions)}"

            if failed_actions:
                if successful_actions:
                    summary += " but "
                summary += f"encountered {len(failed_actions)} error(s)"

            # current_url = page_structure.get("url") if page_structure else "the page"

            if successful_actions and not failed_actions:
                summary += ". The task was completed successfully."
            elif successful_actions and failed_actions:
                summary += ". The task was partially completed."
            else:
                summary += ". The task could not be completed."

            return summary

        except Exception as e:
            self.logger.error(f"Error generating explanation: {str(e)}")
            return "Performed the requested browser actions."

    async def _process_command_queue(self):
        """Background task to process commands from the queue"""
        self.logger.info(
            f"Starting command queue processor for session {self.session_id}"
        )

        while self.is_active:
            if not self.is_processing and self.command_queue:
                # Find the first unprocessed command
                for i, cmd in enumerate(self.command_queue):
                    if not cmd.processed:
                        self.is_processing = True
                        self.current_command = cmd

                        # Execute the command
                        result = await self._execute_command(cmd)

                        # Update the command with the result
                        self.command_queue[i].result = result
                        self.command_queue[i].processed = True
                        self.current_command = None
                        self.is_processing = False
                        self.last_activity = time.time()
                        break

            # Check for session timeout (30 minutes of inactivity)
            if time.time() - self.last_activity > 1800:  # 30 minutes
                self.logger.info(
                    f"Session {self.session_id} timed out due to inactivity"
                )
                await self.stop()
                break

            await asyncio.sleep(0.5)

        self.logger.info(
            f"Command queue processor stopped for session {self.session_id}"
        )


# Global session manager
class BrowserSessionManager:
    def __init__(self):
        self.sessions: Dict[str, BrowserSession] = {}
        self.logger = setup_logger("session_manager")

    async def create_session(
        self, browser_type: str = "chromium", headless: bool = False, timeout: int = 30
    ) -> str:
        """Create a new browser session and return session ID"""
        session = BrowserSession(
            browser_type=browser_type, headless=headless, timeout=timeout
        )
        await session.start()

        self.sessions[session.session_id] = session
        self.logger.info(f"Created new browser session {session.session_id}")

        return session.session_id

    async def get_session(self, session_id: str) -> Optional[BrowserSession]:
        """Get a browser session by ID"""
        return self.sessions.get(session_id)

    async def add_command(self, session_id: str, user_input: str) -> Optional[str]:
        """Add a command to a session's queue"""
        session = await self.get_session(session_id)
        if not session:
            self.logger.error(f"Session {session_id} not found")
            return None

        return await session.add_command(user_input)

    async def get_command_result(self, session_id: str, command_id: str) -> Dict:
        """Get the result of a command in a session"""
        session = await self.get_session(session_id)
        if not session:
            return {"status": "error", "message": f"Session {session_id} not found"}

        return await session.get_command_result(command_id)

    async def get_session_status(self, session_id: str) -> Dict:
        """Get the status of a session"""
        session = await self.get_session(session_id)
        if not session:
            return {"status": "error", "message": f"Session {session_id} not found"}

        return await session.get_session_status()

    async def stop_session(self, session_id: str) -> bool:
        """Stop a browser session"""
        session = await self.get_session(session_id)
        if not session:
            return False

        result = await session.stop()
        if result:
            del self.sessions[session_id]
            self.logger.info(f"Stopped and removed session {session_id}")

        return result

    async def cleanup_inactive_sessions(self):
        """Cleanup inactive sessions (background task)"""
        self.logger.info("Starting inactive session cleanup task")

        while True:
            to_remove = []
            current_time = time.time()

            for session_id, session in self.sessions.items():
                # Check if session is inactive for more than 30 minutes
                if not session.is_active or (
                    current_time - session.last_activity > 1800
                ):
                    await session.stop()
                    to_remove.append(session_id)

            # Remove stopped sessions
            for session_id in to_remove:
                if session_id in self.sessions:
                    del self.sessions[session_id]
                    self.logger.info(f"Cleaned up inactive session {session_id}")

            await asyncio.sleep(300)  # Check every 5 minutes


# Global instance
session_manager = BrowserSessionManager()


# Start background cleanup task
async def start_cleanup_task():
    await session_manager.cleanup_inactive_sessions()


# Initialize cleanup task when module is imported
asyncio.create_task(start_cleanup_task())
