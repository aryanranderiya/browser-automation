import uuid
import time
from typing import Dict, Optional, Any
from playwright.async_api import async_playwright, Browser, Page
from utils.logger import setup_logger
from dotenv import load_dotenv

load_dotenv()
logger = setup_logger("browser_session")


class BrowserSession:
    """Manages a persistent browser session without command queue"""

    def __init__(
        self, browser_type: str = "chromium", headless: bool = False, timeout: int = 30
    ):
        self.session_id = str(uuid.uuid4())
        self.browser_type = browser_type
        self.headless = headless
        self.timeout = timeout
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.is_active: bool = False
        self.last_activity: float = time.time()
        self.session_data: Dict[str, Any] = {}  # Store session state like login info
        self.logger = setup_logger(f"session_{self.session_id[:8]}")
        self.screenshot_path: Optional[str] = None
        self.playwright = None

    async def start(self):
        """Start the browser session"""
        if self.is_active:
            return False

        self.logger.info(
            f"Starting browser session {self.session_id} with {self.browser_type}"
        )
        self.playwright = await async_playwright().start()

        browser_types = {
            "chromium": self.playwright.chromium,
            "firefox": self.playwright.firefox,
            "webkit": self.playwright.webkit,
        }

        if self.browser_type.lower() not in browser_types:
            self.browser_type = "chromium"

        self.browser = await browser_types[self.browser_type.lower()].launch(
            headless=self.headless
        )
        self.page = await self.browser.new_page()
        self.is_active = True
        self.last_activity = time.time()
        return True

    async def stop(self):
        """Stop the browser session"""
        if not self.is_active:
            return False

        self.logger.info(f"Stopping browser session {self.session_id}")
        self.is_active = False

        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

        return True

    async def get_session_status(self) -> Dict:
        """Get current session status"""
        return {
            "session_id": self.session_id,
            "is_active": self.is_active,
            "browser_type": self.browser_type,
            "headless": self.headless,
            "last_activity": self.last_activity,
            "current_url": self.page.url if self.page and self.is_active else None,
            "screenshot_path": self.screenshot_path,
        }

    async def take_screenshot(self) -> str:
        """Take a screenshot of the current page"""
        if not self.is_active or not self.page:
            raise ValueError("Browser session is not active")

        filename = f"screenshot_{self.session_id}_{int(time.time())}.png"
        path = f"/tmp/{filename}"
        await self.page.screenshot(path=path)
        self.screenshot_path = path
        return path

    async def get_page(self) -> Optional[Page]:
        """Get the current page object"""
        if not self.is_active:
            return None
        return self.page


# Global session manager
class BrowserSessionManager:
    def __init__(self):
        self.sessions: Dict[BrowserSession] = {}
        self.logger = setup_logger("session_manager")

    async def create_session(
        self, browser_type: str = "chromium", headless: bool = False, timeout: int = 30
    ) -> str:
        """Create a new browser session and return session ID"""
        session = BrowserSession(
            browser_type=browser_type, headless=headless, timeout=timeout
        )
        await session.start()

        self.sessions[session.session_id] = session
        self.logger.info(f"Created new browser session {session.session_id}")

        return session.session_id

    async def get_session(self, session_id: str) -> Optional[BrowserSession]:
        """Get a browser session by ID"""

        print("this is the sessions", self.sessions)

        return self.sessions.get(session_id)

    async def get_session_status(self, session_id: str) -> Dict:
        """Get the status of a session"""
        session = await self.get_session(session_id)
        if not session:
            return {"status": "error", "message": f"Session {session_id} not found"}

        return await session.get_session_status()

    async def stop_session(self, session_id: str) -> bool:
        """Stop a browser session"""
        session = await self.get_session(session_id)
        if not session:
            return False

        result = await session.stop()
        if result:
            del self.sessions[session_id]
            self.logger.info(f"Stopped and removed session {session_id}")

        return result


# Global instance
session_manager = BrowserSessionManager()
