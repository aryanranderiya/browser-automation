import json
import os
import time
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, BackgroundTasks
from openai import OpenAI
from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from utils.logger import setup_logger
from utils.browser_utils import (
    BrowserAutomationError,
    NavigationError,
    ElementNotFoundError,
    TimeoutError,
    ExtractorError,
)
from prompts.system_prompt import system_prompt

load_dotenv()
router = APIRouter()
logger = setup_logger("interact")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1", api_key=os.environ.get("GROQ_API_KEY")
)


class InteractionRequest(BaseModel):
    user_input: str
    timeout: Optional[int] = Field(default=30, description="Global timeout in seconds")
    headless: Optional[bool] = Field(
        default=False, description="Run browser in headless mode"
    )
    browser_type: Optional[str] = Field(
        default="chromium", description="Browser to use: chromium, firefox, or webkit"
    )


class InteractionResponse(BaseModel):
    status: str
    message: str
    details: Optional[Dict] = None
    screenshot_path: Optional[str] = None


class BrowserAction:
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


async def execute_browser_interaction(
    request: InteractionRequest,
) -> InteractionResponse:
    """Execute browser interactions based on natural language commands"""
    logger.info(f"Processing interaction request: {request.user_input}")
    command_results = []
    screenshot_path = None
    page_structure = None

    try:
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

            initial_commands = get_browser_commands(request.user_input)

            initial_nav_commands = [
                cmd for cmd in initial_commands if cmd.get("command_type") == "navigate"
            ]

            if initial_nav_commands:
                first_nav = initial_nav_commands[0]
                nav_result = await action_executor.execute(first_nav)
                command_results.append(nav_result)

                if nav_result["success"]:
                    from utils.browser_utils import extract_page_structure

                    page_structure = await extract_page_structure(page)
                    logger.info(
                        f"Extracted page structure with {len(page_structure.get('interactiveElements', {}).get('inputs', []))} inputs, "
                        + f"{len(page_structure.get('interactiveElements', {}).get('buttons', []))} buttons, "
                        + f"{len(page_structure.get('interactiveElements', {}).get('links', []))} links"
                    )

                    commands = get_browser_commands(request.user_input, page_structure)

                    commands = [
                        cmd
                        for cmd in commands
                        if not (
                            cmd.get("command_type") == "navigate"
                            and cmd.get("url") == first_nav.get("url")
                        )
                    ]
                else:
                    commands = [cmd for cmd in initial_commands if cmd != first_nav]
            else:
                commands = initial_commands

            for command in commands:
                if command["command_type"] == "navigate" and any(
                    r.get("command") == "navigate" for r in command_results
                ):
                    continue

                result = await action_executor.execute(command)
                command_results.append(result)

                if (
                    command["command_type"] == "navigate"
                    and result["success"]
                    and not page_structure
                ):
                    from utils.browser_utils import extract_page_structure

                    page_structure = await extract_page_structure(page)
                    logger.info("Extracted page structure after navigation")

                if not result["success"] and command["command_type"] not in [
                    "wait",
                    "screenshot",
                ]:
                    logger.warning(f"Command failed: {result['message']}")

                if result.get("screenshot_path"):
                    screenshot_path = result["screenshot_path"]

            if not screenshot_path:
                filename = f"final_screenshot_{int(time.time())}.png"
                path = f"/tmp/{filename}"
                await page.screenshot(path=path)
                screenshot_path = path

            await browser.close()

        success_count = sum(1 for result in command_results if result["success"])
        status = "success" if success_count == len(command_results) else "partial"
        if success_count == 0:
            status = "error"

        return InteractionResponse(
            status=status,
            message=f"Executed {success_count}/{len(command_results)} commands successfully",
            details={"results": command_results},
            screenshot_path=screenshot_path,
        )

    except Exception as e:
        logger.error(f"Error in browser interaction: {str(e)}")
        return InteractionResponse(
            status="error",
            message=f"Error during browser interaction: {str(e)}",
            details={"error": str(e)},
        )


class ExtractRequest(BaseModel):
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
    status: str
    message: str
    data: Optional[Union[Dict, List, str]] = None
    screenshot_path: Optional[str] = None


async def execute_data_extraction(
    request: ExtractRequest,
) -> ExtractResponse:
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


@router.post("/extract", response_model=ExtractResponse)
async def extract(request: ExtractRequest):
    """
    API endpoint to extract data from web pages

    Example input for extracting links:
    {
        "url": "https://example.com",
        "extraction_type": "links",
        "selector": "a.product-link",
        "timeout": 30,
        "headless": true
    }

    Example input for extracting table data:
    {
        "url": "https://example.com/table-page",
        "extraction_type": "table",
        "selector": "table.data-table",
        "timeout": 30
    }

    Example input for extracting specific elements:
    {
        "url": "https://example.com/products",
        "extraction_type": "elements",
        "selector": ".product-card",
        "attributes": ["innerText", "data-product-id", "data-price"],
        "timeout": 30
    }
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


@router.post("/interact", response_model=InteractionResponse)
async def interact(request: InteractionRequest, background_tasks: BackgroundTasks):
    """
    API endpoint to handle natural language browser interactions

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
