from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field


class InteractionRequest(BaseModel):
    user_input: str
    timeout: Optional[int] = Field(default=30, description="Global timeout in seconds")
    headless: Optional[bool] = Field(
        default=False, description="Run browser in headless mode"
    )
    browser_type: Optional[str] = Field(
        default="chromium", description="Browser to use: chromium, firefox, or webkit"
    )
    wait_for_captcha: Optional[bool] = Field(
        default=True, description="Pause execution and wait for user to solve captchas"
    )


class InteractionResponse(BaseModel):
    status: str
    message: str
    details: Optional[Dict] = None
    screenshot_path: Optional[str] = None


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
    wait_for_captcha: Optional[bool] = Field(
        default=True, description="Pause execution and wait for user to solve captchas"
    )


class ExtractResponse(BaseModel):
    status: str
    message: str
    data: Optional[Union[Dict, List, str]] = None
    screenshot_path: Optional[str] = None
