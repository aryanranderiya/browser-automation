"use client";

import { useState, useEffect, useRef } from "react";
import { api, CommandStatus, SessionStatus } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

// Define message types for the chat interface
interface Message {
  id: string;
  type: "user" | "system" | "result";
  content: string;
  timestamp: Date;
  status?: "pending" | "completed" | "error";
  commandDetails?: any;
  progressSteps?: { action: string; status: string; message?: string }[];
}

export default function BrowserAutomation() {
  // State for browser session
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<SessionStatus | null>(
    null
  );
  const [isStartingSession, setIsStartingSession] = useState(false);
  const [isStoppingSession, setIsStoppingSession] = useState(false);

  // State for command execution
  const [userInput, setUserInput] = useState("");
  const [isExecutingCommand, setIsExecutingCommand] = useState(false);
  const [currentCommandId, setCurrentCommandId] = useState<string | null>(null);
  const [commandStatus, setCommandStatus] = useState<CommandStatus | null>(
    null
  );

  // Chat message history (replaces command history)
  const [messages, setMessages] = useState<Message[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // State for UI
  const [error, setError] = useState<string | null>(null);
  const [showCaptchaPrompt, setShowCaptchaPrompt] = useState(false);

  // Refs
  const statusCheckInterval = useRef<NodeJS.Timeout | null>(null);

  // Function to start a browser session
  const startSession = async () => {
    try {
      setIsStartingSession(true);
      setError(null);

      const response = await api.startBrowser({
        browser_type: "chromium",
        headless: false,
        wait_for_captcha: true,
      });

      setSessionId(response.session_id);
      setSessionStatus(await api.getSessionStatus(response.session_id));

      // Add a system message indicating the session has started
      addMessage({
        id: crypto.randomUUID(),
        type: "system",
        content: "Browser session started. What would you like to do?",
        timestamp: new Date(),
        status: "completed",
      });
    } catch (err: any) {
      setError(`Failed to start browser: ${err.message}`);
    } finally {
      setIsStartingSession(false);
    }
  };

  // Function to stop a browser session
  const stopSession = async () => {
    if (!sessionId) return;

    try {
      setIsStoppingSession(true);
      setError(null);

      await api.stopBrowser(sessionId);

      // Add a system message indicating the session has stopped
      addMessage({
        id: crypto.randomUUID(),
        type: "system",
        content: "Browser session stopped.",
        timestamp: new Date(),
        status: "completed",
      });

      // Clear session state
      setSessionId(null);
      setSessionStatus(null);
      setCommandStatus(null);
      setCurrentCommandId(null);

      // Clear polling interval
      if (statusCheckInterval.current) {
        clearInterval(statusCheckInterval.current);
        statusCheckInterval.current = null;
      }
    } catch (err: any) {
      setError(`Failed to stop browser: ${err.message}`);
    } finally {
      setIsStoppingSession(false);
    }
  };

  // Function to add a message to the chat
  const addMessage = (message: Message) => {
    setMessages((prev) => [...prev, message]);
  };

  // Function to execute a command
  const executeCommand = async () => {
    if (!sessionId || !userInput.trim()) return;

    // Generate a unique ID for this message
    const messageId = crypto.randomUUID();

    // Add user message
    addMessage({
      id: messageId,
      type: "user",
      content: userInput,
      timestamp: new Date(),
    });

    // Add a pending result message
    addMessage({
      id: `${messageId}-result`,
      type: "result",
      content: "Processing your request...",
      timestamp: new Date(),
      status: "pending",
      progressSteps: [],
    });

    try {
      setIsExecutingCommand(true);
      setError(null);
      setCommandStatus(null);

      const response = await api.executeCommand(sessionId, userInput, 60);

      // If we got a command ID, start polling for status
      if (response.details?.command_id) {
        setCurrentCommandId(response.details.command_id);

        // Start polling for command status
        if (statusCheckInterval.current) {
          clearInterval(statusCheckInterval.current);
        }

        statusCheckInterval.current = setInterval(async () => {
          if (!sessionId || !response.details.command_id) return;

          try {
            const status = await api.getCommandStatus(
              sessionId,
              response.details.command_id
            );
            setCommandStatus(status);

            // Collect progress steps if available
            let progressSteps: { action: string; status: string }[] = [];

            if (status.progress) {
              // Add current progress step
              progressSteps = [
                {
                  action: status.progress.last_action || "Processing",
                  status: "in-progress",
                },
              ];
            }

            // Add completed steps from results if available
            if (status.result?.results) {
              progressSteps = status.result.results.map(
                (result: {
                  command: string;
                  success: boolean;
                  message: Message;
                }) => ({
                  action: result.command,
                  status: result.success ? "completed" : "failed",
                  message: result.message,
                })
              );
            }

            // Update the result message with the latest status
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === `${messageId}-result`
                  ? {
                      ...msg,
                      content:
                        status.result?.explanation ||
                        status.progress?.current_explanation ||
                        "Processing your request...",
                      status:
                        status.status === "completed" ? "completed" : "pending",
                      progressSteps,
                      commandDetails: status.result,
                    }
                  : msg
              )
            );

            const sessionStatus = await api.getSessionStatus(sessionId);
            setSessionStatus(sessionStatus);

            // Check if we're waiting for captcha
            if (sessionStatus.status === "waiting_for_captcha") {
              setShowCaptchaPrompt(true);
            } else {
              setShowCaptchaPrompt(false);
            }

            // If command is completed, stop polling
            if (
              status.status === "completed" &&
              status.task_status === "completed"
            ) {
              if (statusCheckInterval.current) {
                clearInterval(statusCheckInterval.current);
                statusCheckInterval.current = null;
              }

              // Clear input
              setUserInput("");
            }
          } catch (err) {
            console.error("Error checking command status:", err);

            // Update the result message with the error
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === `${messageId}-result`
                  ? {
                      ...msg,
                      content: "Error checking command status",
                      status: "error",
                    }
                  : msg
              )
            );
          }
        }, 1000);
      }
    } catch (err: any) {
      setError(`Failed to execute command: ${err.message}`);

      // Update the result message with the error
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === `${messageId}-result`
            ? {
                ...msg,
                content: `Failed to execute command: ${err.message}`,
                status: "error",
              }
            : msg
        )
      );
    } finally {
      setIsExecutingCommand(false);
    }
  };

  // Function to handle captcha resolution
  const handleCaptchaResolved = async () => {
    if (!sessionId) return;

    try {
      await api.resolveCaptcha(sessionId);
      setShowCaptchaPrompt(false);

      // Add a system message about the captcha resolution
      addMessage({
        id: crypto.randomUUID(),
        type: "system",
        content: "Captcha has been resolved. Continuing with your request...",
        timestamp: new Date(),
        status: "completed",
      });
    } catch (err: any) {
      setError(`Failed to signal captcha resolution: ${err.message}`);
    }
  };

  // Scroll to bottom of chat when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Clean up interval on unmount
  useEffect(() => {
    return () => {
      if (statusCheckInterval.current) {
        clearInterval(statusCheckInterval.current);
      }
    };
  }, []);

  // Handle form submission
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (userInput.trim()) {
      executeCommand();
    }
  };

  // Handle key press in textarea (for Enter to send)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Send on Enter without Shift (Shift+Enter creates a new line)
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (userInput.trim()) {
        executeCommand();
      }
    }
  };

  // Function to periodically check session status
  useEffect(() => {
    let sessionCheckInterval: NodeJS.Timeout | null = null;

    // Only run if we have a session ID
    if (sessionId) {
      // Check session status immediately
      const checkSessionStatus = async () => {
        try {
          const status = await api.getSessionStatus(sessionId);
          setSessionStatus(status);

          // If the session is no longer active but our UI thinks it is,
          // update the UI state
          if (!status.session_info.is_active && sessionId) {
            addMessage({
              id: crypto.randomUUID(),
              type: "system",
              content:
                "Browser session disconnected. Please start a new session.",
              timestamp: new Date(),
              status: "error",
            });

            // Clear session state
            setSessionId(null);
            setCommandStatus(null);
            setCurrentCommandId(null);

            // Clear polling intervals
            if (statusCheckInterval.current) {
              clearInterval(statusCheckInterval.current);
              statusCheckInterval.current = null;
            }
          }
        } catch (err) {
          console.error("Error checking session status:", err);
          // If we can't reach the backend, assume session is lost
          setSessionId(null);
        }
      };

      // Check status immediately
      checkSessionStatus();

      // Then set up interval to check periodically (every 5 seconds)
      sessionCheckInterval = setInterval(checkSessionStatus, 5000);
    }

    // Clean up interval on unmount or when sessionId changes
    return () => {
      if (sessionCheckInterval) {
        clearInterval(sessionCheckInterval);
      }
    };
  }, [sessionId]);

  return (
    <div className="container mx-auto py-8 px-4">
      <Card className="mb-8">
        <CardHeader>
          <CardTitle>CrustData Browser Automation</CardTitle>
          <CardDescription>
            Control web browsers with natural language commands
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* Session controls */}
          <div className="mb-6">
            <h3 className="text-md font-medium mb-2">Browser Session</h3>
            {!sessionId ? (
              <Button onClick={startSession} disabled={isStartingSession}>
                {isStartingSession
                  ? "Starting..."
                  : "Start New Browser Session"}
              </Button>
            ) : (
              <div className="flex flex-col space-y-4">
                <div className="flex items-center">
                  <div className="bg-green-500 rounded-full h-3 w-3 mr-2"></div>
                  <span>
                    Session active:{" "}
                    {sessionStatus?.session_info.browser_type || "browser"}
                    {sessionStatus?.session_info.current_url &&
                      ` - ${sessionStatus.session_info.current_url}`}
                  </span>
                </div>
                <Button
                  onClick={stopSession}
                  variant="destructive"
                  disabled={isStoppingSession}
                >
                  {isStoppingSession ? "Stopping..." : "Stop Browser Session"}
                </Button>
              </div>
            )}
          </div>

          {/* Captcha prompt */}
          {showCaptchaPrompt && (
            <div className="mb-6 p-4 border border-yellow-500 bg-yellow-50 rounded-md">
              <h3 className="text-md font-medium mb-2 text-yellow-700">
                Captcha Detected
              </h3>
              <p className="mb-2">
                Please solve the captcha in the browser window, then click the
                button below to continue.
              </p>
              <Button onClick={handleCaptchaResolved} variant="outline">
                I&apos;ve Solved the Captcha
              </Button>
            </div>
          )}

          {/* Error display */}
          {error && (
            <div className="mb-6 p-4 border border-red-500 bg-red-50 rounded-md">
              <p className="text-red-700">{error}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Chat interface */}
      {sessionId && (
        <Card>
          <CardHeader>
            <CardTitle>Browser Automation Chat</CardTitle>
            <CardDescription>
              Send commands and view results in a conversation format
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* Messages display */}
            <div className="flex flex-col space-y-4 h-[500px] overflow-y-auto mb-4 p-4 border rounded-md">
              {messages.length === 0 ? (
                <div className="text-center text-gray-500 py-10">
                  Your conversation will appear here. Start by sending a
                  command.
                </div>
              ) : (
                messages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex ${
                      message.type === "user" ? "justify-end" : "justify-start"
                    }`}
                  >
                    <div
                      className={`rounded-lg p-4 max-w-[80%] ${
                        message.type === "user"
                          ? "bg-primary text-primary-foreground"
                          : message.type === "system"
                          ? "bg-secondary text-secondary-foreground"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {/* Message content */}
                      <div className="mb-2">
                        {message.status === "pending" && (
                          <div className="flex items-center mb-1">
                            <div className="animate-pulse mr-2 h-2 w-2 rounded-full bg-current"></div>
                            <span className="text-xs opacity-70">
                              Processing...
                            </span>
                          </div>
                        )}
                        <p>{message.content}</p>
                      </div>

                      {/* Progress steps */}
                      {message.type === "result" &&
                        message.progressSteps &&
                        message.progressSteps.length > 0 && (
                          <div className="mt-2 mb-3 border-t pt-2">
                            <p className="text-sm font-medium mb-1">
                              Progress:
                            </p>
                            <ul className="space-y-1">
                              {message.progressSteps.map((step, idx) => (
                                <li key={idx} className="flex items-start">
                                  {step.status === "in-progress" ? (
                                    <div className="flex-shrink-0 mr-2 mt-1">
                                      <div className="animate-spin h-3 w-3 border-2 border-current border-t-transparent rounded-full"></div>
                                    </div>
                                  ) : step.status === "completed" ? (
                                    <svg
                                      className="flex-shrink-0 w-4 h-4 mr-1.5 text-green-500"
                                      fill="currentColor"
                                      viewBox="0 0 20 20"
                                    >
                                      <path
                                        fillRule="evenodd"
                                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                                        clipRule="evenodd"
                                      ></path>
                                    </svg>
                                  ) : (
                                    <svg
                                      className="flex-shrink-0 w-4 h-4 mr-1.5 text-red-500"
                                      fill="currentColor"
                                      viewBox="0 0 20 20"
                                    >
                                      <path
                                        fillRule="evenodd"
                                        d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                                        clipRule="evenodd"
                                      ></path>
                                    </svg>
                                  )}
                                  <div className="text-xs">
                                    <span>{step.action}</span>
                                    {step.message && (
                                      <span className="block text-xs opacity-75 mt-0.5">
                                        {step.message}
                                      </span>
                                    )}
                                  </div>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                      {/* Results details */}
                      {message.type === "result" &&
                        message.status === "completed" &&
                        message.commandDetails && (
                          <div className="mt-4 space-y-4">
                            {/* Actions */}
                            {message.commandDetails.results &&
                              message.commandDetails.results.length > 0 && (
                                <div>
                                  <p className="text-sm font-medium mb-1">
                                    Actions:
                                  </p>
                                  <div className="text-xs border rounded-md overflow-hidden">
                                    <table className="min-w-full divide-y divide-gray-200">
                                      <thead className="bg-gray-50">
                                        <tr>
                                          <th className="px-2 py-1 text-left font-medium text-gray-500">
                                            Action
                                          </th>
                                          <th className="px-2 py-1 text-left font-medium text-gray-500">
                                            Status
                                          </th>
                                        </tr>
                                      </thead>
                                      <tbody className="bg-white divide-y divide-gray-200">
                                        {message.commandDetails.results.map(
                                          (result: any, index: number) => (
                                            <tr key={index}>
                                              <td className="px-2 py-1 whitespace-nowrap">
                                                {result.command}
                                              </td>
                                              <td className="px-2 py-1 whitespace-nowrap">
                                                <span
                                                  className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium ${
                                                    result.success
                                                      ? "bg-green-100 text-green-800"
                                                      : "bg-red-100 text-red-800"
                                                  }`}
                                                >
                                                  {result.success
                                                    ? "Success"
                                                    : "Failed"}
                                                </span>
                                              </td>
                                            </tr>
                                          )
                                        )}
                                      </tbody>
                                    </table>
                                  </div>
                                </div>
                              )}
                          </div>
                        )}

                      {/* Timestamp */}
                      <div className="text-xs opacity-70 mt-1">
                        {message.timestamp.toLocaleTimeString()}
                      </div>
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Command input */}
            <form onSubmit={handleSubmit} className="flex flex-col space-y-2">
              <Textarea
                placeholder="Enter a command (e.g., 'Go to google.com and search for browser automation')"
                value={userInput}
                onChange={(e) => setUserInput(e.target.value)}
                onKeyDown={handleKeyDown}
                className="min-h-[80px]"
                disabled={isExecutingCommand || showCaptchaPrompt}
              />
              <Button
                type="submit"
                disabled={
                  isExecutingCommand || !userInput.trim() || showCaptchaPrompt
                }
                className="self-end"
              >
                {isExecutingCommand ? "Processing..." : "Send Command"}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
