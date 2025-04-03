import time
from typing import Dict

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from utils.logger import setup_logger
from utils.browser_utils import (
    BrowserAutomationError,
    NavigationError,
    ElementNotFoundError,
    TimeoutError,
    ExtractorError,
)


class BrowserAction:
    def __init__(self, page, timeout: int = 30):
        self.page = page
        self.timeout = timeout
        self.logger = setup_logger("browser_actions")

    async def execute(self, command: Dict) -> Dict:
        """Execute a browser command and return result with status"""
        action = command.get("command_type")
        result = {"success": False, "message": "", "command": action}
        # time.sleep(3)
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

                # First check if we need to navigate before searching
                current_url = self.page.url
                if current_url == "about:blank" or not current_url:
                    # Instead of failing immediately, provide a more helpful response
                    self.logger.warning(f"Cannot search on blank page.")
                    result["success"] = False
                    result["message"] = (
                        "Cannot search on an empty page. A navigation command is required first."
                    )
                    result["needs_navigation"] = True
                    return result

                # Make sure page is fully loaded
                try:
                    await self.page.wait_for_load_state(
                        "domcontentloaded", timeout=self.timeout * 1000
                    )
                    self.logger.info("Page DOM loaded, now checking for selector")
                except PlaywrightTimeoutError:
                    error_msg = "Timeout waiting for page to load before searching"
                    result["message"] = error_msg
                    raise TimeoutError(error_msg, {"query": query})

                # Now wait for selector with better error handling
                try:
                    self.logger.info(f"Looking for search selector: {selector}")
                    await self.page.wait_for_selector(
                        selector, timeout=self.timeout * 1000
                    )
                except PlaywrightTimeoutError:
                    # For debugging - print all available input elements
                    try:
                        # Using locators instead of evaluate to get input elements
                        all_inputs = self.page.locator("input")
                        count = await all_inputs.count()
                        input_elements = []
                        for i in range(count):
                            input_el = all_inputs.nth(i)
                            name = await input_el.get_attribute("name") or ""
                            input_id = await input_el.get_attribute("id") or ""
                            input_type = await input_el.get_attribute("type") or ""
                            placeholder = (
                                await input_el.get_attribute("placeholder") or ""
                            )
                            input_elements.append(
                                {
                                    "name": name,
                                    "id": input_id,
                                    "type": input_type,
                                    "placeholder": placeholder,
                                }
                            )

                        input_selectors = []
                        for inp in input_elements:
                            if inp.get("id"):
                                input_selectors.append(f"#{inp['id']}")
                            if inp.get("name"):
                                input_selectors.append(f"input[name='{inp['name']}']")

                        self.logger.error(f"Available input elements: {input_elements}")
                        self.logger.error(
                            f"Possible selectors to use: {input_selectors}"
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Error while trying to list available inputs: {str(e)}"
                        )

                    error_msg = f"Search element with selector '{selector}' not found on page: {current_url}"
                    result["message"] = error_msg
                    raise ElementNotFoundError(error_msg, {"selector": selector})

                # Fill and submit the search
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

            elif action == "wait_for_captcha":
                message = command.get(
                    "message",
                    "Captcha detected. Please solve the captcha in the browser window.",
                )
                self.logger.info("Detected captcha, waiting for user resolution")

                # Since BrowserAction doesn't have access to the Event object for signaling,
                # we can only return a result indicating captcha was detected
                result = {
                    "success": True,
                    "message": message,
                    "command": action,
                    # This flag will be used by the caller to determine if user interaction is needed
                    "waiting_for_user": True,
                }

            elif action == "wait_for_page_load":
                timeout = command.get(
                    "timeout", 10000
                )  # Default 10 seconds in milliseconds
                self.logger.info(
                    f"Waiting for page to load completely, timeout: {timeout}ms"
                )

                try:
                    # Wait for DOM content to be loaded
                    await self.page.wait_for_load_state(
                        "domcontentloaded", timeout=timeout
                    )
                    self.logger.info("Page DOM content loaded")

                    # Wait for network to be idle (no active connections for at least 500ms)
                    await self.page.wait_for_load_state("networkidle", timeout=timeout)
                    self.logger.info("Network idle, page fully loaded")

                    result["success"] = True
                    result["message"] = "Page fully loaded"
                except PlaywrightTimeoutError as e:
                    error_msg = f"Timeout waiting for page to load completely: {str(e)}"
                    self.logger.warning(error_msg)
                    # We don't want to fail the entire command chain if this times out
                    # Sometimes pages have long-running connections
                    result["success"] = True
                    result["message"] = "Page load wait timed out, but continuing"
                    result["warning"] = error_msg

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
                    # Using locators instead of evaluate
                    table_locator = self.page.locator(selector)

                    # Check if table exists
                    if await table_locator.count() == 0:
                        error_msg = f"No table found with selector: {selector}"
                        result["message"] = error_msg
                        raise ExtractorError(error_msg, {"selector": selector})

                    # Extract headers
                    headers_locator = table_locator.locator("th")
                    headers_count = await headers_locator.count()
                    headers = []
                    for i in range(headers_count):
                        header_text = await headers_locator.nth(i).text_content()
                        headers.append(header_text.strip())

                    # Extract rows (skip header row)
                    rows_locator = table_locator.locator("tr")
                    rows_count = await rows_locator.count()
                    rows = []

                    # Start from 1 to skip header row if headers exist
                    start_idx = 1 if headers_count > 0 else 0
                    for i in range(start_idx, rows_count):
                        row_locator = rows_locator.nth(i)
                        cells_locator = row_locator.locator("td")
                        cells_count = await cells_locator.count()

                        row_data = []
                        for j in range(cells_count):
                            cell_text = await cells_locator.nth(j).text_content()
                            row_data.append(cell_text.strip())

                        rows.append(row_data)

                    table_data = {"headers": headers, "rows": rows}

                    result["success"] = True
                    result["message"] = f"Extracted table data from {selector}"
                    result["data"] = table_data
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
                    # Using locators instead of evaluate
                    links_locator = self.page.locator(selector)
                    count = await links_locator.count()
                    links = []

                    for i in range(count):
                        link = links_locator.nth(i)
                        # Extract properties using get_attribute and text_content instead of evaluate
                        text = await link.text_content() or ""
                        url = await link.get_attribute("href") or ""
                        title = await link.get_attribute("title") or ""

                        links.append({"text": text.strip(), "url": url, "title": title})

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
                    # Using locators instead of evaluate
                    elements_locator = self.page.locator(selector)
                    count = await elements_locator.count()
                    elements_data = []

                    for i in range(count):
                        element = elements_locator.nth(i)
                        data = {}

                        for attr in attributes:
                            if attr == "innerText":
                                text = await element.text_content() or ""
                                data[attr] = text.strip()
                            elif attr == "innerHTML":
                                data[attr] = await element.inner_html()
                            else:
                                value = await element.get_attribute(attr) or ""
                                data[attr] = value

                        elements_data.append(data)

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
                    # Using locators instead of evaluate for JSON-LD extraction
                    json_ld_scripts = self.page.locator(
                        'script[type="application/ld+json"]'
                    )
                    json_ld_count = await json_ld_scripts.count()

                    if json_ld_count > 0:
                        # Try to parse the JSON-LD content
                        try:
                            json_ld_content = await json_ld_scripts.first.text_content()
                            if json_ld_content:
                                import json

                                json_data = {
                                    "source": "json-ld",
                                    "data": json.loads(json_ld_content),
                                }
                                result["success"] = True
                                result["message"] = f"Extracted structured JSON-LD data"
                                result["data"] = json_data["data"]
                                return result
                        except Exception as json_error:
                            self.logger.warning(
                                f"Error parsing JSON-LD: {str(json_error)}"
                            )

                    # If no JSON-LD or parsing failed, try meta tags
                    meta_locator = self.page.locator(
                        'meta[property^="og:"], meta[name^="twitter:"]'
                    )
                    meta_count = await meta_locator.count()

                    if meta_count > 0:
                        meta_data = {}
                        for i in range(meta_count):
                            meta_tag = meta_locator.nth(i)
                            property_name = (
                                await meta_tag.get_attribute("property")
                                or await meta_tag.get_attribute("name")
                                or ""
                            )
                            content = await meta_tag.get_attribute("content") or ""
                            if property_name:
                                meta_data[property_name] = content

                        if meta_data:
                            json_data = {"source": "meta-tags", "data": meta_data}
                            result["success"] = True
                            result["message"] = "Extracted structured meta tag data"
                            result["data"] = json_data["data"]
                            return result

                    # No structured data found
                    error_msg = "No structured JSON data found in page"
                    result["message"] = error_msg
                    raise ExtractorError(error_msg, {"page_url": self.page.url})
                except Exception as e:
                    error_msg = "Failed to extract JSON data from page"
                    result["message"] = error_msg
                    raise ExtractorError(error_msg, {"error": str(e)})

            elif action == "press":
                key = command.get("key")
                selector = command.get("selector", None)
                self.logger.info(
                    f"Pressing key {key}" + (f" on {selector}" if selector else "")
                )

                try:
                    if selector:
                        # Wait for the selector if specified
                        await self.page.wait_for_selector(
                            selector, timeout=self.timeout * 1000
                        )
                        # Press the key on the specified element
                        await self.page.press(selector, key)
                    else:
                        # Press the key on the active element or page
                        await self.page.keyboard.press(key)

                    result["success"] = True
                    result["message"] = f"Pressed {key}" + (
                        f" on {selector}" if selector else ""
                    )
                except PlaywrightTimeoutError:
                    if selector:
                        error_msg = f"Element with selector '{selector}' not found for key press"
                        result["message"] = error_msg
                        raise ElementNotFoundError(
                            error_msg, {"selector": selector, "key": key}
                        )
                    else:
                        error_msg = f"Failed to press {key}"
                        result["message"] = error_msg
                        raise BrowserAutomationError(error_msg, {"key": key})
                except Exception as e:
                    error_msg = f"Error pressing {key}: {str(e)}"
                    result["message"] = error_msg
                    raise BrowserAutomationError(
                        error_msg, {"key": key, "error": str(e)}
                    )

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
