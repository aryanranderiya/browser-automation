# filepath: /home/aryan/Downloads/Projects/crustdata-build-challenge/backend/routes/browser_agent.py
import json
import os
import time
import uuid
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException
from openai import OpenAI
from playwright.async_api import async_playwright, Page
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from utils.logger import setup_logger
from utils.browser_utils import extract_page_structure
from prompts.system_prompt import system_prompt

load_dotenv()
router = APIRouter(prefix="/browser-agent", tags=["browser-agent"])
logger = setup_logger("browser-agent")

# Initialize OpenAI client (using GROQ in this case)
client = OpenAI(
    base_url="https://api.groq.com/openai/v1", api_key=os.environ.get("GROQ_API_KEY")
)


class AgentRequest(BaseModel):
    task: str = Field(
        ..., description="Natural language task for the agent to complete"
    )
    max_steps: Optional[int] = Field(
        default=10, description="Maximum number of steps to execute"
    )
    headless: Optional[bool] = Field(
        default=False, description="Run browser in headless mode"
    )
    browser_type: Optional[str] = Field(
        default="chromium", description="Browser to use: chromium, firefox, or webkit"
    )
    start_url: Optional[str] = Field(
        default=None, description="URL to start the browsing session with"
    )
    interactive: Optional[bool] = Field(
        default=False,
        description="Whether to run in interactive mode where steps are executed one by one",
    )


class AgentResponse(BaseModel):
    status: str
    message: str
    details: Optional[Dict] = None
    steps_completed: int
    final_url: Optional[str] = None
    screenshot_path: Optional[str] = None
    session_id: Optional[str] = None


class AgentStepRequest(BaseModel):
    session_id: str = Field(..., description="The ID of the active agent session")
    steps: Optional[int] = Field(default=1, description="Number of steps to execute")


class AgentStepResponse(BaseModel):
    status: str
    message: str
    steps_completed: int
    current_url: Optional[str] = None
    screenshot_path: Optional[str] = None
    details: Optional[Dict] = None
    is_complete: bool = False


class AgentStep(BaseModel):
    observation: str
    thought: Optional[str] = None
    action: Dict


class AgentMemory:
    """Memory system to track agent state and history"""

    def __init__(self):
        self.history: List[AgentStep] = []
        self.current_state: Dict[str, Any] = {}
        self.task: str = ""
        self.logger = setup_logger("agent-memory")

    def add_step(self, step: AgentStep):
        """Add a step to the history"""
        self.history.append(step)

    def get_context(self, max_steps: int = 5) -> str:
        """Get the recent context as a formatted string for the LLM"""
        # Take only the most recent steps to avoid context limits
        recent_steps = (
            self.history[-max_steps:] if len(self.history) > max_steps else self.history
        )

        context = []
        for i, step in enumerate(recent_steps):
            context.append(f"Step {i + 1}:")
            context.append(f"Observation: {step.observation}")
            if step.thought:
                context.append(f"Thought: {step.thought}")
            context.append(f"Action: {json.dumps(step.action, indent=2)}")
            context.append("")

        return "\n".join(context)

    def summarize(self) -> str:
        """Generate a summary of the agent's actions so far"""
        if not self.history:
            return "No actions taken yet."

        steps = len(self.history)
        unique_actions = set([step.action.get("command_type") for step in self.history])

        return f"Completed {steps} steps with actions: {', '.join(unique_actions)}."


class BrowserAgent:
    """Main agent class that controls the browser and decision making"""

    def __init__(
        self,
        task: str,
        browser_type: str = "chromium",
        headless: bool = False,
        max_steps: int = 10,
    ):
        self.task = task
        self.browser_type = browser_type
        self.headless = headless
        self.max_steps = max_steps
        self.memory = AgentMemory()
        self.memory.task = task
        self.session_id = str(uuid.uuid4())
        self.logger = setup_logger(f"agent-{self.session_id[:8]}")
        self.page = None
        self.browser = None
        self.playwright = None
        self.current_step = 0
        self.final_screenshot = None
        self.is_complete = False

    async def start(self, start_url: Optional[str] = None):
        """Initialize the browser session"""
        self.logger.info(f"Starting browser agent session for task: {self.task}")
        self.playwright = await async_playwright().start()

        browser_types = {
            "chromium": self.playwright.chromium,
            "firefox": self.playwright.firefox,
            "webkit": self.playwright.webkit,
        }

        if self.browser_type.lower() not in browser_types:
            self.browser_type = "chromium"

        self.browser = await browser_types[self.browser_type.lower()].launch(
            headless=self.headless
        )
        self.page = await self.browser.new_page()

        # If we have a starting URL, navigate there
        if start_url:
            await self.page.goto(start_url)
            initial_content = await extract_page_structure(self.page)
            self.memory.current_state = initial_content

            # Create first observation
            first_observation = f"Started browser and navigated to {start_url}. Page title: {initial_content.get('title')}"
            first_step = AgentStep(
                observation=first_observation,
                action={"command_type": "navigate", "url": start_url},
            )
            self.memory.add_step(first_step)

        return True

    async def stop(self):
        """Close the browser and clean up resources"""
        self.logger.info(f"Stopping browser agent session {self.session_id}")

        try:
            if self.browser:
                await self.browser.close()
                self.browser = None
                self.page = None

            if self.playwright:
                await self.playwright.stop()
                self.playwright = None

            return True
        except Exception as e:
            self.logger.error(f"Error stopping browser: {e}")
            return False

    async def take_screenshot(self) -> str:
        """Take a screenshot of the current page"""
        if not self.page:
            raise ValueError("Browser not initialized")

        filename = f"agent_screenshot_{self.session_id}_{int(time.time())}.png"
        path = f"/tmp/{filename}"
        await self.page.screenshot(path=path)
        self.final_screenshot = path
        return path

    async def run(self) -> Dict:
        """Run the agent to complete the task"""
        if not self.page:
            await self.start()

        completed_steps = 0

        try:
            # Main agent loop
            while completed_steps < self.max_steps:
                self.logger.info(
                    f"Executing step {completed_steps + 1}/{self.max_steps}"
                )

                # Get current page state
                page_structure = await extract_page_structure(self.page)

                # Determine next action
                next_action = await self.determine_next_action(page_structure)

                # Execute the action
                result = await self.execute_action(next_action)

                # Record result
                self.memory.add_step(
                    AgentStep(
                        observation=result.get("message", "Action completed"),
                        thought=next_action.get("thought"),
                        action=next_action,
                    )
                )

                completed_steps += 1
                self.current_step += 1

                # Check if the task is complete
                if next_action.get("command_type") == "task_complete":
                    self.logger.info("Task marked as complete by agent")
                    self.is_complete = True
                    break

            # Take final screenshot
            screenshot_path = await self.take_screenshot()

            # Return results
            return {
                "status": "success" if completed_steps > 0 else "error",
                "message": f"Completed {completed_steps} steps"
                if completed_steps > 0
                else "Failed to execute task",
                "details": {"memory": self.memory.summarize()},
                "steps_completed": completed_steps,
                "final_url": await self.page.url() if self.page else None,
                "screenshot_path": screenshot_path,
                "is_complete": self.is_complete,
            }

        except Exception as e:
            self.logger.error(f"Error during agent execution: {e}")

            # Try to get a screenshot even if there was an error
            try:
                if self.page:
                    screenshot_path = await self.take_screenshot()
                else:
                    screenshot_path = None
            except:
                screenshot_path = None

            return {
                "status": "error",
                "message": f"Error during execution: {str(e)}",
                "details": {"error": str(e)},
                "steps_completed": completed_steps,
                "final_url": await self.page.url() if self.page else None,
                "screenshot_path": screenshot_path,
                "is_complete": self.is_complete,
            }
        finally:
            # Only close the browser if we're not in an interactive session
            if not self.session_id in active_agents:
                await self.stop()

    async def execute_steps(self, steps: int = 1) -> Dict:
        """Execute a specific number of steps"""
        if not self.page:
            raise ValueError("Browser session not initialized")

        steps_executed = 0

        try:
            # Execute requested number of steps
            for _ in range(steps):
                # Get current page state
                page_structure = await extract_page_structure(self.page)

                # Determine next action
                next_action = await self.determine_next_action(page_structure)

                # Execute the action
                result = await self.execute_action(next_action)

                # Record the step
                self.memory.add_step(
                    AgentStep(
                        observation=result.get("message", "Action completed"),
                        thought=next_action.get("thought"),
                        action=next_action,
                    )
                )

                steps_executed += 1
                self.current_step += 1

                # Check if the task is complete
                if next_action.get("command_type") == "task_complete":
                    self.logger.info("Task marked as complete by agent")
                    self.is_complete = True
                    break

            # Take screenshot
            screenshot_path = await self.take_screenshot()

            return {
                "status": "success",
                "message": f"Executed {steps_executed} steps",
                "steps_completed": steps_executed,
                "current_url": await self.page.url() if self.page else None,
                "screenshot_path": screenshot_path,
                "details": {
                    "current_step": self.current_step,
                    "memory": self.memory.summarize(),
                },
                "is_complete": self.is_complete,
            }

        except Exception as e:
            self.logger.error(f"Error executing agent steps: {e}")
            return {
                "status": "error",
                "message": f"Error executing agent steps: {str(e)}",
                "steps_completed": 0,
                "is_complete": self.is_complete,
            }

    async def determine_next_action(self, page_structure: Dict) -> Dict:
        """Determine the next action based on the page state and task"""
        self.logger.info("Determining next action")

        try:
            # Prepare context for the LLM
            system_content = system_prompt

            # Create recent history summary
            history_context = self.memory.get_context()

            # Create the full context
            page_info = json.dumps(page_structure, indent=2)
            user_content = f"""TASK: {self.task}

CURRENT PAGE STRUCTURE:
```json
{page_info}
```

RECENT HISTORY:
{history_context}

Based on the above information, determine the next action to take to complete the task. 
Think step-by-step about what's needed, and ONLY use selectors that exist in the current page structure.

If you believe the task is complete, use the command_type "task_complete".

Return a single command in the standard JSON format, prefixed with your reasoning as "thought":"""

            # Get response from LLM
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",  # or another appropriate model
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            self.logger.info("Received response from LLM")

            # Parse the response to extract thought and command
            parsed = json.loads(content)

            # Extract thought if present
            thought = None
            if "thought" in parsed:
                thought = parsed["thought"]

            # Get the command
            if "commands" in parsed and len(parsed["commands"]) > 0:
                command = parsed["commands"][0]
            elif "command" in parsed:
                command = parsed
            else:
                command = {
                    "command_type": "error",
                    "message": "No valid command found in LLM response",
                }

            # Add thought to the command
            command["thought"] = thought

            return command

        except Exception as e:
            self.logger.error(f"Error determining next action: {e}")
            return {
                "command_type": "error",
                "message": f"Error determining action: {str(e)}",
            }

    async def execute_action(self, action: Dict) -> Dict:
        """Execute a browser action and return the result"""
        action_type = action.get("command_type")
        self.logger.info(f"Executing action: {action_type}")

        result = {"success": False, "message": ""}

        try:
            # Create a BrowserAction to handle execution
            from routes.interact import BrowserAction

            action_executor = BrowserAction(self.page, timeout=30)

            # Skip 'thought' as it's not a command parameter
            clean_action = {k: v for k, v in action.items() if k != "thought"}

            # Special handling for task_complete
            if action_type == "task_complete":
                result = {
                    "success": True,
                    "message": "Task marked as complete",
                    "command": "task_complete",
                }
            else:
                result = await action_executor.execute(clean_action)

            return result

        except Exception as e:
            self.logger.error(f"Error executing action {action_type}: {e}")
            return {
                "success": False,
                "message": f"Error executing {action_type}: {str(e)}",
                "command": action_type,
            }


# Store active agent sessions
active_agents: Dict[str, BrowserAgent] = {}


@router.post("/execute", response_model=AgentResponse)
async def execute_agent(request: AgentRequest):
    """
    Run an agent to complete a task, with the option to run interactively.

    The agent uses an LLM to determine actions based on the page state and executes them
    until the task is complete or the maximum number of steps is reached.

    Set interactive=true to create a session that you can control step-by-step.

    Example input:
    {
        "task": "Search for puppies on Google and click on the first image result",
        "max_steps": 5,
        "headless": false,
        "browser_type": "chromium",
        "start_url": "https://www.google.com",
        "interactive": false
    }
    """
    try:
        logger.info(f"Starting browser agent for task: {request.task}")

        agent = BrowserAgent(
            task=request.task,
            browser_type=request.browser_type,
            headless=request.headless,
            max_steps=request.max_steps,
        )

        # Start the agent with the provided URL
        await agent.start(start_url=request.start_url)

        # If interactive mode, store the agent and return session info
        if request.interactive:
            session_id = agent.session_id
            active_agents[session_id] = agent

            return AgentResponse(
                status="success",
                message="Interactive agent session started",
                steps_completed=0,
                session_id=session_id,
            )

        # Otherwise, run the agent to completion
        result = await agent.run()

        return AgentResponse(
            status=result["status"],
            message=result["message"],
            details=result["details"],
            steps_completed=result["steps_completed"],
            final_url=result["final_url"],
            screenshot_path=result["screenshot_path"],
        )

    except Exception as e:
        logger.error(f"Error running browser agent: {str(e)}")
        return AgentResponse(
            status="error",
            message=f"Error running browser agent: {str(e)}",
            details={"error": str(e)},
            steps_completed=0,
        )


@router.post("/step", response_model=AgentStepResponse)
async def execute_step(request: AgentStepRequest):
    """
    Execute one or more steps in an existing agent session.

    Example input:
    {
        "session_id": "your-session-id",
        "steps": 1
    }
    """
    try:
        logger.info(f"Executing steps for agent session {request.session_id}")

        if request.session_id not in active_agents:
            raise HTTPException(
                status_code=404,
                detail=f"Agent session {request.session_id} not found or expired",
            )

        agent = active_agents[request.session_id]

        # Execute steps
        result = await agent.execute_steps(steps=request.steps)

        # If task is complete and we don't need the session anymore, clean up
        if result["is_complete"]:
            logger.info(f"Task complete, cleaning up session {request.session_id}")

        return AgentStepResponse(
            status=result["status"],
            message=result["message"],
            steps_completed=result["steps_completed"],
            current_url=result.get("current_url"),
            screenshot_path=result.get("screenshot_path"),
            details=result.get("details"),
            is_complete=result["is_complete"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing agent steps: {str(e)}")
        return AgentStepResponse(
            status="error",
            message=f"Error executing agent steps: {str(e)}",
            steps_completed=0,
            is_complete=False,
        )


@router.delete("/session/{session_id}", response_model=Dict)
async def cleanup_session(session_id: str):
    """
    Stop an agent session and clean up resources.
    """
    try:
        logger.info(f"Cleaning up agent session {session_id}")

        if session_id not in active_agents:
            return {
                "status": "warning",
                "message": f"Agent session {session_id} not found or already stopped",
            }

        agent = active_agents[session_id]
        result = await agent.stop()

        if result:
            # Remove from active sessions
            del active_agents[session_id]

        return {
            "status": "success" if result else "error",
            "message": "Agent session stopped successfully"
            if result
            else "Error stopping agent session",
        }

    except Exception as e:
        logger.error(f"Error stopping agent session: {str(e)}")
        return {"status": "error", "message": f"Error stopping agent session: {str(e)}"}


@router.get("/session/{session_id}", response_model=Dict)
async def get_session_status(session_id: str):
    """
    Get the current status of an agent session.
    """
    try:
        logger.info(f"Getting status for agent session {session_id}")

        if session_id not in active_agents:
            raise HTTPException(
                status_code=404,
                detail=f"Agent session {session_id} not found or expired",
            )

        agent = active_agents[session_id]

        return {
            "status": "active",
            "task": agent.task,
            "current_step": agent.current_step,
            "current_url": await agent.page.url() if agent.page else None,
            "browser_type": agent.browser_type,
            "headless": agent.headless,
            "memory_summary": agent.memory.summarize(),
            "is_complete": agent.is_complete,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
