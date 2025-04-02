// Type definitions for CrustData Browser Automation system

// Session types
export interface SessionResponse {
    session_id: string;
    status: string;
    message: string;
}

export interface SessionStatus {
    status: string;
    message: string;
    [key: string]: any;
}

// Command types
export interface CommandResponse {
    command_id: string;
    status: string;
    message: string;
}

export interface CommandResult {
    status: string;
    message: string;
    result?: any;
    screenshot_path?: string;
}

// Screenshot types
export interface ScreenshotResponse {
    status: string;
    message: string;
    screenshot_path: string;
}

// Message types (for chat interface)
export interface Message {
    id: string;
    type: 'user' | 'system' | 'result' | 'error';
    content: string;
    timestamp: Date;
    metadata?: {
        commandId?: string;
        sessionId?: string;
        screenshot_path?: string;
        result?: any;
    };
}

// Browser session configuration
export interface BrowserConfig {
    browser_type: 'chromium' | 'firefox' | 'webkit';
    headless: boolean;
    timeout: number;
}

// Extraction types
export interface ExtractionResult {
    status: string;
    message: string;
    data: any;
    screenshot_path?: string;
}