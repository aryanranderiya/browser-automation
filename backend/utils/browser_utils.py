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

        // Function to extract interactive elements with improved selectors
        function extractInteractiveElements() {
            const interactive = {
                inputs: [],
                buttons: [],
                links: [],
                selects: [],
                forms: [],
                images: [],
                checkboxes: []
            };
            
            // Get input fields with improved handling
            document.querySelectorAll('input:not([type="hidden"]):not([disabled]), textarea:not([disabled])').forEach(el => {
                const visibleText = el.labels ? Array.from(el.labels).map(label => label.textContent.trim()).join(' ') : '';
                const placeholder = el.placeholder || '';
                const selector = getCssSelector(el);
                
                interactive.inputs.push({
                    type: el.type || 'text',
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: placeholder,
                    labelText: visibleText,
                    value: el.value || '',
                    path: getElementPath(el),
                    selector: selector,
                    isRequired: el.required,
                    isDisabled: el.disabled,
                    isVisible: isElementVisible(el)
                });
            });
            
            // Get buttons with more context
            document.querySelectorAll('button:not([disabled]), [type="button"]:not([disabled]), [type="submit"]:not([disabled]), [role="button"]:not([disabled])').forEach(el => {
                const text = el.innerText.trim().substring(0, 50);
                const ariaLabel = el.getAttribute('aria-label') || '';
                const selector = getCssSelector(el);
                
                interactive.buttons.push({
                    text: text,
                    ariaLabel: ariaLabel,
                    id: el.id || '',
                    path: getElementPath(el),
                    selector: selector,
                    hasIcon: el.querySelector('i, svg, img') !== null,
                    isPrimary: el.classList.contains('primary') || el.classList.contains('btn-primary'),
                    isSubmit: el.type === 'submit',
                    isVisible: isElementVisible(el)
                });
            });
            
            // Get links with better context
            document.querySelectorAll('a:not([disabled])').forEach(el => {
                const text = el.innerText.trim().substring(0, 50);
                const selector = getCssSelector(el);
                
                interactive.links.push({
                    text: text,
                    href: el.href || '',
                    id: el.id || '',
                    title: el.title || '',
                    path: getElementPath(el),
                    selector: selector,
                    isNavigation: isLikelyNavigationLink(el),
                    isExternal: el.hostname !== window.location.hostname,
                    isVisible: isElementVisible(el)
                });
            });
            
            // Get select dropdowns with options
            document.querySelectorAll('select:not([disabled])').forEach(el => {
                const selector = getCssSelector(el);
                const labelText = getSelectLabel(el);
                
                interactive.selects.push({
                    name: el.name || '',
                    id: el.id || '',
                    labelText: labelText,
                    options: Array.from(el.options).map(opt => ({
                        text: opt.text,
                        value: opt.value,
                        selected: opt.selected
                    })).slice(0, 15), // Limit to 15 options for brevity
                    path: getElementPath(el),
                    selector: selector,
                    isRequired: el.required,
                    isVisible: isElementVisible(el)
                });
            });
            
            // Get forms with their fields
            document.querySelectorAll('form').forEach(el => {
                const fields = Array.from(el.querySelectorAll('input:not([type="hidden"]), select, textarea')).map(field => {
                    return {
                        type: field.tagName.toLowerCase() === 'select' ? 'select' : field.type || 'text',
                        name: field.name || '',
                        id: field.id || '',
                        selector: getCssSelector(field),
                        required: field.required
                    };
                });
                
                const submitButton = el.querySelector('button[type="submit"], input[type="submit"]');
                
                interactive.forms.push({
                    id: el.id || '',
                    action: el.action || '',
                    method: el.method || 'get',
                    path: getElementPath(el),
                    selector: getCssSelector(el),
                    fields: fields,
                    submitSelector: submitButton ? getCssSelector(submitButton) : null,
                    submitText: submitButton ? (submitButton.innerText.trim() || submitButton.value) : ''
                });
            });
            
            // Get checkboxes and radio buttons
            document.querySelectorAll('input[type="checkbox"]:not([disabled]), input[type="radio"]:not([disabled])').forEach(el => {
                const labelText = el.labels ? Array.from(el.labels).map(label => label.textContent.trim()).join(' ') : '';
                const selector = getCssSelector(el);
                
                interactive.checkboxes.push({
                    type: el.type,
                    name: el.name || '',
                    id: el.id || '',
                    labelText: labelText,
                    checked: el.checked,
                    selector: selector,
                    isRequired: el.required,
                    isVisible: isElementVisible(el)
                });
            });
            
            // Get important images
            document.querySelectorAll('img[alt]:not([alt=""]), img[src*="logo"], img[class*="logo"], svg').forEach(el => {
                if (el.width < 5 || el.height < 5) return; // Skip tiny images
                
                interactive.images.push({
                    alt: el.alt || '',
                    src: el.src || '',
                    selector: getCssSelector(el),
                    isLogo: isLikelyLogo(el),
                    width: el.width,
                    height: el.height
                });
            });
            
            return interactive;
        }
        
        // Helper: Check if element is a logo
        function isLikelyLogo(el) {
            if (el.alt && el.alt.toLowerCase().includes('logo')) return true;
            if (el.src && el.src.toLowerCase().includes('logo')) return true;
            if (el.className && el.className.toLowerCase().includes('logo')) return true;
            if (el.id && el.id.toLowerCase().includes('logo')) return true;
            
            // Check if it's in the header area
            const rect = el.getBoundingClientRect();
            return rect.top < 150 && (rect.left < 300 || rect.right > window.innerWidth - 300);
        }
        
        // Helper: Check if link is likely a navigation link
        function isLikelyNavigationLink(el) {
            // Check if in navigation element
            if (el.closest('nav, [role="navigation"], .nav, .navigation, .menu, header')) return true;
            
            // Check if it has navigation-like classes
            if (el.className && /nav|menu|header|top|main/.test(el.className.toLowerCase())) return true;
            
            return false;
        }
        
        // Helper: Get a select element's label text
        function getSelectLabel(selectEl) {
            // First check for an associated label
            if (selectEl.id) {
                const label = document.querySelector(`label[for="${selectEl.id}"]`);
                if (label) return label.textContent.trim();
            }
            
            // Look for a sibling or parent label
            const parentLabel = selectEl.closest('label');
            if (parentLabel) {
                return parentLabel.textContent.replace(selectEl.outerHTML, '').trim();
            }
            
            // Look for nearby text that might be a label
            const prev = selectEl.previousElementSibling;
            if (prev && (prev.tagName === 'LABEL' || prev.tagName === 'SPAN' || prev.tagName === 'DIV')) {
                return prev.textContent.trim();
            }
            
            return '';
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

        // Extract page structure with enhanced metadata
        function extractPageStructure() {
            // Basic page info
            const title = document.title;
            const url = window.location.href;
            const domain = window.location.hostname;
            const metaDescription = document.querySelector('meta[name="description"]')?.content || '';
            
            // Extract website type/category based on content
            const pageType = determinePageType();
            
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
            
            // Extract main content areas
            const mainContentText = extractMainContent();
            
            // Check for important UI components
            const hasLoginForm = !!document.querySelector('form input[type="password"]') ||
                                document.body.innerText.toLowerCase().includes('sign in') ||
                                document.body.innerText.toLowerCase().includes('log in');
            
            const hasCaptcha = document.body.innerHTML.toLowerCase().includes('captcha') ||
                            document.body.innerHTML.toLowerCase().includes('recaptcha') ||
                            document.body.innerHTML.toLowerCase().includes('cloudflare') ||
                            document.body.innerText.toLowerCase().includes('i\'m not a robot');
            
            const hasNavigation = !!document.querySelector('nav, [role="navigation"]');
            
            const hasSearchBox = !!document.querySelector('input[type="search"], input[name*="search"], input[placeholder*="search" i], input[aria-label*="search" i]');
            
            return {
                title,
                url,
                domain,
                metaDescription,
                pageType,
                mainText,
                mainContentText,
                headings: {
                    h1: h1Text,
                    h2: h2Text
                },
                pageFeatures: {
                    hasLoginForm,
                    hasCaptcha,
                    hasNavigation,
                    hasSearchBox
                },
                interactiveElements: extractInteractiveElements()
            };
        }
        
        // Helper: Determine type of website
        function determinePageType() {
            const url = window.location.href.toLowerCase();
            const title = document.title.toLowerCase();
            const bodyText = document.body.innerText.toLowerCase();
            
            // E-commerce indicators
            if (
                url.includes('shop') || url.includes('store') || 
                title.includes('shop') || title.includes('store') || 
                bodyText.includes('shopping cart') || bodyText.includes('add to cart') ||
                bodyText.includes('checkout') || document.querySelector('.product, .price, [data-product-id]')
            ) {
                return 'e-commerce';
            }
            
            // Search engine
            if (
                url.includes('search') || title.includes('search') ||
                bodyText.includes('search results') || 
                document.querySelector('input[type="search"], form[role="search"]')
            ) {
                return 'search';
            }
            
            // Social media
            if (
                url.includes('feed') || url.includes('profile') || 
                bodyText.includes('follow') || bodyText.includes('like') ||
                bodyText.includes('comment') || bodyText.includes('share')
            ) {
                return 'social-media';
            }
            
            // News or blog
            if (
                url.includes('news') || url.includes('article') || url.includes('blog') ||
                title.includes('news') || document.querySelector('article, .article, .post')
            ) {
                return 'news-or-blog';
            }
            
            // Login page
            if (
                url.includes('login') || url.includes('signin') || 
                bodyText.includes('login') || bodyText.includes('sign in') ||
                document.querySelector('input[type="password"]')
            ) {
                return 'login';
            }
            
            return 'general'; // Default
        }
        
        // Helper: Extract the main content by looking for main content containers
        function extractMainContent() {
            // Look for common main content containers
            const mainContent = document.querySelector('main, [role="main"], #main, .main, #content, .content, article');
            
            if (mainContent) {
                return mainContent.innerText.substring(0, 1000) + 
                      (mainContent.innerText.length > 1000 ? '...' : '');
            }
            
            // Fallback to body text
            return document.body.innerText.substring(0, 500) + 
                  (document.body.innerText.length > 500 ? '...' : '');
        }
        
        return extractPageStructure();
    }""")
