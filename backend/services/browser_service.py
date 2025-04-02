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

            elif action == "wait_for_captcha":
                message = command.get(
                    "message",
                    "Captcha detected. Please solve the captcha in the browser window.",
                )
                self.logger.info("Detected captcha, waiting for user resolution")

                # Take a screenshot to show the captcha
                filename = f"captcha_screenshot_{int(time.time())}.png"
                path = f"/tmp/{filename}"
                await self.page.screenshot(path=path)

                # Since BrowserAction doesn't have access to the Event object for signaling,
                # we can only return a result indicating captcha was detected
                result = {
                    "success": True,
                    "message": message,
                    "command": action,
                    "screenshot_path": path,
                    # This flag will be used by the caller to determine if user interaction is needed
                    "waiting_for_user": True,
                }

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
