import time
import asyncio

from utils.browser_session import session_manager
from utils.logger import setup_logger
from models.interaction import InteractionRequest, InteractionResponse

logger = setup_logger("interaction_service")


async def execute_browser_interaction(
    request: InteractionRequest,
) -> InteractionResponse:
    """Execute browser interactions based on natural language commands"""
    logger.info(f"Processing interaction request: {request.user_input}")
    session_id = None

    try:
        # Create a temporary browser session
        session_id = await session_manager.create_session(
            browser_type=request.browser_type.lower(),
            headless=request.headless,
            timeout=request.timeout,
            wait_for_captcha=request.wait_for_captcha,
        )

        # Add the command to the session
        command_id = await session_manager.add_command(session_id, request.user_input)

        # Wait for the command to complete (with a timeout)
        max_wait = 30  # seconds
        start_time = time.time()
        while time.time() - start_time < max_wait:
            result = await session_manager.get_command_result(session_id, command_id)

            if result.get("status") == "completed":
                # Return the result directly
                command_result = result.get("result", {})
                status = "success"
                if command_result.get("status") == "error":
                    status = "error"

                results = command_result.get("results", [])
                if any(r.get("waiting_for_user", False) for r in results):
                    # If we're waiting for user input on captcha, return that info
                    return InteractionResponse(
                        status="waiting_for_captcha",
                        message=f"Captcha detected. Please solve the captcha in the browser window and then call /resolve_captcha/{session_id}",
                        details={
                            "session_id": session_id,
                            "results": results,
                            "explanation": command_result.get("explanation", ""),
                        },
                    )

                # If not waiting for captcha, stop the session if it was created for this request
                if not request.wait_for_captcha:
                    await session_manager.stop_session(session_id)

                return InteractionResponse(
                    status=status,
                    message=command_result.get("explanation", ""),
                    details={"results": results, "session_id": session_id},
                )

            await asyncio.sleep(0.5)

        # If we timed out, return a waiting response
        return InteractionResponse(
            status="pending",
            message="Request is still being processed. Check back later for results.",
            details={"session_id": session_id},
        )

    except Exception as e:
        # Cleanup session on error
        if session_id:
            try:
                await session_manager.stop_session(session_id)
            except:
                pass

        logger.error(f"Error in browser interaction: {str(e)}")
        return InteractionResponse(
            status="error",
            message=f"Error during browser interaction: {str(e)}",
            details={"error": str(e)},
        )
