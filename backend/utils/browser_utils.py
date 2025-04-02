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
    """
    return await page.evaluate("""() => {
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

        // Function to extract interactive elements
        function extractInteractiveElements() {
            const interactive = {
                inputs: [],
                buttons: [],
                links: [],
                selects: [],
                forms: []
            };
            
            // Get input fields
            document.querySelectorAll('input:not([type="hidden"]), textarea').forEach(el => {
                interactive.inputs.push({
                    type: el.type || 'text',
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: el.placeholder || '',
                    path: getElementPath(el),
                    selector: el.id ? `#${el.id}` : 
                             el.name ? `[name="${el.name}"]` : null
                });
            });
            
            // Get buttons
            document.querySelectorAll('button, [type="button"], [type="submit"], [role="button"]').forEach(el => {
                const text = el.innerText.trim().substring(0, 50);
                interactive.buttons.push({
                    text: text,
                    id: el.id || '',
                    path: getElementPath(el),
                    selector: el.id ? `#${el.id}` : 
                              text ? `button:contains("${text}")` : null
                });
            });
            
            // Get links
            document.querySelectorAll('a').forEach(el => {
                const text = el.innerText.trim().substring(0, 50);
                interactive.links.push({
                    text: text,
                    href: el.href || '',
                    id: el.id || '',
                    path: getElementPath(el),
                    selector: el.id ? `#${el.id}` : 
                              text ? `a:contains("${text}")` : null
                });
            });
            
            // Get select dropdowns
            document.querySelectorAll('select').forEach(el => {
                interactive.selects.push({
                    name: el.name || '',
                    id: el.id || '',
                    options: Array.from(el.options).map(opt => opt.text).slice(0, 10),
                    path: getElementPath(el),
                    selector: el.id ? `#${el.id}` : 
                              el.name ? `select[name="${el.name}"]` : null
                });
            });
            
            // Get forms
            document.querySelectorAll('form').forEach(el => {
                interactive.forms.push({
                    id: el.id || '',
                    action: el.action || '',
                    method: el.method || 'get',
                    path: getElementPath(el),
                    selector: el.id ? `#${el.id}` : null
                });
            });
            
            return interactive;
        }

        // Main structure extraction
        const title = document.title;
        const url = window.location.href;
        const metaDescription = document.querySelector('meta[name="description"]')?.content || '';
        
        // Extract visible text (truncated)
        const mainText = document.body.innerText.substring(0, 500) + 
                        (document.body.innerText.length > 500 ? '...' : '');
        
        // Extract main heading
        const h1Text = Array.from(document.querySelectorAll('h1'))
            .map(h => h.innerText.trim())
            .filter(Boolean)
            .join(' | ');
            
        const h2Text = Array.from(document.querySelectorAll('h2'))
            .map(h => h.innerText.trim())
            .filter(Boolean)
            .slice(0, 5)
            .join(' | ') + 
            (document.querySelectorAll('h2').length > 5 ? '...' : '');
        
        return {
            title,
            url,
            metaDescription,
            mainText,
            headings: {
                h1: h1Text,
                h2: h2Text
            },
            interactiveElements: extractInteractiveElements()
        };
    }""")
