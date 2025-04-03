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

    Note: We use a hybrid approach here - using locators for basic page details
    and a more focused evaluate call for the complex extraction of interactive elements
    and page structure.
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

    # Use evaluate call for the complex element extraction since it's more efficient than
    # multiple locator calls for this specific case
    # This is more focused than before, only extracting interactive elements
    page_details = await page.evaluate("""() => {
        // Helper function to get a simplified DOM path
        function getElementPath(element, maxLength = 80) {
            let path = '';
            const idPath = [];
            const classPath = [];
            
            // Try to create a reasonable path with id/class info
            while (element && element.nodeType === Node.ELEMENT_NODE) {
                let identifier = element.tagName.toLowerCase();
                
                if (element.id) {
                    identifier += '#' + element.id;
                    idPath.unshift(identifier);
                } else if (element.className && typeof element.className === 'string') {
                    const classes = element.className.split(/\\s+/).filter(Boolean).join('.');
                    if (classes) {
                        identifier += '.' + classes;
                    }
                    classPath.unshift(identifier);
                } else {
                    // Count sibling position for elements without ID or class
                    let sibling = element, position = 1;
                    while (sibling = sibling.previousElementSibling) {
                        if (sibling.tagName === element.tagName) position++;
                    }
                    
                    if (position > 1) {
                        identifier += `:nth-of-type(${position})`;
                    }
                    classPath.unshift(identifier);
                }
                
                element = element.parentElement;
            }
            
            // Prefer ID-based paths, then class-based
            path = idPath.length > 0 ? idPath.join(' > ') : classPath.join(' > ');
            
            // Truncate if too long
            if (path.length > maxLength) {
                path = '...' + path.substring(path.length - maxLength);
            }
            
            return path;
        }
        
        // Helper function to generate a CSS selector for an element
        function getCssSelector(element) {
            if (!element) return null;
            
            // If element has an ID, that's the simplest selector
            if (element.id) {
                return `#${element.id}`;
            }
            
            // If element has a name attribute (common for form elements)
            if (element.name && (element.tagName === 'INPUT' || element.tagName === 'SELECT' || element.tagName === 'TEXTAREA')) {
                return `${element.tagName.toLowerCase()}[name="${element.name}"]`;
            }
            
            // For buttons and links, try to use text content
            if ((element.tagName === 'BUTTON' || element.tagName === 'A') && element.textContent.trim()) {
                const trimmedText = element.textContent.trim().substring(0, 30).replace(/"/g, '\\"');
                return `${element.tagName.toLowerCase()}:contains("${trimmedText}")`;
            }
            
            // If element has distinguishing classes
            if (element.className && typeof element.className === 'string') {
                const classes = element.className.split(/\\s+/).filter(Boolean);
                if (classes.length > 0) {
                    // Use the most specific class that would likely identify the element
                    let bestClass = classes.find(cls => cls.match(/^(btn|button|submit|search|input|field|form|menu|nav|link|item|card|container)/) || 
                                                        cls.match(/[A-Z]/) || // Component-style class names often have capitals
                                                        cls.length > 8); // Longer class names tend to be more specific
                    
                    if (!bestClass) bestClass = classes[0]; // Fallback to first class
                    return `${element.tagName.toLowerCase()}.${bestClass}`;
                }
            }
            
            // Fallback to a position-based selector
            let parent = element.parentElement;
            if (parent) {
                let siblings = Array.from(parent.children).filter(child => child.tagName === element.tagName);
                if (siblings.length > 1) {
                    const index = siblings.indexOf(element) + 1;
                    return `${element.tagName.toLowerCase()}:nth-of-type(${index})`;
                } else {
                    return element.tagName.toLowerCase();
                }
            }
            
            // Last resort
            return element.tagName.toLowerCase();
        }
        
        // Helper: Check if element is visible on page
        function isElementVisible(el) {
            if (!el) return false;
            if (el.style.display === 'none') return false;
            if (el.style.visibility === 'hidden') return false;
            if (el.style.opacity === '0') return false;
            
            const style = window.getComputedStyle(el);
            if (style.display === 'none') return false;
            if (style.visibility === 'hidden') return false;
            if (parseFloat(style.opacity) === 0) return false;
            
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return false;
            
            return true;
        }

        // Extract interactive elements only - more focused approach
        const interactiveElements = {
            inputs: [],
            buttons: [],
            links: [],
            selects: [],
            forms: [],
            checkboxes: []
        };
        
        // Extract inputs
        document.querySelectorAll('input:not([type="hidden"]):not([disabled]), textarea:not([disabled])').forEach(el => {
            if (!isElementVisible(el)) return;
            
            const visibleText = el.labels ? Array.from(el.labels).map(label => label.textContent.trim()).join(' ') : '';
            const placeholder = el.placeholder || '';
            const selector = getCssSelector(el);
            
            interactiveElements.inputs.push({
                type: el.type || 'text',
                name: el.name || '',
                id: el.id || '',
                placeholder: placeholder,
                labelText: visibleText,
                selector: selector,
                isRequired: el.required
            });
        });
        
        // Extract buttons
        document.querySelectorAll('button:not([disabled]), [type="button"]:not([disabled]), [type="submit"]:not([disabled]), [role="button"]:not([disabled])').forEach(el => {
            if (!isElementVisible(el)) return;
            
            const text = el.innerText.trim().substring(0, 50);
            const selector = getCssSelector(el);
            
            interactiveElements.buttons.push({
                text: text,
                id: el.id || '',
                selector: selector,
                isSubmit: el.type === 'submit'
            });
        });
        
        // Extract links
        document.querySelectorAll('a:not([disabled])').forEach(el => {
            if (!isElementVisible(el)) return;
            
            const text = el.innerText.trim().substring(0, 50);
            const selector = getCssSelector(el);
            
            interactiveElements.links.push({
                text: text,
                href: el.href || '',
                selector: selector
            });
        });
        
        // Extract select elements
        document.querySelectorAll('select:not([disabled])').forEach(el => {
            if (!isElementVisible(el)) return;
            
            const selector = getCssSelector(el);
            const labelText = el.labels ? Array.from(el.labels).map(label => label.textContent.trim()).join(' ') : '';
            
            interactiveElements.selects.push({
                name: el.name || '',
                id: el.id || '',
                labelText: labelText,
                options: Array.from(el.options).map(opt => ({
                    text: opt.text,
                    value: opt.value,
                    selected: opt.selected
                })).slice(0, 15), // Limit options for brevity
                selector: selector
            });
        });
        
        // Extract form elements
        document.querySelectorAll('form').forEach(el => {
            const submitButton = el.querySelector('button[type="submit"], input[type="submit"]');
            
            interactiveElements.forms.push({
                id: el.id || '',
                action: el.action || '',
                method: el.method || 'get',
                selector: getCssSelector(el),
                submitSelector: submitButton ? getCssSelector(submitButton) : null,
                submitText: submitButton ? (submitButton.innerText.trim() || submitButton.value) : ''
            });
        });
        
        // Extract checkboxes and radio buttons
        document.querySelectorAll('input[type="checkbox"]:not([disabled]), input[type="radio"]:not([disabled])').forEach(el => {
            if (!isElementVisible(el)) return;
            
            const labelText = el.labels ? Array.from(el.labels).map(label => label.textContent.trim()).join(' ') : '';
            const selector = getCssSelector(el);
            
            interactiveElements.checkboxes.push({
                type: el.type,
                name: el.name || '',
                id: el.id || '',
                labelText: labelText,
                checked: el.checked,
                selector: selector
            });
        });
        
        // Extract headings as they provide context
        const headings = {
            h1: Array.from(document.querySelectorAll('h1')).map(h => h.innerText.trim()).filter(Boolean),
            h2: Array.from(document.querySelectorAll('h2')).slice(0, 5).map(h => h.innerText.trim()).filter(Boolean)
        };
        
        // Extract main content text (truncated)
        const mainContent = document.querySelector('main, [role="main"], #main, .main, #content, .content, article');
        const mainText = mainContent 
            ? mainContent.innerText.substring(0, 500) + (mainContent.innerText.length > 500 ? '...' : '')
            : document.body.innerText.substring(0, 300) + (document.body.innerText.length > 300 ? '...' : '');
            
        return {
            interactiveElements,
            headings,
            mainText
        };
    }""")

    # Combine the data from locators and evaluate
    return {
        "title": title,
        "url": url,
        "pageFeatures": {
            "hasCaptcha": has_captcha,
            "hasLoginForm": has_login_form,
            "hasNavigation": has_navigation,
            "hasSearchBox": has_search_box,
        },
        "headings": page_details["headings"],
        "mainText": page_details["mainText"],
        "interactiveElements": page_details["interactiveElements"],
    }
