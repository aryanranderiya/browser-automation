from time import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from utils.browser_utils import extract_page_structure
from utils.logger import setup_logger
from utils.browser_session import session_manager
from routes.interact import BrowserAction, get_browser_commands

router = APIRouter(prefix="/automate", tags=["automation"])
logger = setup_logger("automate_routes")


class StartSessionRequest(BaseModel):
    browser_type: Optional[str] = Field(
        default="chromium", description="Browser to use: chromium, firefox, or webkit"
    )
    headless: Optional[bool] = Field(
        default=False, description="Run browser in headless mode"
    )
    timeout: Optional[int] = Field(default=30, description="Global timeout in seconds")


class SessionResponse(BaseModel):
    session_id: str
    status: str
    message: str


class ExecuteCommandRequest(BaseModel):
    user_input: str = Field(
        ..., description="Natural language input describing what to do in the browser"
    )


class CommandResponse(BaseModel):
    status: str
    message: str
    results: Optional[List[Dict]] = None
    screenshot_path: Optional[str] = None


@router.post("/session/start", response_model=SessionResponse)
async def start_session(request: StartSessionRequest):
    """
    Start a new browser automation session.

    This creates a persistent browser instance that can receive multiple commands
    over time using the same session ID.
    """
    try:
        logger.info(
            f"Starting new browser session with type={request.browser_type}, headless={request.headless}"
        )

        session_id = await session_manager.create_session(
            browser_type=request.browser_type,
            headless=request.headless,
            timeout=request.timeout,
        )

        return SessionResponse(
            session_id=session_id,
            status="success",
            message="Browser session started successfully",
        )

    except Exception as e:
        logger.error(f"Error starting session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/{session_id}/stop", response_model=SessionResponse)
async def stop_session(session_id: str):
    """
    Stop a browser automation session and release all resources.
    """
    try:
        logger.info(f"Stopping browser session {session_id}")

        result = await session_manager.stop_session(session_id)

        if result:
            return SessionResponse(
                session_id=session_id,
                status="success",
                message="Browser session stopped successfully",
            )
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found or already stopped",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/{session_id}/execute", response_model=CommandResponse)
async def execute_command(session_id: str, request: ExecuteCommandRequest):
    """
    Execute a command in the browser session.

    This directly executes the command and returns the result.

    Example: "Log into Instagram with username aryan and password 1234224"
    """
    try:
        logger.info(
            f"Executing command in session {session_id}: {request.user_input[:50]}..."
        )

        # Get the session
        session = await session_manager.get_session(session_id)
        if not session or not session.is_active:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id} not found or not active"
            )

        # Get the page
        page = await session.get_page()
        if not page:
            raise HTTPException(status_code=400, detail="Browser page is not available")

        # Create a BrowserAction instance for this page
        action_executor = BrowserAction(page, timeout=session.timeout)

        # Generate commands from the user input
        commands = get_browser_commands(request.user_input)
        command_results = []

        # Execute each command
        for command in commands:
            result = await action_executor.execute(command)
            command_results.append(result)

            # Update last activity time
            session.last_activity = time.time()

            # If it was a navigation command, extract page structure
            if command["command_type"] == "navigate" and result["success"]:
                page_structure = await extract_page_structure(page)
                logger.info("Extracted page structure after navigation")

        # Take a screenshot after execution
        screenshot_path = await session.take_screenshot()

        # Calculate success rate
        success_count = sum(1 for result in command_results if result["success"])
        status = "success" if success_count == len(command_results) else "partial"
        if success_count == 0:
            status = "error"

        return CommandResponse(
            status=status,
            message=f"Executed {success_count}/{len(command_results)} commands successfully",
            results=command_results,
            screenshot_path=screenshot_path,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing command: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}/status", response_model=Dict)
async def get_session_status(session_id: str):
    """
    Get the current status of a browser session.
    """
    try:
        logger.info(f"Getting status for session {session_id}")

        status = await session_manager.get_session_status(session_id)

        if "error" in status.get("status", ""):
            raise HTTPException(
                status_code=404,
                detail=status.get("message", f"Session {session_id} not found"),
            )

        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}/screenshot", response_model=Dict)
async def take_screenshot(session_id: str):
    """
    Take a screenshot of the current browser state.
    """
    try:
        logger.info(f"Taking screenshot for session {session_id}")

        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id} not found"
            )

        screenshot_path = await session.take_screenshot()

        return {
            "status": "success",
            "message": "Screenshot taken successfully",
            "screenshot_path": screenshot_path,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error taking screenshot: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
