"use client";

import { useState, useEffect } from "react";
import { v4 as uuidv4 } from "uuid";
import { browserAgentAPI } from "@/lib/api";
import Image from "next/image";

export default function BrowserAutomation() {
  const [task, setTask] = useState("");
  const [startUrl, setStartUrl] = useState("https://www.google.com");
  const [isInteractive, setIsInteractive] = useState(false);
  const [maxSteps, setMaxSteps] = useState(10);
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);
  const [stepCount, setStepCount] = useState(0);

  // Clean up session on unmount
  useEffect(() => {
    return () => {
      if (sessionId) {
        browserAgentAPI
          .cleanupSession(sessionId)
          .catch((err) => console.error("Error cleaning up session:", err));
      }
    };
  }, [sessionId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    setScreenshotUrl(null);
    setIsLoading(true);

    try {
      const response = await browserAgentAPI.executeTask(
        task,
        startUrl,
        isInteractive,
        maxSteps
      );

      const data = response.data;
      setResult(data);

      if (data.session_id) {
        setSessionId(data.session_id);
        setStepCount(0);
      } else {
        setSessionId(null);
        if (data.screenshot_path) {
          // Convert backend path to URL
          const screenshotFileName = data.screenshot_path.split("/").pop();
          setScreenshotUrl(`/api/screenshots/${screenshotFileName}`);
        }
      }
    } catch (err: any) {
      setError(
        err.response?.data?.message || err.message || "An error occurred"
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleExecuteStep = async () => {
    if (!sessionId) return;

    setIsLoading(true);
    try {
      const response = await browserAgentAPI.executeStep(sessionId, 1);
      const data = response.data;
      setResult(data);
      setStepCount((prev) => prev + data.steps_completed);

      if (data.screenshot_path) {
        const screenshotFileName = data.screenshot_path.split("/").pop();
        setScreenshotUrl(`/api/screenshots/${screenshotFileName}`);
      }

      // If task is complete, clean up the session
      if (data.is_complete) {
        setSessionId(null);
      }
    } catch (err: any) {
      setError(
        err.response?.data?.message || err.message || "An error occurred"
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleFinishSession = async () => {
    if (!sessionId) return;

    setIsLoading(true);
    try {
      await browserAgentAPI.cleanupSession(sessionId);
      setSessionId(null);
    } catch (err: any) {
      setError(
        err.response?.data?.message || err.message || "Error ending session"
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-6">Browser Automation Agent</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="space-y-6">
          <form
            onSubmit={handleSubmit}
            className="space-y-4 bg-white dark:bg-gray-900 p-6 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm"
          >
            <div>
              <label htmlFor="task" className="block text-sm font-medium mb-1">
                Task Description
              </label>
              <textarea
                id="task"
                className="w-full p-3 border border-gray-300 dark:border-gray-700 rounded-md dark:bg-gray-800"
                value={task}
                onChange={(e) => setTask(e.target.value)}
                placeholder="Describe what you want the browser to do..."
                rows={4}
                required
              />
            </div>

            <div>
              <label
                htmlFor="startUrl"
                className="block text-sm font-medium mb-1"
              >
                Start URL
              </label>
              <input
                id="startUrl"
                type="url"
                className="w-full p-3 border border-gray-300 dark:border-gray-700 rounded-md dark:bg-gray-800"
                value={startUrl}
                onChange={(e) => setStartUrl(e.target.value)}
                placeholder="https://example.com"
              />
            </div>

            <div className="flex items-center">
              <input
                id="interactive"
                type="checkbox"
                className="h-4 w-4 text-blue-600 border-gray-300 rounded"
                checked={isInteractive}
                onChange={(e) => setIsInteractive(e.target.checked)}
              />
              <label htmlFor="interactive" className="ml-2 block text-sm">
                Interactive Mode (Step-by-step)
              </label>
            </div>

            <div>
              <label
                htmlFor="maxSteps"
                className="block text-sm font-medium mb-1"
              >
                Maximum Steps: {maxSteps}
              </label>
              <input
                id="maxSteps"
                type="range"
                min="1"
                max="30"
                className="w-full"
                value={maxSteps}
                onChange={(e) => setMaxSteps(parseInt(e.target.value))}
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={isLoading}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-md disabled:opacity-50"
              >
                {isLoading && !sessionId ? "Starting..." : "Start Browser Task"}
              </button>
            </div>
          </form>

          {sessionId && (
            <div className="bg-white dark:bg-gray-900 p-6 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm">
              <h3 className="text-lg font-semibold mb-3">
                Interactive Session
              </h3>
              <p className="mb-3">Steps executed: {stepCount}</p>

              <div className="flex space-x-3">
                <button
                  onClick={handleExecuteStep}
                  disabled={isLoading}
                  className="bg-green-600 hover:bg-green-700 text-white font-medium py-2 px-4 rounded-md disabled:opacity-50"
                >
                  {isLoading ? "Running Step..." : "Execute Next Step"}
                </button>

                <button
                  onClick={handleFinishSession}
                  className="bg-red-600 hover:bg-red-700 text-white font-medium py-2 px-4 rounded-md"
                >
                  End Session
                </button>
              </div>
            </div>
          )}

          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4 rounded-md text-red-700 dark:text-red-300">
              <h3 className="font-semibold mb-1">Error</h3>
              <p>{error}</p>
            </div>
          )}

          {result && (
            <div className="bg-white dark:bg-gray-900 p-6 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm">
              <h3 className="text-lg font-semibold mb-3">Result</h3>
              <pre className="bg-gray-100 dark:bg-gray-800 p-3 rounded-md overflow-auto text-sm">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          )}
        </div>

        <div>
          {screenshotUrl ? (
            <div className="bg-white dark:bg-gray-900 p-6 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm">
              <h3 className="text-lg font-semibold mb-3">Browser Screenshot</h3>
              <div className="border border-gray-300 dark:border-gray-700 rounded-md overflow-hidden">
                <img
                  src={screenshotUrl}
                  alt="Browser Screenshot"
                  className="w-full h-auto"
                />
              </div>
            </div>
          ) : (
            <div className="bg-white dark:bg-gray-900 p-6 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm flex items-center justify-center h-96">
              <p className="text-gray-500 dark:text-gray-400">
                Screenshot will appear here once the browser task is executed
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
