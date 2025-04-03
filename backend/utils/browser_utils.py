from typing import Dict, List, Optional
from fastapi import HTTPException, status


class BrowserAutomationError(Exception):
    """Base exception for browser automation errors"""

    def __init__(self, message: str, details: Optional[Dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class NavigationError(BrowserAutomationError):
    """Raised when navigation to a URL fails"""

    pass


class ElementNotFoundError(BrowserAutomationError):
    """Raised when an element cannot be found with the given selector"""

    pass


class TimeoutError(BrowserAutomationError):
    """Raised when an operation times out"""

    pass


class ExtractorError(BrowserAutomationError):
    """Raised when data extraction fails"""

    pass


class CommandParsingError(BrowserAutomationError):
    """Raised when parsing natural language to commands fails"""

    pass


def handle_browser_error(error: Exception) -> HTTPException:
    """Convert browser automation errors into appropriate HTTP exceptions"""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = {"message": str(error)}

    if isinstance(error, NavigationError):
        status_code = status.HTTP_400_BAD_REQUEST
        detail["error_type"] = "navigation_error"

    elif isinstance(error, ElementNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
        detail["error_type"] = "element_not_found"

    elif isinstance(error, TimeoutError):
        status_code = status.HTTP_408_REQUEST_TIMEOUT
        detail["error_type"] = "timeout"

    elif isinstance(error, ExtractorError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        detail["error_type"] = "extraction_error"

    elif isinstance(error, CommandParsingError):
        status_code = status.HTTP_400_BAD_REQUEST
        detail["error_type"] = "command_parsing_error"

    # Add error details if available
    if hasattr(error, "details") and error.details:
        detail["details"] = error.details

    return HTTPException(status_code=status_code, detail=detail)


def validate_selectors(selectors: List[str]) -> List[str]:
    """Validate and fix common CSS selector issues"""
    validated = []

    for selector in selectors:
        # Add basic validation/correction logic
        selector = selector.strip()

        # Fix missing quotes in attribute selectors
        if "[" in selector and "]" in selector and "=" in selector:
            parts = selector.split("[")
            for i in range(1, len(parts)):
                if "]" in parts[i]:
                    attr_part = parts[i].split("]")[0]
                    if "=" in attr_part:
                        key, value = attr_part.split("=", 1)
                        # If value is not quoted and contains non-alphanumeric chars, add quotes
                        if not (value.startswith('"') or value.startswith("'")):
                            if any(c for c in value if not (c.isalnum() or c == "-")):
                                value = f'"{value}"'
                                parts[i] = f"{key}={value}]{parts[i].split(']', 1)[1]}"

            selector = "[".join(parts)

        validated.append(selector)

    return validated


# async def extract_page_structure(page):
#     """
#     Extracts the structure of the current page including important interactive elements.
#     This helps the LLM understand what elements are actually available for interaction.
#     Uses Playwright's Locator API for better maintainability.
#     """
#     # Extract basic page info using locators
#     url = page.url
#     title = await page.title()

#     # Check for basic features using a single evaluation for better performance
#     basic_features = await page.evaluate("""() => {
#         const doc = document;
#         return {
#             hasCaptcha: Boolean(
#                 doc.body.textContent.match(/captcha|recaptcha|cloudflare|i'm not a robot/i)
#             ),
#             hasLoginForm: Boolean(
#                 doc.querySelector('input[type="password"]') ||
#                 doc.body.textContent.match(/sign in|log in/i)
#             ),
#             hasNavigation: Boolean(
#                 doc.querySelector('nav, [role="navigation"]')
#             ),
#             hasSearchBox: Boolean(
#                 doc.querySelector('input[type="search"], input[name*="search"], input[placeholder*="search" i], input[aria-label*="search" i]')
#             )
#         };
#     }""")

#     # Initialize result structure
#     result = {
#         "url": url,
#         "title": title,
#         "pageFeatures": basic_features,
#     }

#     # Extract headings using a single evaluation
#     headings_data = await page.evaluate("""() => {
#         const headings = {};
#         const h1s = Array.from(document.querySelectorAll('h1')).slice(0, 3).map(h => h.textContent.trim()).filter(Boolean);
#         const h2s = Array.from(document.querySelectorAll('h2')).slice(0, 5).map(h => h.textContent.trim()).filter(Boolean);
        
#         if (h1s.length) headings.h1 = h1s;
#         if (h2s.length) headings.h2 = h2s;
        
#         return headings;
#     }""")

#     if headings_data:
#         result["headings"] = headings_data

#     # Extract interactive elements
#     interactive_elements = {}

#     # Efficiently extract all input fields in one pass
#     if basic_features["hasSearchBox"]:
#         search_inputs = await page.evaluate("""() => {
#             const selectors = [
#                 'input[name="q"]',
#                 'input[type="search"]',
#                 'input[placeholder*="search" i]',
#                 'input[aria-label*="search" i]',
#                 '.search-box input, .searchbox input',
#                 '#search input, #searchbox input',
#                 'form[role="search"] input',
#                 'input[name*="search" i]'
#             ];
            
#             for (const selector of selectors) {
#                 const el = document.querySelector(selector);
#                 if (el && el.offsetParent !== null) {
#                     const id = el.id || "";
#                     const name = el.name || "";
#                     const placeholder = el.placeholder || "";
                    
#                     let bestSelector = selector;
#                     if (id) bestSelector = `#${id}`;
#                     else if (name) bestSelector = `input[name="${name}"]`;
                    
#                     return [{
#                         selector: bestSelector,
#                         type: "search",
#                         name: name,
#                         id: id,
#                         placeholder: placeholder,
#                         isSearch: true
#                     }];
#                 }
#             }
#             return [];
#         }""")

#         if search_inputs:
#             interactive_elements["searchInputs"] = search_inputs

#     # Extract the most important interactive elements efficiently using a single call
#     # This covers: inputs, buttons, links, selects, forms, checkboxes and images
#     const_elements = await page.evaluate("""() => {
#         // Helper function to create selector based on element properties
#         const createSelector = (el, prefix = "") => {
#             if (el.id) return `#${el.id}`;
#             if (el.dataset.testid) return `[data-testid="${el.dataset.testid}"]`;
#             if (el.className) {
#                 const classes = el.className.split(" ");
#                 if (classes.length && classes[0]) return `.${classes[0]}`;
#             }
#             return null;
#         };
        
#         // Helper function to check visibility
#         const isVisible = (el) => {
#             return el.offsetParent !== null;
#         };
        
#         const elements = {
#             inputs: [],
#             buttons: [],
#             links: [],
#             selects: [],
#             forms: [],
#             checkboxes: [],
#             images: []
#         };
        
#         // Extract inputs
#         const inputs = document.querySelectorAll('input:not([type="hidden"]):not([disabled]), textarea:not([disabled])');
#         for (let i = 0; i < inputs.length; i++) {
#             const input = inputs[i];
#             if (!isVisible(input)) continue;
            
#             const type = input.type || "text";
#             const name = input.name || "";
#             const id = input.id || "";
#             const placeholder = input.placeholder || "";
#             const className = input.className || "";
#             const isRequired = input.required;
            
#             // Get label text if possible
#             let labelText = "";
#             if (id) {
#                 const label = document.querySelector(`label[for="${id}"]`);
#                 if (label) labelText = label.textContent.trim();
#             }
            
#             // Create selector
#             let selector = createSelector(input, "input");
#             if (!selector) {
#                 if (name) selector = `input[name="${name}"]`;
#                 else selector = `input[type="${type}"]`;
#             }
            
#             elements.inputs.push({
#                 type,
#                 name,
#                 id,
#                 placeholder,
#                 classes: className,
#                 labelText,
#                 selector,
#                 isRequired
#             });
#         }
        
#         // Extract buttons
#         const buttons = document.querySelectorAll('button:not([disabled]), [type="button"]:not([disabled]), [type="submit"]:not([disabled]), [role="button"]:not([disabled])');
#         for (let i = 0; i < buttons.length; i++) {
#             const button = buttons[i];
#             if (!isVisible(button)) continue;
            
#             const text = button.textContent?.trim() || "";
#             const id = button.id || "";
#             const type = button.type || "";
#             const className = button.className || "";
#             const dataTestid = button.dataset.testid || "";
            
#             // Create selector
#             let selector = createSelector(button);
#             if (!selector) {
#                 if (text) {
#                     selector = `button:has-text("${text.substring(0, 30)}")`;
#                 } else {
#                     selector = "button";
#                 }
#             }
            
#             elements.buttons.push({
#                 text: text.substring(0, 50),
#                 id,
#                 classes: className,
#                 dataTestId: dataTestid,
#                 selector,
#                 isSubmit: type === "submit"
#             });
#         }
        
#         // Extract links (up to 30)
#         const links = document.querySelectorAll("a:not([disabled])");
#         for (let i = 0; i < Math.min(links.length, 30); i++) {
#             const link = links[i];
#             if (!isVisible(link)) continue;
            
#             const text = link.textContent?.trim() || "";
#             if (!text) continue;
            
#             const href = link.href || "";
#             const id = link.id || "";
#             const className = link.className || "";
#             const dataTestid = link.dataset.testid || "";
            
#             let selector = createSelector(link);
            
#             if (!selector) selector = "a";
            
#             elements.links.push({
#                 text: text.substring(0, 50),
#                 href,
#                 id,
#                 classes: className,
#                 dataTestId: dataTestid,
#                 selector,
#                 index: i,
#                 indexSelector: `a:nth-of-type(${i+1})`
#             });
#         }
        
#         // Extract selects
#         const selects = document.querySelectorAll("select:not([disabled])");
#         for (let i = 0; i < selects.length; i++) {
#             const select = selects[i];
#             if (!isVisible(select)) continue;
            
#             const name = select.name || "";
#             const id = select.id || "";
#             const className = select.className || "";
            
#             // Get label text
#             let labelText = "";
#             if (id) {
#                 const label = document.querySelector(`label[for="${id}"]`);
#                 if (label) labelText = label.textContent.trim();
#             }
            
#             // Get options (limited to 10)
#             const optionsElements = select.querySelectorAll("option");
#             const options = Array.from(optionsElements).slice(0, 10).map(opt => ({
#                 text: opt.textContent.trim(),
#                 value: opt.value || "",
#                 selected: opt.selected
#             }));
            
#             // Create selector
#             let selector = createSelector(select);
#             if (!selector) {
#                 if (name) selector = `select[name="${name}"]`;
#                 else selector = "select";
#             }
            
#             elements.selects.push({
#                 name,
#                 id,
#                 classes: className,
#                 labelText,
#                 options,
#                 selector
#             });
#         }
        
#         // Extract forms
#         const forms = document.querySelectorAll("form");
#         for (let i = 0; i < forms.length; i++) {
#             const form = forms[i];
#             const id = form.id || "";
#             const action = form.action || "";
#             const method = form.method || "get";
#             const className = form.className || "";
#             const dataTestid = form.dataset.testid || "";
            
#             // Find submit button
#             const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
#             let submitSelector = null;
#             let submitText = "";
            
#             if (submitButton) {
#                 const submitId = submitButton.id || "";
#                 const submitClass = submitButton.className || "";
#                 submitText = submitButton.textContent?.trim() || submitButton.value || "";
                
#                 if (submitId) {
#                     submitSelector = `#${submitId}`;
#                 } else if (submitClass) {
#                     const submitClassNames = submitClass.split(" ");
#                     if (submitClassNames.length && submitClassNames[0]) {
#                         const tag = submitButton.tagName.toLowerCase();
#                         submitSelector = `${tag}.${submitClassNames[0]}`;
#                     }
#                 } else if (submitText) {
#                     submitSelector = `button:has-text("${submitText.substring(0, 30)}")`;
#                 } else {
#                     submitSelector = 'button[type="submit"], input[type="submit"]';
#                 }
#             }
            
#             // Create selector
#             let selector = createSelector(form);
#             if (!selector) {
#                 selector = "form";
#             }
            
#             elements.forms.push({
#                 id,
#                 classes: className,
#                 dataTestId: dataTestid,
#                 action,
#                 method,
#                 selector,
#                 submitSelector,
#                 submitText: submitText.trim()
#             });
#         }
        
#         // Extract checkboxes/radio buttons
#         const checkboxes = document.querySelectorAll('input[type="checkbox"]:not([disabled]), input[type="radio"]:not([disabled])');
#         for (let i = 0; i < checkboxes.length; i++) {
#             const checkbox = checkboxes[i];
#             if (!isVisible(checkbox)) continue;
            
#             const type = checkbox.type || "";
#             const name = checkbox.name || "";
#             const id = checkbox.id || "";
#             const className = checkbox.className || "";
#             const isChecked = checkbox.checked;
            
#             // Get label text
#             let labelText = "";
#             if (id) {
#                 const label = document.querySelector(`label[for="${id}"]`);
#                 if (label) labelText = label.textContent.trim();
#             }
            
#             // Create selector
#             let selector = createSelector(checkbox);
#             if (!selector) {
#                 if (name) selector = `input[name="${name}"][type="${type}"]`;
#                 else selector = `input[type="${type}"]`;
#             }
            
#             elements.checkboxes.push({
#                 type,
#                 name,
#                 id,
#                 classes: className,
#                 labelText,
#                 checked: isChecked,
#                 selector
#             });
#         }
        
#         // Extract images (up to 20)
#         const images = document.querySelectorAll("img");
#         for (let i = 0; i < Math.min(images.length, 20); i++) {
#             const img = images[i];
#             if (!isVisible(img)) continue;
            
#             const src = img.src || "";
#             const alt = img.alt || "";
#             const id = img.id || "";
#             const className = img.className || "";
#             const dataTestid = img.dataset.testid || "";
            
#             // Create selector
#             let selector = createSelector(img, "img");
#             if (!selector) {
#                 if (alt) selector = `img[alt="${alt}"]`;
#                 else selector = `img:nth-child(${i+1})`;
#             }
            
#             elements.images.push({
#                 src,
#                 alt,
#                 id,
#                 classes: className,
#                 dataTestId: dataTestid,
#                 selector,
#                 positionSelector: `img:nth-child(${i+1})`,
#                 containerPositionSelector: `img:nth-of-type(${i+1})`
#             });
#         }
        
#         return elements;
#     }""")

#     # Add extracted elements to interactive_elements object
#     for key, value in const_elements.items():
#         if value:
#             interactive_elements[key] = value

#     if interactive_elements:
#         result["interactiveElements"] = interactive_elements

#     return result

import asyncio


async def extract_page_structure(page):
    """
    Optimized extraction of page structure using bulk evaluation,
    parallel asynchronous calls, and DRY logic for similar element types.
    """
    # Basic page info and features (using parallel calls)
    url = page.url
    title = await page.title()
    (
        captcha_count,
        pwd_count,
        sign_in_count,
        nav_count,
        search_count,
    ) = await asyncio.gather(
        page.locator("text=/captcha|recaptcha|cloudflare|i'm not a robot/i").count(),
        page.locator('input[type="password"]').count(),
        page.locator("text=/sign in|log in/i").count(),
        page.locator('nav, [role="navigation"]').count(),
        page.locator(
            'input[type="search"], input[name*="search"], input[placeholder*="search" i], input[aria-label*="search" i]'
        ).count(),
    )

    result = {
        "url": url,
        "title": title,
        "pageFeatures": {
            "hasCaptcha": captcha_count > 0,
            "hasLoginForm": (pwd_count + sign_in_count) > 0,
            "hasNavigation": nav_count > 0,
            "hasSearchBox": search_count > 0,
        },
    }

    # Extract headings (h1 and h2)
    headings = await page.evaluate("""() => {
        const cleanTexts = (nodes, limit) => 
            Array.from(nodes)
                .slice(0, limit)
                .map(el => el.textContent.trim())
                .filter(Boolean);
        return {
            h1: cleanTexts(document.querySelectorAll("h1"), 3),
            h2: cleanTexts(document.querySelectorAll("h2"), 5)
        };
    }""")
    if headings.get("h1") or headings.get("h2"):
        result["headings"] = headings

    interactiveElements = {}

    # Helper: check if an element is visible
    visibility_check = (
        "el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)"
    )

    # Extract inputs (inputs and textareas)
    inputs = await page.evaluate(f"""() => {{
        const isVisible = {visibility_check};
        return Array.from(document.querySelectorAll('input:not([type="hidden"]):not([disabled]), textarea:not([disabled])'))
            .filter(isVisible)
            .map(el => {{
                const type = el.getAttribute("type") || "text";
                const name = el.getAttribute("name") || "";
                const id = el.getAttribute("id") || "";
                const placeholder = el.getAttribute("placeholder") || "";
                const classes = el.getAttribute("class") || "";
                const isRequired = el.hasAttribute("required");
                let labelText = "";
                if (id) {{
                    const label = document.querySelector(`label[for="${{id}}"]`);
                    if (label) labelText = label.textContent.trim();
                }}
                let selector = id ? `#${{id}}` :
                              classes ? `input.${{classes.split(" ")[0]}}` :
                              name ? `input[name="${{name}}"]` :
                              `input[type="${{type}}"]`;
                return {{
                    type, name, id, placeholder, classes, 
                    labelText, selector, isRequired
                }};
            }});
    }}""")
    if inputs:
        interactiveElements["inputs"] = inputs

    # Extract buttons
    buttons = await page.evaluate(f"""() => {{
        const isVisible = {visibility_check};
        return Array.from(document.querySelectorAll(
            'button:not([disabled]), [type="button"]:not([disabled]), [type="submit"]:not([disabled]), [role="button"]:not([disabled])'
        ))
        .filter(isVisible)
        .map(el => {{
            const text = (el.textContent || "").trim().slice(0,50);
            const id = el.getAttribute("id") || "";
            const type = el.getAttribute("type") || "";
            const classes = el.getAttribute("class") || "";
            const dataTestId = el.getAttribute("data-testid") || "";
            let selector = "";
            if (id) {{
                selector = `#${{id}}`;
            }} else if (dataTestId) {{
                selector = `[data-testid="${{dataTestId}}"]`;
            }} else if (classes) {{
                const classNames = classes.split(" ");
                if (classNames.length) {{
                    const tag = el.tagName.toLowerCase() === "button" ? "button" : "[role='button']";
                    selector = `${{tag}}.${{classNames[0]}}`;
                }}
            }} else if (text) {{
                selector = `button:has-text("${{text.slice(0,30)}}")`;
            }} else {{
                selector = "button";
            }}
            return {{
                text, id, classes, dataTestId, selector,
                isSubmit: type === "submit"
            }};
        }});
    }}""")
    if buttons:
        interactiveElements["buttons"] = buttons

    # Extract links
    links = await page.evaluate(f"""() => {{
        const isVisible = {visibility_check};
        return Array.from(document.querySelectorAll("a:not([disabled])"))
            .filter(isVisible)
            .map((el, index) => {{
                const text = (el.textContent || "").trim();
                if (!text) return null;
                const href = el.getAttribute("href") || "";
                const id = el.getAttribute("id") || "";
                const classes = el.getAttribute("class") || "";
                const dataTestId = el.getAttribute("data-testid") || "";
                let selector = "";
                if (id) {{
                    selector = `#${{id}}`;
                }} else if (dataTestId) {{
                    selector = `[data-testid="${{dataTestId}}"]`;
                }} else if (classes) {{
                    const classNames = classes.split(" ");
                    if (classNames.length) {{
                        selector = `.${{classNames[0]}}`;
                    }}
                }} else {{
                    selector = `a:has-text("${{text.slice(0,30)}}")`;
                }}
                return {{
                    text: text.slice(0,50),
                    href, id, classes, dataTestId, selector,
                    positionSelector: `a:nth-child(${{index + 1}})`
                }};
            }})
            .filter(Boolean);
    }}""")
    if links:
        interactiveElements["links"] = links

    # Extract select elements
    selects = await page.evaluate(f"""() => {{
        const isVisible = {visibility_check};
        return Array.from(document.querySelectorAll("select:not([disabled])"))
            .filter(isVisible)
            .map(el => {{
                const name = el.getAttribute("name") || "";
                const id = el.getAttribute("id") || "";
                const classes = el.getAttribute("class") || "";
                let labelText = "";
                if (id) {{
                    const label = document.querySelector(`label[for="${{id}}"]`);
                    if (label) labelText = label.textContent.trim();
                }}
                const options = Array.from(el.querySelectorAll("option"))
                    .slice(0,10)
                    .map(opt => {{
                        return {{
                            text: (opt.textContent || "").trim(),
                            value: opt.getAttribute("value") || "",
                            selected: opt.hasAttribute("selected")
                        }};
                    }});
                let selector = id ? `#${{id}}` :
                              classes ? `select.${{classes.split(" ")[0]}}` :
                              name ? `select[name="${{name}}"]` :
                              "select";
                return {{
                    name, id, classes, labelText, options, selector
                }};
            }});
    }}""")
    if selects:
        interactiveElements["selects"] = selects

    # Extract forms and their submit buttons
    forms = await page.evaluate(f"""() => {{
        const isVisible = {visibility_check};
        return Array.from(document.querySelectorAll("form"))
            .filter(isVisible)
            .map(el => {{
                const id = el.getAttribute("id") || "";
                const action = el.getAttribute("action") || "";
                const method = el.getAttribute("method") || "get";
                const classes = el.getAttribute("class") || "";
                const dataTestId = el.getAttribute("data-testid") || "";
                let submitButton = el.querySelector('button[type="submit"], input[type="submit"]');
                let submitSelector = "";
                let submitText = "";
                if (submitButton) {{
                    const submitId = submitButton.getAttribute("id") || "";
                    const submitClass = submitButton.getAttribute("class") || "";
                    submitText = (submitButton.textContent || submitButton.getAttribute("value") || "").trim();
                    if (submitId) {{
                        submitSelector = `#${{submitId}}`;
                    }} else if (submitClass) {{
                        submitSelector = `${{submitButton.tagName.toLowerCase()}}.${{submitClass.split(" ")[0]}}`;
                    }} else if (submitText) {{
                        submitSelector = `button:has-text("${{submitText.slice(0,30)}}")`;
                    }} else {{
                        submitSelector = 'button[type="submit"], input[type="submit"]';
                    }}
                }}
                let selector = id ? `#${{id}}` :
                              dataTestId ? `form[data-testid="${{dataTestId}}"]` :
                              classes ? `form.${{classes.split(" ")[0]}}` :
                              "form";
                return {{
                    id, classes, dataTestId, action, method, selector,
                    submitSelector, submitText
                }};
            }});
    }}""")
    if forms:
        interactiveElements["forms"] = forms

    # Extract checkboxes and radio buttons
    checkboxes = await page.evaluate(f"""() => {{
        const isVisible = {visibility_check};
        return Array.from(document.querySelectorAll('input[type="checkbox"]:not([disabled]), input[type="radio"]:not([disabled])'))
            .filter(isVisible)
            .map(el => {{
                const type = el.getAttribute("type") || "";
                const name = el.getAttribute("name") || "";
                const id = el.getAttribute("id") || "";
                const classes = el.getAttribute("class") || "";
                const checked = el.checked;
                let labelText = "";
                if (id) {{
                    const label = document.querySelector(`label[for="${{id}}"]`);
                    if (label) labelText = label.textContent.trim();
                }}
                let selector = id ? `#${{id}}` :
                              classes ? `input[type="${{type}}"].${{classes.split(" ")[0]}}` :
                              name ? `input[name="${{name}}"][type="${{type}}"]` :
                              `input[type="${{type}}"]`;
                return {{
                    type, name, id, classes, labelText, checked, selector
                }};
            }});
    }}""")
    if checkboxes:
        interactiveElements["checkboxes"] = checkboxes

    # Extract images (limit to 20)
    images = await page.evaluate(f"""() => {{
        const isVisible = {visibility_check};
        return Array.from(document.querySelectorAll("img"))
            .filter(isVisible)
            .slice(0,20)
            .map((el, index) => {{
                const src = el.getAttribute("src") || "";
                const alt = el.getAttribute("alt") || "";
                const id = el.getAttribute("id") || "";
                const classes = el.getAttribute("class") || "";
                const dataTestId = el.getAttribute("data-testid") || "";
                let selector = "";
                if (id) {{
                    selector = `img#${{id}}`;
                }} else if (dataTestId) {{
                    selector = `img[data-testid="${{dataTestId}}"]`;
                }} else if (classes) {{
                    selector = `img.${{classes.split(" ")[0]}}`;
                }} else {{
                    selector = alt ? `img[alt="${{alt}}"]` : `img:nth-child(${{index+1}})`;
                }}
                return {{
                    src, alt, id, classes, dataTestId, selector,
                    positionSelector: `img:nth-child(${{index+1}})`,
                    containerPositionSelector: `img:nth-of-type(${{index+1}})`
                }};
            }});
    }}""")
    if images:
        interactiveElements["images"] = images

    if interactiveElements:
        result["interactiveElements"] = interactiveElements

    return result
