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


async def extract_page_structure(page):
    """
    Extracts the structure of the current page including important interactive elements.
    This helps the LLM understand what elements are actually available for interaction.
    Uses Playwright's Locator API instead of evaluate for better maintainability.
    """
    # Extract basic page info using locators
    url = page.url
    title = await page.title()

    # Check for basic features
    has_captcha = (
        await page.locator(
            "text=/captcha|recaptcha|cloudflare|i'm not a robot/i"
        ).count()
        > 0
    )
    has_login_form = (
        await page.locator('input[type="password"]').count() > 0
        or await page.locator("text=/sign in|log in/i").count() > 0
    )
    has_navigation = await page.locator('nav, [role="navigation"]').count() > 0
    has_search_box = (
        await page.locator(
            'input[type="search"], input[name*="search"], input[placeholder*="search" i], input[aria-label*="search" i]'
        ).count()
        > 0
    )

    # Use Playwright's Locator API for all element extraction
    result = {
        "url": url,
        "title": title,
        "pageFeatures": {
            "hasCaptcha": has_captcha,
            "hasLoginForm": has_login_form,
            "hasNavigation": has_navigation,
            "hasSearchBox": has_search_box,
        },
    }

    # Extract headings (limit to 3 for h1, 5 for h2 to save tokens)
    headings = {}
    h1_locator = page.locator("h1")
    h1_count = min(await h1_locator.count(), 3)
    if h1_count > 0:
        h1s = []
        for i in range(h1_count):
            text = await h1_locator.nth(i).text_content()
            if text.strip():
                h1s.append(text.strip())
        if h1s:
            headings["h1"] = h1s

    h2_locator = page.locator("h2")
    h2_count = min(await h2_locator.count(), 5)
    if h2_count > 0:
        h2s = []
        for i in range(h2_count):
            text = await h2_locator.nth(i).text_content()
            if text.strip():
                h2s.append(text.strip())
        if h2s:
            headings["h2"] = h2s

    if headings:
        result["headings"] = headings

    # Extract main content text (truncated)
    main_content_locator = page.locator(
        'main, [role="main"], #main, .main, #content, .content, article'
    ).first
    if await main_content_locator.count() > 0:
        main_text = await main_content_locator.text_content()
        if main_text:
            main_text = main_text.strip()[:300]  # Limit to 300 characters
            result["mainText"] = main_text
    else:
        # If no main content element found, use body (with limited content)
        body_text = await page.locator("body").text_content()
        if body_text:
            body_text = body_text.strip()[:200]  # Even more limited for body
            result["mainText"] = body_text

    # Extract interactive elements
    interactive_elements = {}

    # Extract inputs
    inputs_locator = page.locator(
        'input:not([type="hidden"]):not([disabled]), textarea:not([disabled])'
    )
    input_count = await inputs_locator.count()
    if input_count > 0:
        inputs = []
        for i in range(input_count):
            input_el = inputs_locator.nth(i)

            # Skip if not visible (similar to isElementVisible in JS)
            if not await input_el.is_visible():
                continue

            # Get basic properties
            input_type = await input_el.get_attribute("type") or "text"
            input_name = await input_el.get_attribute("name") or ""
            input_id = await input_el.get_attribute("id") or ""
            placeholder = await input_el.get_attribute("placeholder") or ""
            class_attr = await input_el.get_attribute("class") or ""

            # Check if required
            is_required = await input_el.get_attribute("required") == "true"

            # Get label text (more complex)
            label_text = ""
            if input_id:
                label_locator = page.locator(f'label[for="{input_id}"]')
                if await label_locator.count() > 0:
                    label_text = await label_locator.text_content() or ""

            # Create selector (with simplified logic)
            selector = None
            if input_id:
                selector = f"#{input_id}"
            elif class_attr:
                class_names = class_attr.split()
                if class_names:
                    selector = f"input.{class_names[0]}"
            elif input_name:
                selector = f'input[name="{input_name}"]'
            else:
                selector = f'input[type="{input_type}"]'

            inputs.append(
                {
                    "type": input_type,
                    "name": input_name,
                    "id": input_id,
                    "placeholder": placeholder,
                    "classes": class_attr,
                    "labelText": label_text.strip(),
                    "selector": selector,
                    "isRequired": is_required,
                }
            )

        if inputs:
            interactive_elements["inputs"] = inputs

    # Extract buttons
    buttons_locator = page.locator(
        'button:not([disabled]), [type="button"]:not([disabled]), [type="submit"]:not([disabled]), [role="button"]:not([disabled])'
    )
    button_count = await buttons_locator.count()
    if button_count > 0:
        buttons = []
        for i in range(button_count):
            button = buttons_locator.nth(i)

            # Skip if not visible
            if not await button.is_visible():
                continue

            button_text = await button.text_content() or ""
            button_id = await button.get_attribute("id") or ""
            button_type = await button.get_attribute("type") or ""
            class_attr = await button.get_attribute("class") or ""
            data_testid = await button.get_attribute("data-testid") or ""

            # Create selector
            selector = None
            if button_id:
                selector = f"#{button_id}"
            elif data_testid:
                selector = f'[data-testid="{data_testid}"]'
            elif class_attr:
                class_names = class_attr.split()
                if class_names:
                    tag = "button" if await button.evaluate("el => el.tagName.toLowerCase()") == "button" else "[role='button']"
                    selector = f"{tag}.{class_names[0]}"
            elif button_text.strip():
                selector = f'button:has-text("{button_text.strip()[:30]}")'
            else:
                selector = "button"

            buttons.append(
                {
                    "text": button_text.strip()[:50],
                    "id": button_id,
                    "classes": class_attr,
                    "dataTestId": data_testid,
                    "selector": selector,
                    "isSubmit": button_type == "submit",
                }
            )

        if buttons:
            interactive_elements["buttons"] = buttons

    # Extract links
    links_locator = page.locator("a:not([disabled])")
    link_count = await links_locator.count()
    if link_count > 0:
        links = []
        for i in range(link_count):
            link = links_locator.nth(i)

            # Skip if not visible
            if not await link.is_visible():
                continue

            link_text = await link.text_content() or ""
            if not link_text.strip():
                continue  # Skip links without text

            link_href = await link.get_attribute("href") or ""
            link_id = await link.get_attribute("id") or ""
            class_attr = await link.get_attribute("class") or ""
            data_testid = await link.get_attribute("data-testid") or ""

            # Create selector prioritizing ID and class
            selector = None
            if link_id:
                selector = f"a#{link_id}"
            elif data_testid:
                selector = f'a[data-testid="{data_testid}"]'
            elif class_attr:
                class_names = class_attr.split()
                if class_names:
                    selector = f"a.{class_names[0]}"
            else:
                # Only use text selector as a last resort
                selector = f'a:has-text("{link_text.strip()[:30]}")'
                # list_selector = f'a:nth-child({i+1})'

            links.append(
                {
                    "text": link_text.strip()[:50],
                    "href": link_href,
                    "id": link_id,
                    "classes": class_attr,
                    "dataTestId": data_testid,
                    "selector": selector,
                    "positionSelector": f"a:nth-child({i+1})"
                }
            )

        if links:
            interactive_elements["links"] = links

    # Extract select elements
    selects_locator = page.locator("select:not([disabled])")
    select_count = await selects_locator.count()
    if select_count > 0:
        selects = []
        for i in range(select_count):
            select = selects_locator.nth(i)

            # Skip if not visible
            if not await select.is_visible():
                continue

            select_name = await select.get_attribute("name") or ""
            select_id = await select.get_attribute("id") or ""
            class_attr = await select.get_attribute("class") or ""

            # Get label text
            label_text = ""
            if select_id:
                label_locator = page.locator(f'label[for="{select_id}"]')
                if await label_locator.count() > 0:
                    label_text = await label_locator.text_content() or ""

            # Get options (limited to first 10)
            options_locator = select.locator("option")
            option_count = min(await options_locator.count(), 10)
            options = []

            for j in range(option_count):
                option = options_locator.nth(j)
                option_text = await option.text_content() or ""
                option_value = await option.get_attribute("value") or ""
                is_selected = await option.get_attribute("selected") is not None

                options.append(
                    {
                        "text": option_text.strip(),
                        "value": option_value,
                        "selected": is_selected,
                    }
                )

            # Create selector
            selector = None
            if select_id:
                selector = f"#{select_id}"
            elif class_attr:
                class_names = class_attr.split()
                if class_names:
                    selector = f"select.{class_names[0]}"
            elif select_name:
                selector = f'select[name="{select_name}"]'
            else:
                selector = "select"

            selects.append(
                {
                    "name": select_name,
                    "id": select_id,
                    "classes": class_attr,
                    "labelText": label_text.strip(),
                    "options": options,
                    "selector": selector,
                }
            )

        if selects:
            interactive_elements["selects"] = selects

    # Extract form elements
    forms_locator = page.locator("form")
    form_count = await forms_locator.count()
    if form_count > 0:
        forms = []
        for i in range(form_count):
            form = forms_locator.nth(i)
            form_id = await form.get_attribute("id") or ""
            form_action = await form.get_attribute("action") or ""
            form_method = await form.get_attribute("method") or "get"
            class_attr = await form.get_attribute("class") or ""
            data_testid = await form.get_attribute("data-testid") or ""

            # Find submit button
            submit_button = form.locator(
                'button[type="submit"], input[type="submit"]'
            ).first
            submit_selector = None
            submit_text = ""

            if await submit_button.count() > 0:
                submit_id = await submit_button.get_attribute("id") or ""
                submit_class = await submit_button.get_attribute("class") or ""
                submit_text = (
                    await submit_button.text_content()
                    or await submit_button.get_attribute("value")
                    or ""
                )

                if submit_id:
                    submit_selector = f"#{submit_id}"
                elif submit_class:
                    submit_class_names = submit_class.split()
                    if submit_class_names:
                        submit_tag = await submit_button.evaluate("el => el.tagName.toLowerCase()")
                        submit_selector = f"{submit_tag}.{submit_class_names[0]}"
                elif submit_text.strip():
                    submit_selector = f'button:has-text("{submit_text.strip()[:30]}")'
                else:
                    submit_selector = 'button[type="submit"], input[type="submit"]'

            # Create selector
            selector = None
            if form_id:
                selector = f"#{form_id}"
            elif data_testid:
                selector = f'form[data-testid="{data_testid}"]'
            elif class_attr:
                class_names = class_attr.split()
                if class_names:
                    selector = f"form.{class_names[0]}"
            else:
                selector = "form"

            forms.append(
                {
                    "id": form_id,
                    "classes": class_attr,
                    "dataTestId": data_testid,
                    "action": form_action,
                    "method": form_method,
                    "selector": selector,
                    "submitSelector": submit_selector,
                    "submitText": submit_text.strip(),
                }
            )

        if forms:
            interactive_elements["forms"] = forms

    # Extract checkboxes and radio buttons
    checkboxes_locator = page.locator(
        'input[type="checkbox"]:not([disabled]), input[type="radio"]:not([disabled])'
    )
    checkbox_count = await checkboxes_locator.count()
    if checkbox_count > 0:
        checkboxes = []
        for i in range(checkbox_count):
            checkbox = checkboxes_locator.nth(i)

            # Skip if not visible
            if not await checkbox.is_visible():
                continue

            checkbox_type = await checkbox.get_attribute("type") or ""
            checkbox_name = await checkbox.get_attribute("name") or ""
            checkbox_id = await checkbox.get_attribute("id") or ""
            class_attr = await checkbox.get_attribute("class") or ""
            is_checked = await checkbox.is_checked()

            # Get label text
            label_text = ""
            if checkbox_id:
                label_locator = page.locator(f'label[for="{checkbox_id}"]')
                if await label_locator.count() > 0:
                    label_text = await label_locator.text_content() or ""

            # Create selector
            selector = None
            if checkbox_id:
                selector = f"#{checkbox_id}"
            elif class_attr:
                class_names = class_attr.split()
                if class_names:
                    selector = f'input[type="{checkbox_type}"].{class_names[0]}'
            elif checkbox_name:
                selector = f'input[name="{checkbox_name}"][type="{checkbox_type}"]'
            else:
                selector = f'input[type="{checkbox_type}"]'

            checkboxes.append(
                {
                    "type": checkbox_type,
                    "name": checkbox_name,
                    "id": checkbox_id,
                    "classes": class_attr,
                    "labelText": label_text.strip(),
                    "checked": is_checked,
                    "selector": selector,
                }
            )

        if checkboxes:
            interactive_elements["checkboxes"] = checkboxes
            
    # Extract image elements (useful for image-heavy sites like Unsplash)
    images_locator = page.locator("img")
    image_count = await images_locator.count()
    if image_count > 0:
        images = []
        for i in range(min(image_count, 20)):  # Limit to 20 images
            img = images_locator.nth(i)
            
            # Skip if not visible
            if not await img.is_visible():
                continue
                
            img_src = await img.get_attribute("src") or ""
            img_alt = await img.get_attribute("alt") or ""
            img_id = await img.get_attribute("id") or ""
            class_attr = await img.get_attribute("class") or ""
            data_testid = await img.get_attribute("data-testid") or ""
            
            # Create selector
            selector = None
            if img_id:
                selector = f"img#{img_id}"
            elif data_testid:
                selector = f'img[data-testid="{data_testid}"]'
            elif class_attr:
                class_names = class_attr.split()
                if class_names:
                    selector = f"img.{class_names[0]}"
            else:
                if img_alt:
                    selector = f'img[alt="{img_alt}"]'
                else:
                    selector = f"img:nth-child({i+1})"
                    
            images.append({
                "src": img_src,
                "alt": img_alt,
                "id": img_id,
                "classes": class_attr,
                "dataTestId": data_testid,
                "selector": selector,
                "positionSelector": f"img:nth-child({i+1})",
                "containerPositionSelector": f"img:nth-of-type({i+1})"
            })
        
        if images:
            interactive_elements["images"] = images

    if interactive_elements:
        result["interactiveElements"] = interactive_elements

    return result
