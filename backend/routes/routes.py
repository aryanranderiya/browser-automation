from fastapi import APIRouter, HTTPException, BackgroundTasks
from dotenv import load_dotenv
from typing import Optional

from utils.logger import setup_logger
from models.interaction import (
    InteractionRequest,
    InteractionResponse,
)
from services.interaction_service import execute_browser_interaction
from utils.browser_session import session_manager

load_dotenv()
router = APIRouter()
logger = setup_logger("interact")


@router.post("/start_browser")
async def start_browser(
    browser_type: Optional[str] = "chromium",
    headless: Optional[bool] = False,
    timeout: Optional[int] = 30,
    wait_for_captcha: Optional[bool] = True,
):
    """
    API endpoint to start a new browser session

    Returns a session_id that can be used with other endpoints
    """
    try:
        logger.info(
            f"Starting browser with parameters: browser_type={browser_type}, headless={headless}, timeout={timeout}s"
        )

        session_id = await session_manager.create_session(
            browser_type=browser_type,
            headless=headless,
            timeout=timeout,
            wait_for_captcha=wait_for_captcha,
        )

        if not session_id:
            raise HTTPException(
                status_code=500, detail="Failed to create browser session"
            )

        status = await session_manager.get_session_status(session_id)

        return {
            "status": "success",
            "message": "Browser session started successfully",
            "session_id": session_id,
            "details": status,
        }

    except Exception as e:
        logger.error(f"Error starting browser: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop_browser/{session_id}")
async def stop_browser(session_id: str):
    """
    API endpoint to stop a browser session

    Call this endpoint when you're done with a browser session to free up resources
    """
    try:
        logger.info(f"Stopping browser session: {session_id}")

        result = await session_manager.stop_session(session_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found or already stopped",
            )

        return {
            "status": "success",
            "message": f"Browser session {session_id} stopped successfully",
        }

    except Exception as e:
        logger.error(f"Error stopping browser: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/interact/{session_id}", response_model=InteractionResponse)
async def execute_command(session_id: str, request: InteractionRequest):
    """
    API endpoint to execute a command in an existing browser session

    Example input:
    {
        "user_input": "Log into Twitter using my account example@gmail.com with password mysecretpass123",
        "timeout": 45
    }
    """
    try:
        logger.info(
            f"Executing command in session {session_id} with parameters: timeout={request.timeout}s"
        )

        # Check if session exists
        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id} not found"
            )

        # Add command to session
        command_id = await session_manager.add_command(session_id, request.user_input)

        if not command_id:
            raise HTTPException(
                status_code=500, detail="Failed to add command to session"
            )

        # Wait briefly for command to start processing
        import asyncio

        await asyncio.sleep(0.5)

        # Get initial status
        result = await session_manager.get_command_result(session_id, command_id)

        if result.get("status") == "completed":
            # Command completed immediately
            command_result = result.get("result", {})
            status = "success" if command_result.get("status") != "error" else "error"

            # Check if task was completed
            task_completed = command_result.get("task_completed", False)
            completion_status = "completed" if task_completed else "in_progress"

            return InteractionResponse(
                status=status,
                message=command_result.get("explanation", "Command executed"),
                details={
                    "command_id": command_id,
                    "session_id": session_id,
                    "results": command_result.get("results", []),
                    "task_status": completion_status,
                },
                screenshot_path=command_result.get("screenshot_path"),
            )
        else:
            # Command is still processing
            return InteractionResponse(
                status="pending",
                message="Command is being processed. Check status with /command_status endpoint.",
                details={"command_id": command_id, "session_id": session_id},
            )

    except Exception as e:
        logger.error(f"Error executing command: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/command_status/{session_id}/{command_id}")
async def command_status(session_id: str, command_id: str):
    """
    API endpoint to check the status of a command

    Returns the current status and results if the command has completed
    """
    try:
        logger.info(f"Checking status of command {command_id} in session {session_id}")

        result = await session_manager.get_command_result(session_id, command_id)

        # If the command is completed, check task status
        if result.get("status") == "completed":
            command_result = result.get("result", {})

            # Add task completion information
            task_completed = command_result.get("task_completed", False)
            completion_status = "completed" if task_completed else "in_progress"

            result["task_status"] = completion_status

            # If task is still in progress, add more context about progress
            if not task_completed and "results" in command_result:
                # Get count of actions completed
                completed_actions = len(command_result.get("results", []))
                result["progress"] = {
                    "actions_completed": completed_actions,
                    "last_action": command_result["results"][-1].get(
                        "command", "unknown"
                    )
                    if completed_actions > 0
                    else None,
                    "current_explanation": command_result.get("explanation", ""),
                }

        return result

    except Exception as e:
        logger.error(f"Error checking command status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/interact", response_model=InteractionResponse)
async def interact(request: InteractionRequest, background_tasks: BackgroundTasks):
    """
    API endpoint to handle natural language browser interactions

    This endpoint creates a new browser session, executes the command, and then closes the session.
    For persistent sessions, use the /start_browser and /interact/{session_id} endpoints instead.

    Example input:
    {
        "user_input": "Log into Twitter using my account example@gmail.com with password mysecretpass123",
        "timeout": 45,
        "headless": false,
        "browser_type": "chromium"
    }
    """
    try:
        logger.info(
            f"Received interaction request with parameters: timeout={request.timeout}s, headless={request.headless}"
        )

        response = await execute_browser_interaction(request)

        return response

    except Exception as e:
        logger.error(f"Error in interaction API: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resolve_captcha/{session_id}")
async def resolve_captcha(session_id: str):
    """
    API endpoint to signal that a captcha has been resolved by the user

    Call this endpoint after solving a captcha manually in the browser
    """
    try:
        from utils.browser_session import session_manager

        logger.info(f"Received captcha resolution signal for session: {session_id}")

        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id} not found"
            )

        # Signal that captcha has been resolved
        session.captcha_resolved.set()

        return {
            "status": "success",
            "message": "Captcha resolution acknowledged. Execution will continue.",
        }

    except Exception as e:
        logger.error(f"Error in captcha resolution API: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}")
async def get_session_status(session_id: str):
    """
    API endpoint to check the status of a browser session

    Call this endpoint to check if a session is active, waiting for captcha resolution, etc.
    """
    try:
        from utils.browser_session import session_manager

        logger.info(f"Checking status for session: {session_id}")

        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id} not found"
            )

        status = await session_manager.get_session_status(session_id)

        # Check if there's a command that's waiting for captcha resolution
        is_waiting_for_captcha = False
        for cmd in session.command_queue:
            if cmd.processed and cmd.result:
                results = cmd.result.get("results", [])
                if any(r.get("waiting_for_user", False) for r in results):
                    is_waiting_for_captcha = True
                    break

        return {
            "status": "waiting_for_captcha" if is_waiting_for_captcha else "active",
            "session_info": status,
            "screenshot_path": session.screenshot_path,
        }

    except Exception as e:
        logger.error(f"Error in session status API: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
