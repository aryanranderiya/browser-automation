import json
import os
import time
from typing import Dict, List, Optional, Union

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from openai import OpenAI
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)
from playwright.async_api import (
    async_playwright,
)
from pydantic import BaseModel, Field
from utils.browser_session import session_manager
from utils.browser_utils import (
    BrowserAutomationError,
    ElementNotFoundError,
    ExtractorError,
    NavigationError,
    TimeoutError,
    extract_page_structure,
)
from utils.logger import setup_logger

load_dotenv()
router = APIRouter()
logger = setup_logger("browser_automation")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1", api_key=os.environ.get("GROQ_API_KEY")
)


# ================ Models ================


class BrowserRequest(BaseModel):
    """Base model for browser automation requests"""

    timeout: Optional[int] = Field(default=30, description="Global timeout in seconds")
    headless: Optional[bool] = Field(
        default=False, description="Run browser in headless mode"
    )
    browser_type: Optional[str] = Field(
        default="chromium", description="Browser to use: chromium, firefox, or webkit"
    )


class SessionResponse(BaseModel):
    """Response model for session operations"""

    session_id: str
    status: str
    message: str
    screenshot_path: Optional[str] = None


class CommandRequest(BaseModel):
    """Request model for executing commands"""

    user_input: str = Field(
        ..., description="Natural language input describing what to do in the browser"
    )


class CommandResponse(BaseModel):
    """Response model for command execution"""

    status: str
    message: str
    details: Optional[Dict] = None
    screenshot_path: Optional[str] = None


class ExtractRequest(BaseModel):
    """Request model for data extraction"""

    url: str
    extraction_type: str = Field(
        ...,
        description="Type of extraction: 'text', 'links', 'table', 'elements', 'json'",
    )
    selector: Optional[str] = Field(
        default=None, description="CSS selector to target specific elements"
    )
    attributes: Optional[List[str]] = Field(
        default=None, description="Attributes to extract from elements"
    )
    timeout: Optional[int] = Field(default=30, description="Global timeout in seconds")
    headless: Optional[bool] = Field(
        default=True, description="Run browser in headless mode"
    )
    browser_type: Optional[str] = Field(
        default="chromium", description="Browser to use: chromium, firefox, or webkit"
    )


class ExtractResponse(BaseModel):
    """Response model for data extraction"""

    status: str
    message: str
    data: Optional[Union[Dict, List, str]] = None
    screenshot_path: Optional[str] = None


# ================ Core Browser Action Handler ================


class BrowserAction:
    """Handles browser actions and commands"""

    def __init__(self, page, timeout: int = 30):
        self.page = page
        self.timeout = timeout
        self.logger = setup_logger("browser_actions")

    async def execute(self, command: Dict) -> Dict:
        """Execute a browser command and return result with status"""
        action = command.get("command_type")
        result = {"success": False, "message": "", "command": action}

        try:
            if action == "navigate":
                url = command.get("url", "")
                if not url.startswith(("http://", "https://")):
                    url = f"https://{url}"

                self.logger.info(f"Navigating to {url}")
                response = await self.page.goto(url, timeout=self.timeout * 1000)
                if response and response.ok:
                    result["success"] = True
                    result["message"] = f"Successfully navigated to {url}"
                else:
                    error_msg = f"Navigation to {url} failed or timed out"
                    result["message"] = error_msg
                    raise NavigationError(
                        error_msg,
                        {"url": url, "status": response.status if response else None},
                    )

            elif action == "search":
                selector = command.get("selector")
                query = command.get("query")
                self.logger.info(f"Searching {query} in {selector}")

                try:
                    await self.page.wait_for_selector(
                        selector, timeout=self.timeout * 1000
                    )
                except PlaywrightTimeoutError:
                    error_msg = f"Search element with selector '{selector}' not found"
                    result["message"] = error_msg
                    raise ElementNotFoundError(error_msg, {"selector": selector})

                await self.page.fill(selector, query)
                await self.page.press(selector, "Enter")

                try:
                    await self.page.wait_for_load_state(
                        "networkidle", timeout=self.timeout * 1000
                    )
                except PlaywrightTimeoutError:
                    error_msg = "Timeout waiting for page to load after search"
                    result["message"] = error_msg
                    raise TimeoutError(error_msg, {"query": query})

                result["success"] = True
                result["message"] = f"Search performed for '{query}'"

            elif action == "click":
                selector = command.get("selector")
                self.logger.info(f"Clicking element {selector}")

                try:
                    await self.page.wait_for_selector(
                        selector, timeout=self.timeout * 1000
                    )
                except PlaywrightTimeoutError:
                    error_msg = f"Click element with selector '{selector}' not found"
                    result["message"] = error_msg
                    raise ElementNotFoundError(error_msg, {"selector": selector})

                await self.page.click(selector)
                result["success"] = True
                result["message"] = f"Clicked on element: {selector}"

            elif action == "fill":
                selector = command.get("selector")
                value = command.get("value")
                self.logger.info(f"Filling {selector} with {value}")

                try:
                    await self.page.wait_for_selector(
                        selector, timeout=self.timeout * 1000
                    )
                except PlaywrightTimeoutError:
                    error_msg = f"Form field with selector '{selector}' not found"
                    result["message"] = error_msg
                    raise ElementNotFoundError(error_msg, {"selector": selector})

                await self.page.fill(selector, value)
                result["success"] = True
                result["message"] = f"Filled {selector} with text"

            elif action == "wait":
                seconds = command.get("seconds", 5)
                self.logger.info(f"Waiting for {seconds} seconds")

                await self.page.wait_for_timeout(seconds * 1000)
                result["success"] = True
                result["message"] = f"Waited for {seconds} seconds"

            elif action == "screenshot":
                filename = f"screenshot_{int(time.time())}.png"
                path = f"/tmp/{filename}"
                self.logger.info(f"Taking screenshot and saving to {path}")

                await self.page.screenshot(path=path)
                result["success"] = True
                result["message"] = "Screenshot captured"
                result["screenshot_path"] = path

            elif action == "extract_text":
                selector = command.get("selector", "body")
                self.logger.info(f"Extracting text from {selector}")

                try:
                    text = await self.page.text_content(selector)
                    result["success"] = True
                    result["message"] = f"Extracted text from {selector}"
                    result["data"] = text
                except Exception as e:
                    error_msg = f"Failed to extract text from selector '{selector}'"
                    result["message"] = error_msg
                    raise ExtractorError(
                        error_msg, {"selector": selector, "error": str(e)}
                    )

            elif action == "extract_table":
                selector = command.get("selector", "table")
                self.logger.info(f"Extracting table data from {selector}")

                try:
                    table_data = await self.page.evaluate(
                        """(selector) => {
                        const table = document.querySelector(selector);
                        if (!table) return null;
                        
                        const headers = Array.from(table.querySelectorAll('th')).map(th => th.innerText.trim());
                        const rows = Array.from(table.querySelectorAll('tr')).slice(1); // Skip header row
                        
                        return {
                            headers: headers,
                            rows: rows.map(row => 
                                Array.from(row.querySelectorAll('td')).map(cell => cell.innerText.trim())
                            )
                        };
                    }""",
                        selector,
                    )

                    if table_data:
                        result["success"] = True
                        result["message"] = f"Extracted table data from {selector}"
                        result["data"] = table_data
                    else:
                        error_msg = f"No table found with selector: {selector}"
                        result["message"] = error_msg
                        raise ExtractorError(error_msg, {"selector": selector})
                except Exception as e:
                    error_msg = (
                        f"Failed to extract table data from selector '{selector}'"
                    )
                    result["message"] = error_msg
                    raise ExtractorError(
                        error_msg, {"selector": selector, "error": str(e)}
                    )

            elif action == "extract_links":
                selector = command.get("selector", "a")
                self.logger.info(f"Extracting links from {selector}")

                try:
                    links = await self.page.evaluate(
                        """(selector) => {
                        const elements = document.querySelectorAll(selector);
                        return Array.from(elements).map(el => {
                            return {
                                text: el.innerText.trim(),
                                url: el.href,
                                title: el.title
                            };
                        });
                    }""",
                        selector,
                    )

                    result["success"] = True
                    result["message"] = f"Extracted {len(links)} links from {selector}"
                    result["data"] = links
                except Exception as e:
                    error_msg = f"Failed to extract links from selector '{selector}'"
                    result["message"] = error_msg
                    raise ExtractorError(
                        error_msg, {"selector": selector, "error": str(e)}
                    )

            elif action == "extract_elements":
                selector = command.get("selector")
                attributes = command.get("attributes", ["innerText"])
                self.logger.info(f"Extracting elements matching {selector}")

                try:
                    elements_data = await self.page.evaluate(
                        """(selector, attributes) => {
                        const elements = document.querySelectorAll(selector);
                        return Array.from(elements).map(el => {
                            const data = {};
                            attributes.forEach(attr => {
                                if (attr === 'innerText') {
                                    data[attr] = el.innerText.trim();
                                } else if (attr === 'innerHTML') {
                                    data[attr] = el.innerHTML;
                                } else {
                                    data[attr] = el.getAttribute(attr);
                                }
                            });
                            return data;
                        });
                    }""",
                        selector,
                        attributes,
                    )

                    result["success"] = True
                    result["message"] = (
                        f"Extracted {len(elements_data)} elements matching {selector}"
                    )
                    result["data"] = elements_data
                except Exception as e:
                    error_msg = f"Failed to extract elements from selector '{selector}'"
                    result["message"] = error_msg
                    raise ExtractorError(
                        error_msg,
                        {
                            "selector": selector,
                            "attributes": attributes,
                            "error": str(e),
                        },
                    )

            elif action == "extract_json":
                self.logger.info("Extracting structured JSON data from page")

                try:
                    json_data = await self.page.evaluate("""() => {
                        // Try to find JSON in standard locations
                        let jsonData = null;
                        
                        // Look for JSON-LD
                        const jsonLdScripts = document.querySelectorAll('script[type="application/ld+json"]');
                        if (jsonLdScripts.length > 0) {
                            try {
                                jsonData = JSON.parse(jsonLdScripts[0].textContent);
                                return { source: 'json-ld', data: jsonData };
                            } catch (e) {}
                        }
                        
                        // Look for structured data in meta tags
                        const metaTags = Array.from(document.querySelectorAll('meta[property^="og:"], meta[name^="twitter:"]'));
                        if (metaTags.length > 0) {
                            const metaData = {};
                            metaTags.forEach(tag => {
                                const key = tag.getAttribute('property') || tag.getAttribute('name');
                                metaData[key] = tag.getAttribute('content');
                            });
                            return { source: 'meta-tags', data: metaData };
                        }
                        
                        return null;
                    }""")

                    if json_data:
                        result["success"] = True
                        result["message"] = (
                            f"Extracted structured JSON data from {json_data['source']}"
                        )
                        result["data"] = json_data["data"]
                    else:
                        error_msg = "No structured JSON data found in page"
                        result["message"] = error_msg
                        raise ExtractorError(error_msg, {"page_url": self.page.url})
                except Exception as e:
                    error_msg = "Failed to extract JSON data from page"
                    result["message"] = error_msg
                    raise ExtractorError(error_msg, {"error": str(e)})

            else:
                error_msg = f"Unknown command type: {action}"
                result["message"] = error_msg
                raise ValueError(error_msg)

        except PlaywrightTimeoutError as e:
            error_msg = f"Timeout error executing {action}: {e}"
            self.logger.error(error_msg)
            result["message"] = error_msg
            raise TimeoutError(error_msg, {"command": action})

        except (NavigationError, ElementNotFoundError, TimeoutError, ExtractorError):
            self.logger.error(result["message"])
            raise

        except Exception as e:
            error_msg = f"Error executing {action}: {e}"
            self.logger.error(error_msg)
            result["message"] = error_msg
            raise BrowserAutomationError(
                error_msg, {"command": action, "error": str(e)}
            )

        return result


# ================ Helper Functions ================


def get_browser_commands(user_input: str, page_structure=None) -> List[Dict]:
    """Convert natural language to structured browser commands using LLM"""
    logger.info(f"Generating browser commands for input: {user_input}")

    try:
        # Define system prompt directly as a string
        from prompts.system_prompt import system_prompt as prompt_text
        system_content = prompt_text  # Use a different variable name to avoid confusion
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


async def execute_data_extraction(request: ExtractRequest) -> ExtractResponse:
    """Execute data extraction from a webpage"""
    logger.info(f"Processing extraction request for URL: {request.url}")

    try:
        command = {
            "command_type": f"extract_{request.extraction_type}",
        }

        if request.selector:
            command["selector"] = request.selector

        if request.attributes and request.extraction_type == "elements":
            command["attributes"] = request.attributes

        async with async_playwright() as p:
            browser_types = {
                "chromium": p.chromium,
                "firefox": p.firefox,
                "webkit": p.webkit,
            }

            browser_type = request.browser_type.lower()
            if browser_type not in browser_types:
                browser_type = "chromium"

            browser = await browser_types[browser_type].launch(
                headless=request.headless
            )
            page = await browser.new_page()

            action_executor = BrowserAction(page, timeout=request.timeout)

            navigate_command = {
                "command_type": "navigate",
                "url": request.url,
            }
            navigate_result = await action_executor.execute(navigate_command)

            if not navigate_result["success"]:
                await browser.close()
                return ExtractResponse(
                    status="error",
                    message=f"Failed to navigate to URL: {navigate_result['message']}",
                )

            extract_result = await action_executor.execute(command)

            filename = f"extract_screenshot_{int(time.time())}.png"
            path = f"/tmp/{filename}"
            await page.screenshot(path=path)

            await browser.close()

        if extract_result["success"]:
            return ExtractResponse(
                status="success",
                message=extract_result["message"],
                data=extract_result.get("data"),
                screenshot_path=path,
            )
        else:
            return ExtractResponse(
                status="error",
                message=extract_result["message"],
                screenshot_path=path,
            )

    except Exception as e:
        logger.error(f"Error in data extraction: {str(e)}")
        return ExtractResponse(
            status="error",
            message=f"Error during data extraction: {str(e)}",
        )


# ================ Session API Routes ================


@router.post("/session/start", response_model=SessionResponse)
async def start_session(request: BrowserRequest):
    """
    Start a new browser automation session.

    Creates a persistent browser instance that can receive multiple commands
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

        # Take initial screenshot
        session = await session_manager.get_session(session_id)
        screenshot_path = await session.take_screenshot()

        return SessionResponse(
            session_id=session_id,
            status="success",
            message="Browser session started successfully",
            screenshot_path=screenshot_path,
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
async def execute_command(session_id: str, request: CommandRequest):
    """
    Execute a command in the browser session.

    Examples:
    - "Go to amazon.com and search for laptops"
    - "Fill in the login form with username 'test' and password 'test123'"
    - "Click on the first search result"
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
        current_url = await page.url()
        if current_url and current_url != "about:blank":
            # Extract page structure to give context to the LLM
            page_structure = await extract_page_structure(page)
            commands = get_browser_commands(request.user_input, page_structure)
        else:
            commands = get_browser_commands(request.user_input)

        command_results = []

        # Execute each command
        for command in commands:
            result = await action_executor.execute(command)
            command_results.append(result)

            # Update last activity time
            session.last_activity = time.time()

            # If it was a navigation command, extract page structure for subsequent commands
            if command["command_type"] == "navigate" and result["success"]:
                # We could extract page structure here and update commands, but for
                # simplicity we'll keep the flow linear
                pass

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
            details={"results": command_results},
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


# ================ One-off API Routes ================


@router.post("/extract", response_model=ExtractResponse)
async def extract(request: ExtractRequest):
    """
    Extract data from a webpage without creating a persistent session.

    Examples:
    - Extract links: {"url": "https://example.com", "extraction_type": "links", "selector": "a.product-link"}
    - Extract table: {"url": "https://example.com/table", "extraction_type": "table", "selector": "table.data-table"}
    - Extract elements: {"url": "https://example.com/products", "extraction_type": "elements", "selector": ".product", "attributes": ["innerText", "data-id"]}
    """
    try:
        logger.info(
            f"Received extraction request for URL: {request.url}, type: {request.extraction_type}"
        )
        response = await execute_data_extraction(request)
        return response

    except Exception as e:
        logger.error(f"Error in extraction API: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute", response_model=CommandResponse)
async def execute_one_off(
    request: CommandRequest, browser_config: BrowserRequest = None
):
    """
    Execute a one-off browser automation task without creating a persistent session.

    This is useful for simple, one-time tasks that don't require maintaining state.

    Examples:
    - "Go to amazon.com and take a screenshot of the homepage"
    - "Search for 'Python tutorial' on google and extract the first 5 results"
    """
    if browser_config is None:
        browser_config = BrowserRequest()

    try:
        logger.info(f"Processing one-off execution request: {request.user_input}")
        command_results = []
        screenshot_path = None
        page_structure = None

        async with async_playwright() as p:
            browser_types = {
                "chromium": p.chromium,
                "firefox": p.firefox,
                "webkit": p.webkit,
            }

            browser_type = browser_config.browser_type.lower()
            if browser_type not in browser_types:
                browser_type = "chromium"

            browser = await browser_types[browser_type].launch(
                headless=browser_config.headless
            )
            page = await browser.new_page()

            action_executor = BrowserAction(page, timeout=browser_config.timeout)

            commands = get_browser_commands(request.user_input)

            for command in commands:
                result = await action_executor.execute(command)
                command_results.append(result)

                if command["command_type"] == "navigate" and result["success"]:
                    page_structure = await extract_page_structure(page)
                    # We could regenerate commands here based on page structure,
                    # but for simplicity we'll keep the flow linear

            # Take a final screenshot
            filename = f"final_screenshot_{int(time.time())}.png"
            path = f"/tmp/{filename}"
            await page.screenshot(path=path)
            screenshot_path = path

            await browser.close()

        success_count = sum(1 for result in command_results if result["success"])
        status = "success" if success_count == len(command_results) else "partial"
        if success_count == 0:
            status = "error"

        return CommandResponse(
            status=status,
            message=f"Executed {success_count}/{len(command_results)} commands successfully",
            details={"results": command_results},
            screenshot_path=screenshot_path,
        )

    except Exception as e:
        logger.error(f"Error in one-off execution: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
