import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import axios from 'axios';

// Helper to combine Tailwind CSS classes
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// API Base URL
const API_BASE_URL = 'http://localhost:8000';

// API interaction functions
export const api = {
  // Start a new browser session
  async startBrowser(options = {}) {
    const response = await axios.post(`${API_BASE_URL}/start_browser`, options);
    return response.data;
  },

  // Stop a browser session
  async stopBrowser(sessionId: string) {
    const response = await axios.post(`${API_BASE_URL}/stop_browser/${sessionId}`);
    return response.data;
  },

  // Send a command to a browser session
  async executeCommand(sessionId: string, userInput: string, timeout = 60) {
    const response = await axios.post(`${API_BASE_URL}/interact/${sessionId}`, {
      user_input: userInput,
      timeout
    });
    return response.data;
  },

  // Check the status of a command
  async getCommandStatus(sessionId: string, commandId: string) {
    const response = await axios.get(`${API_BASE_URL}/command_status/${sessionId}/${commandId}`);
    return response.data;
  },

  // Check the status of a session
  async getSessionStatus(sessionId: string) {
    const response = await axios.get(`${API_BASE_URL}/session/${sessionId}`);
    return response.data;
  },

  // Signal that a captcha has been resolved
  async resolveCaptcha(sessionId: string) {
    const response = await axios.post(`${API_BASE_URL}/resolve_captcha/${sessionId}`);
    return response.data;
  }
};

// Types for API responses
export interface CommandResult {
  command: string;
  success: boolean;
  message: string;
  data?: any;
}

export interface SessionStatus {
  status: string;
  session_info: {
    session_id: string;
    is_active: boolean;
    browser_type: string;
    headless: boolean;
    pending_commands: number;
    last_activity: number;
    current_url: string | null;
  };
}

export interface CommandStatus {
  status: string;
  result?: {
    status: string;
    results: CommandResult[];
    explanation: string;
    task_completed: boolean;
  };
  task_status?: string;
  progress?: {
    actions_completed: number;
    last_action: string | null;
    current_explanation: string;
  };
}
