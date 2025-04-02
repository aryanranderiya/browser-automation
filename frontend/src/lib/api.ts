import axios from 'axios';

/**
 * API client for interacting with the browser automation backend
 */
const api = axios.create({
    baseURL: 'http://localhost:8000', // Point directly to the backend server
    timeout: 30000, // 30 seconds timeout
});

/**
 * Browser Agent API service
 * Provides methods for interacting with the browser-agent endpoints
 */
export const browserAgentAPI = {
    /**
     * Execute a browser agent task autonomously or interactively
     * 
     * @param task - Natural language task description
     * @param options - Configuration options
     * @returns Promise with the task execution response
     */
    executeTask: async (task, options = {}) => {
        const {
            startUrl = 'https://www.google.com',
            interactive = false,
            maxSteps = 10,
            headless = false,
            browserType = 'chromium'
        } = options;

        return api.post('/browser-agent/execute', {
            task,
            start_url: startUrl,
            interactive,
            max_steps: maxSteps,
            headless,
            browser_type: browserType
        });
    },

    /**
     * Execute a step in an interactive session
     * 
     * @param sessionId - The ID of the active agent session
     * @param steps - Number of steps to execute (default: 1)
     * @returns Promise with the step execution response
     */
    executeStep: async (sessionId, steps = 1) => {
        return api.post('/browser-agent/step', {
            session_id: sessionId,
            steps
        });
    },

    /**
     * Get the status of an active session
     * 
     * @param sessionId - The ID of the agent session
     * @returns Promise with the session status
     */
    getSessionStatus: async (sessionId) => {
        return api.get(`/browser-agent/session/${sessionId}`);
    },

    /**
     * Clean up and terminate a browser agent session
     * 
     * @param sessionId - The ID of the agent session to terminate
     * @returns Promise with the cleanup result
     */
    cleanupSession: async (sessionId) => {
        return api.delete(`/browser-agent/session/${sessionId}`);
    }
};

/**
 * Browser Automation API service
 * Provides methods for interacting with the automate endpoints
 */
export const automationAPI = {
    /**
     * Start a new browser automation session
     * 
     * @param options - Session configuration options
     * @returns Promise with the session creation response
     */
    startSession: async (options = {}) => {
        const {
            browserType = 'chromium',
            headless = false,
            timeout = 30
        } = options;

        return api.post('/automate/session/start', {
            browser_type: browserType,
            headless,
            timeout
        });
    },

    /**
     * Execute a command in an active browser session
     * 
     * @param sessionId - The ID of the active session
     * @param userInput - Natural language command
     * @returns Promise with the command execution response
     */
    executeCommand: async (sessionId, userInput) => {
        return api.post(`/automate/session/${sessionId}/execute`, {
            user_input: userInput
        });
    },

    /**
     * Get the status of an active automation session
     * 
     * @param sessionId - The ID of the automation session
     * @returns Promise with the session status
     */
    getSessionStatus: async (sessionId) => {
        return api.get(`/automate/session/${sessionId}/status`);
    },

    /**
     * Stop an active automation session
     * 
     * @param sessionId - The ID of the automation session to stop
     * @returns Promise with the session termination response
     */
    stopSession: async (sessionId) => {
        return api.post(`/automate/session/${sessionId}/stop`);
    }
};

/**
 * Browser Interaction API service
 * Provides methods for direct browser interactions
 */
export const interactionAPI = {
    /**
     * Execute a natural language interaction in a browser
     * 
     * @param userInput - Natural language instruction
     * @param options - Configuration options
     * @returns Promise with the interaction response
     */
    interact: async (userInput, options = {}) => {
        const {
            timeout = 30,
            headless = false,
            browserType = 'chromium'
        } = options;

        return api.post('/interact', {
            user_input: userInput,
            timeout,
            headless,
            browser_type: browserType
        });
    },

    /**
     * Extract data from a webpage
     * 
     * @param url - The URL to extract data from
     * @param extractionType - Type of extraction (text, links, table, elements, json)
     * @param options - Additional extraction options
     * @returns Promise with the extraction response
     */
    extract: async (url, extractionType, options = {}) => {
        const {
            selector = null,
            attributes = null,
            timeout = 30,
            headless = true,
            browserType = 'chromium'
        } = options;

        const requestData = {
            url,
            extraction_type: extractionType,
            timeout,
            headless,
            browser_type: browserType
        };

        if (selector) requestData.selector = selector;
        if (attributes) requestData.attributes = attributes;

        return api.post('/extract', requestData);
    }
};

export default {
    browserAgentAPI,
    automationAPI,
    interactionAPI
};