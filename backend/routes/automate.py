from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from utils.logger import setup_logger
from utils.browser_session import session_manager

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


class AddCommandRequest(BaseModel):
    user_input: str = Field(
        ..., description="Natural language input describing what to do in the browser"
    )


class CommandResponse(BaseModel):
    command_id: str
    status: str
    message: str


class CommandResultResponse(BaseModel):
    status: str
    message: str
    result: Optional[Dict] = None
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


@router.post("/session/{session_id}/command", response_model=CommandResponse)
async def add_command(session_id: str, request: AddCommandRequest):
    """
    Add a new command to the session's queue.

    Commands are processed asynchronously in order. Use the returned command_id
    to check the status and result of the command.

    Example: "Log into Instagram with username aryan and password 1234224"
    """
    try:
        logger.info(
            f"Adding command to session {session_id}: {request.user_input[:50]}..."
        )

        command_id = await session_manager.add_command(
            session_id=session_id, user_input=request.user_input
        )

        if command_id:
            return CommandResponse(
                command_id=command_id,
                status="pending",
                message="Command added to queue and will be processed",
            )
        else:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id} not found or not active"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding command: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/session/{session_id}/command/{command_id}", response_model=CommandResultResponse
)
async def get_command_result(session_id: str, command_id: str):
    """
    Get the result of a command that was added to the queue.

    This endpoint should be polled until the command is completed.
    """
    try:
        logger.info(f"Getting result for command {command_id} in session {session_id}")

        result = await session_manager.get_command_result(
            session_id=session_id, command_id=command_id
        )

        if result.get("status") == "error":
            raise HTTPException(
                status_code=404,
                detail=result.get("message", "Command or session not found"),
            )

        return CommandResultResponse(
            status=result.get("status"),
            message=result.get("message", ""),
            result=result.get("result"),
            screenshot_path=result.get("screenshot_path"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting command result: {str(e)}")
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
