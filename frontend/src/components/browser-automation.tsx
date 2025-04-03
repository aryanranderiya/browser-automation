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
  const [commandHistory, setCommandHistory] = useState<
    { input: string; result: string }[]
  >([]);

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

  // Function to execute a command
  const executeCommand = async () => {
    if (!sessionId || !userInput.trim()) return;

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

            // Also update session status to get latest screenshot
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

              // Add to command history
              setCommandHistory((prev) => [
                ...prev,
                {
                  input: userInput,
                  result: status.result?.explanation || "Command executed",
                },
              ]);

              // Clear input
              setUserInput("");
            }
          } catch (err) {
            console.error("Error checking command status:", err);
          }
        }, 1000);
      }
    } catch (err: any) {
      setError(`Failed to execute command: ${err.message}`);
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
    } catch (err: any) {
      setError(`Failed to signal captcha resolution: ${err.message}`);
    }
  };

  // Clean up interval on unmount
  useEffect(() => {
    return () => {
      if (statusCheckInterval.current) {
        clearInterval(statusCheckInterval.current);
      }
    };
  }, []);

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
                Start New Browser Session
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
                  Stop Browser Session
                </Button>
              </div>
            )}
          </div>

          {/* Command input */}
          {sessionId && (
            <div className="mb-6">
              <h3 className="text-md font-medium mb-2">Enter Command</h3>
              <div className="flex flex-col space-y-2">
                <Textarea
                  placeholder="Enter a natural language command (e.g., 'Go to google.com and search for browser automation')"
                  value={userInput}
                  onChange={(e) => setUserInput(e.target.value)}
                  className="min-h-[100px]"
                />
                <Button
                  onClick={executeCommand}
                  disabled={
                    isExecutingCommand || !userInput.trim() || showCaptchaPrompt
                  }
                >
                  Execute Command
                </Button>
              </div>
            </div>
          )}

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

      {/* Results display */}
      {sessionId && (
        <>
          {/* Current result */}
          {commandStatus?.status === "completed" && commandStatus.result && (
            <Card className="mb-8">
              <CardHeader>
                <CardTitle>Current Action</CardTitle>
                <CardDescription>
                  {commandStatus.task_status === "completed"
                    ? "Task completed successfully"
                    : "Task in progress"}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="mb-4">
                  <h3 className="text-md font-medium mb-2">Result</h3>
                  <p>{commandStatus.result.explanation}</p>
                </div>

                {/* Display screenshot */}
                {commandStatus.result.screenshot_path && (
                  <div className="mb-4">
                    <h3 className="text-md font-medium mb-2">Screenshot</h3>
                    <div className="border rounded-md overflow-hidden">
                      <img
                        src={`http://localhost:8000/static${commandStatus.result.screenshot_path}`}
                        alt="Browser screenshot"
                        className="w-full h-auto"
                      />
                    </div>
                  </div>
                )}

                {/* Actions history */}
                {commandStatus.result.results &&
                  commandStatus.result.results.length > 0 && (
                    <div>
                      <h3 className="text-md font-medium mb-2">
                        Actions Performed
                      </h3>
                      <div className="border rounded-md overflow-hidden">
                        <table className="min-w-full divide-y divide-gray-200">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Action
                              </th>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Status
                              </th>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Message
                              </th>
                            </tr>
                          </thead>
                          <tbody className="bg-white divide-y divide-gray-200">
                            {commandStatus.result.results.map(
                              (result, index) => (
                                <tr key={index}>
                                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                    {result.command}
                                  </td>
                                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                                    <span
                                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                        result.success
                                          ? "bg-green-100 text-green-800"
                                          : "bg-red-100 text-red-800"
                                      }`}
                                    >
                                      {result.success ? "Success" : "Failed"}
                                    </span>
                                  </td>
                                  <td className="px-6 py-4 text-sm text-gray-500">
                                    {result.message}
                                  </td>
                                </tr>
                              )
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
              </CardContent>
            </Card>
          )}

          {/* Command history */}
          {commandHistory.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Command History</CardTitle>
                <CardDescription>
                  Previous commands and their results
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {commandHistory.map((cmd, index) => (
                    <div key={index} className="border rounded-md p-4">
                      <div className="mb-2">
                        <span className="font-medium">Command:</span>{" "}
                        {cmd.input}
                      </div>
                      <div>
                        <span className="font-medium">Result:</span>{" "}
                        {cmd.result}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
