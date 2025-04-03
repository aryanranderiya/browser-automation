import asyncio
import time
import uuid
from typing import Dict, List, Optional, Any
from playwright.async_api import async_playwright, Browser, Page
from pydantic import BaseModel
from utils.logger import setup_logger
from utils.browser_utils import extract_page_structure
from services.command_service import get_browser_commands
from services.browser_service import BrowserAction
from dotenv import load_dotenv

load_dotenv()
logger = setup_logger("browser_session")


class BrowserCommand(BaseModel):
    """Command to be executed by the browser"""

    session_id: str
    command_id: str = ""
    user_input: str
    processed: bool = False
    result: Optional[Dict] = None
    timestamp: float = 0.0
    task_completed: bool = False
    task_progress: Optional[str] = None
    task_context: Dict[str, Any] = {}


class BrowserSession:
    """Manages a persistent browser session with command queue"""

    def __init__(
        self,
        browser_type: str = "chromium",
        headless: bool = False,
        timeout: int = 30,
        wait_for_captcha: bool = False,
    ):
        self.session_id = str(uuid.uuid4())
        self.browser_type = browser_type
        self.headless = headless
        self.timeout = timeout
        self.wait_for_captcha = wait_for_captcha
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.command_queue: List[BrowserCommand] = []
        self.current_command: Optional[BrowserCommand] = None
        self.is_processing: bool = False
        self.is_active: bool = False
        self.last_activity: float = time.time()
        self.session_data: Dict[str, Any] = {}  # Store session state like login info
        self.logger = setup_logger(f"session_{self.session_id[:8]}")
        self.captcha_resolved: asyncio.Event = asyncio.Event()

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
            "current_url": self.page.url if self.page and self.is_active else None,
        }

    async def _execute_command(self, command: BrowserCommand) -> Dict:
        """Execute a browser command and return the result"""
        self.logger.info(
            f"Executing command: {command.user_input[:50]}{'...' if len(command.user_input) > 50 else ''}"
        )

        try:
            # Store the original user input for potential reuse in sequential commands
            original_input = command.user_input
            command_chain_results = []
            max_iterations = 15  # Safety limit to prevent infinite loops
            iterations = 0
            task_completed = False
            final_explanation = ""

            # Execute commands sequentially, with each new command based on the current page state
            while not task_completed and iterations < max_iterations:
                iterations += 1
                self.logger.info(f"Task iteration {iterations}/{max_iterations}")

                # Get current page context if we've loaded a page
                page_structure = None
                current_url = self.page.url if self.page else ""
                self.logger.info(f"Current URL: {current_url}")

                if current_url and not current_url.startswith("about:"):
                    # Parse the current page to understand its structure
                    page_structure = await extract_page_structure(self.page)
                    self.logger.info(f"Extracted page structure from {current_url}")

                # Get commands from LLM based on current page state and previous actions
                browser_commands = get_browser_commands(
                    original_input,
                    page_structure,
                    command_chain_results if iterations > 1 else None,
                )

                if not browser_commands:
                    self.logger.info(
                        "No more commands to execute, task may be complete"
                    )
                    break

                # Check if we received a task_complete command type
                if (
                    len(browser_commands) == 1
                    and browser_commands[0].get("command_type") == "task_complete"
                ):
                    task_completed = True
                    final_explanation = browser_commands[0].get(
                        "message", "Task completed successfully"
                    )
                    self.logger.info(
                        f"Task completion signal received: {final_explanation}"
                    )
                    break

                # Check for task_completed flag in any command
                for cmd in browser_commands:
                    if cmd.get("task_completed", False):
                        task_completed = True
                        final_explanation = cmd.get(
                            "task_summary", "Task completed successfully"
                        )
                        self.logger.info(
                            f"Task completion flag found: {final_explanation}"
                        )
                        break

                # Create an instance of BrowserAction to handle command execution
                action_executor = BrowserAction(self.page, timeout=self.timeout)
                iteration_results = []

                # Execute each command in the sequence
                for cmd in browser_commands:
                    action = cmd.get("command_type", "")
                    self.logger.info(f"Processing action: {action}")

                    # Handle the wait_for_captcha action specially since it needs the Event object
                    if action == "wait_for_captcha":
                        message = cmd.get(
                            "message",
                            "Captcha detected. Please solve the captcha in the browser window.",
                        )
                        self.logger.info("Waiting for user to solve captcha")

                        # Reset the event (in case it was set previously)
                        self.captcha_resolved.clear()

                        if self.wait_for_captcha:
                            # Wait for the captcha to be resolved - this will be resumed via the API
                            result = {
                                "success": True,
                                "message": message,
                                "command": action,
                                "waiting_for_user": True,
                            }

                            # Wait for the event to be set
                            try:
                                await asyncio.wait_for(
                                    self.captcha_resolved.wait(), timeout=300
                                )  # 5 minute timeout
                                self.logger.info(
                                    "Captcha resolution received, continuing execution"
                                )
                                result["message"] = (
                                    "Captcha solved, continuing with automation"
                                )
                            except asyncio.TimeoutError:
                                self.logger.warning(
                                    "Timeout waiting for captcha resolution"
                                )
                                result["message"] = (
                                    "Timeout waiting for captcha to be solved"
                                )
                                result["success"] = False
                        else:
                            # If wait_for_captcha is False, just log and continue without waiting
                            result = {
                                "success": False,
                                "message": "Captcha detected but automatic waiting is disabled. Enable 'wait_for_captcha' to pause execution.",
                                "command": action,
                            }
                    else:
                        # For all other actions, use the BrowserAction executor
                        try:
                            self.logger.info(f"Executing command: {cmd}")
                            result = await action_executor.execute(cmd)
                        except Exception as e:
                            self.logger.error(
                                f"Error executing action {action}: {str(e)}"
                            )
                            result = {
                                "success": False,
                                "message": f"Error executing {action}: {str(e)}",
                                "command": action,
                            }

                    iteration_results.append(result)
                    command_chain_results.append(result)

                    # If this action failed and it's a critical action, stop processing this iteration
                    if not result["success"] and action in [
                        "navigate",
                        "click",
                        "fill",
                    ]:
                        self.logger.warning(
                            f"Critical action {action} failed, stopping command execution for this iteration"
                        )
                        break

                    # If we're waiting for captcha and the action was successful, don't process any further commands
                    if action == "wait_for_captcha" and result.get(
                        "waiting_for_user", False
                    ):
                        self.logger.info(
                            "Pausing command execution while waiting for captcha resolution"
                        )
                        break

                    # After navigation, we should stop and re-evaluate the new page
                    if action == "navigate" and result["success"]:
                        self.logger.info(
                            "Stopping after navigation to evaluate new page in next iteration"
                        )
                        break

                # Short delay between iterations to prevent overloading the browser
                await asyncio.sleep(
                    0.5
                )  # Reduced from 1 second to 0.5 seconds for faster execution

                # Generate an interim explanation for this iteration
                if (
                    iterations % 3 == 0 or task_completed
                ):  # Every 3 iterations or on completion
                    interim_explanation = self._generate_explanation(
                        command.user_input, iteration_results, page_structure
                    )
                    self.logger.info(
                        f"Iteration {iterations} progress: {interim_explanation}"
                    )

            # Generate the final explanation of what was done
            if task_completed and final_explanation:
                explanation = f"Task completed: {final_explanation}"
            else:
                explanation = self._generate_explanation(
                    command.user_input, command_chain_results, page_structure
                )
                if iterations >= max_iterations:
                    explanation += (
                        " The task execution reached its maximum number of steps."
                    )

            # Store task completion status
            command.task_completed = task_completed
            command.task_progress = explanation

            return {
                "status": "success",
                "results": command_chain_results,
                "explanation": explanation,
                "task_completed": task_completed,
            }

        except Exception as e:
            self.logger.error(f"Error executing command: {str(e)}")
            return {
                "status": "error",
                "message": f"Error during browser interaction: {str(e)}",
            }

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
                    elif cmd_type == "wait_for_captcha":
                        if action.get("waiting_for_user", False):
                            action_descriptions.append(
                                "paused execution for you to solve a captcha"
                            )
                        else:
                            action_descriptions.append("detected a captcha")
                    elif cmd_type == "extract_text":
                        action_descriptions.append("extracted text content")

                summary += f"{', '.join(action_descriptions)}"

            if failed_actions:
                if successful_actions:
                    summary += " but "
                summary += f"encountered {len(failed_actions)} error(s)"

                # Check if one of the errors was a captcha detection but wait_for_captcha was disabled
                captcha_errors = [
                    a for a in failed_actions if a.get("command") == "wait_for_captcha"
                ]
                if captcha_errors and not self.wait_for_captcha:
                    summary += ". A captcha was detected but automatic waiting is disabled. Enable 'wait_for_captcha' to pause execution when captchas are detected."

            if successful_actions and not failed_actions:
                summary += ". The task was completed successfully."
            elif successful_actions and failed_actions:
                summary += ". The task was partially completed."
            else:
                summary += ". The task could not be completed."

            # Add specific info if we're waiting for captcha resolution
            for action in results:
                if action.get("command") == "wait_for_captcha" and action.get(
                    "waiting_for_user", False
                ):
                    summary += " The browser is waiting for you to solve the captcha. Once solved, the automation will continue."

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
        self,
        browser_type: str = "chromium",
        headless: bool = False,
        timeout: int = 30,
        wait_for_captcha: bool = False,
    ) -> str:
        """Create a new browser session and return session ID"""
        session = BrowserSession(
            browser_type=browser_type,
            headless=headless,
            timeout=timeout,
            wait_for_captcha=wait_for_captcha,
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
