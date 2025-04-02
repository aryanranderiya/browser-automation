"use client";

import { useState, useEffect } from "react";
import { browserAgentAPI } from "@/lib/api";

interface BrowserAgentState {
  task: string;
  startUrl: string;
  isInteractive: boolean;
  maxSteps: number;
  isLoading: boolean;
  sessionId: string | null;
  result: any;
  error: string | null;
  stepCount: number;
  isComplete: boolean;
}

export default function BrowserAgent() {
  const [state, setState] = useState<BrowserAgentState>({
    task: "",
    startUrl: "https://www.google.com",
    isInteractive: false,
    maxSteps: 10,
    isLoading: false,
    sessionId: null,
    result: null,
    error: null,
    stepCount: 0,
    isComplete: false,
  });

  // Clean up session on unmount
  useEffect(() => {
    return () => {
      if (state.sessionId) {
        browserAgentAPI
          .cleanupSession(state.sessionId)
          .catch((err) => console.error("Error cleaning up session:", err));
      }
    };
  }, [state.sessionId]);

  const updateState = (newState: Partial<BrowserAgentState>) => {
    setState((prev) => ({ ...prev, ...newState }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    updateState({ error: null, result: null, isLoading: true });

    try {
      const response = await browserAgentAPI.executeTask(state.task, {
        startUrl: state.startUrl,
        interactive: state.isInteractive,
        maxSteps: state.maxSteps,
      });

      const data = response.data;
      updateState({ result: data });

      if (data.session_id) {
        updateState({
          sessionId: data.session_id,
          stepCount: 0,
        });
      } else {
        updateState({
          sessionId: null,
          isComplete: data.is_complete || false,
        });
      }
    } catch (err: any) {
      updateState({
        error:
          err.response?.data?.message || err.message || "An error occurred",
      });
    } finally {
      updateState({ isLoading: false });
    }
  };

  const handleExecuteStep = async () => {
    if (!state.sessionId) return;

    updateState({ isLoading: true });
    try {
      const response = await browserAgentAPI.executeStep(state.sessionId, 1);
      const data = response.data;
      updateState({
        result: data,
        stepCount: state.stepCount + data.steps_completed,
        isComplete: data.is_complete || false,
      });

      // If task is complete, clean up the session
      if (data.is_complete) {
        updateState({ sessionId: null });
      }
    } catch (err: any) {
      updateState({
        error:
          err.response?.data?.message || err.message || "An error occurred",
      });
    } finally {
      updateState({ isLoading: false });
    }
  };

  const handleFinishSession = async () => {
    if (!state.sessionId) return;

    updateState({ isLoading: true });
    try {
      await browserAgentAPI.cleanupSession(state.sessionId);
      updateState({ sessionId: null });
    } catch (err: any) {
      updateState({
        error:
          err.response?.data?.message || err.message || "Error ending session",
      });
    } finally {
      updateState({ isLoading: false });
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
                value={state.task}
                onChange={(e) => updateState({ task: e.target.value })}
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
                value={state.startUrl}
                onChange={(e) => updateState({ startUrl: e.target.value })}
                placeholder="https://example.com"
              />
            </div>

            <div className="flex items-center">
              <input
                id="interactive"
                type="checkbox"
                className="h-4 w-4 text-blue-600 border-gray-300 rounded"
                checked={state.isInteractive}
                onChange={(e) =>
                  updateState({ isInteractive: e.target.checked })
                }
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
                Maximum Steps: {state.maxSteps}
              </label>
              <input
                id="maxSteps"
                type="range"
                min="1"
                max="30"
                className="w-full"
                value={state.maxSteps}
                onChange={(e) =>
                  updateState({ maxSteps: parseInt(e.target.value) })
                }
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={state.isLoading}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-md disabled:opacity-50"
              >
                {state.isLoading && !state.sessionId
                  ? "Starting..."
                  : "Start Browser Task"}
              </button>
            </div>
          </form>

          {state.sessionId && (
            <div className="bg-white dark:bg-gray-900 p-6 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm">
              <h3 className="text-lg font-semibold mb-3">
                Interactive Session
              </h3>
              <p className="mb-3">Steps executed: {state.stepCount}</p>

              <div className="flex space-x-3">
                <button
                  onClick={handleExecuteStep}
                  disabled={state.isLoading}
                  className="bg-green-600 hover:bg-green-700 text-white font-medium py-2 px-4 rounded-md disabled:opacity-50"
                >
                  {state.isLoading ? "Running Step..." : "Execute Next Step"}
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

          {state.error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4 rounded-md text-red-700 dark:text-red-300">
              <h3 className="font-semibold mb-1">Error</h3>
              <p>{state.error}</p>
            </div>
          )}

          {state.result && (
            <div className="bg-white dark:bg-gray-900 p-6 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm">
              <h3 className="text-lg font-semibold mb-3">Result</h3>
              <pre className="bg-gray-100 dark:bg-gray-800 p-3 rounded-md overflow-auto text-sm">
                {JSON.stringify(state.result, null, 2)}
              </pre>
            </div>
          )}
        </div>

        <div>
          <div className="bg-white dark:bg-gray-900 p-6 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm">
            <h3 className="text-lg font-semibold mb-3">Browser Agent Status</h3>

            {state.sessionId ? (
              <div className="space-y-3">
                <StatusItem label="Session ID" value={state.sessionId} />
                <StatusItem
                  label="Mode"
                  value={state.isInteractive ? "Interactive" : "Autonomous"}
                />
                <StatusItem
                  label="Steps Completed"
                  value={state.stepCount.toString()}
                />
                <StatusItem
                  label="Status"
                  value={
                    state.isComplete
                      ? "Complete"
                      : state.sessionId
                      ? "Active"
                      : "Idle"
                  }
                  valueClass={getStatusClass(
                    state.isComplete,
                    !!state.sessionId
                  )}
                />

                {state.result?.current_url && (
                  <StatusItem
                    label="Current URL"
                    value={state.result.current_url}
                  />
                )}

                {state.result?.details?.memory && (
                  <div className="mt-4">
                    <h4 className="font-medium text-sm mb-2">Memory Summary</h4>
                    <div className="bg-gray-100 dark:bg-gray-800 p-3 rounded-md">
                      {state.result.details.memory}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-gray-500 dark:text-gray-400 h-32 flex items-center justify-center">
                <p>No active session</p>
              </div>
            )}
          </div>

          {state.result?.details && (
            <div className="bg-white dark:bg-gray-900 p-6 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm mt-6">
              <h3 className="text-lg font-semibold mb-3">Browser State</h3>
              <div className="space-y-2">
                {state.result.final_url && (
                  <StatusItem
                    label="Final URL"
                    value={state.result.final_url}
                  />
                )}
                <StatusItem
                  label="Task Status"
                  value={state.isComplete ? "Complete" : "In Progress"}
                  valueClass={
                    state.isComplete ? "text-green-600" : "text-yellow-600"
                  }
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface StatusItemProps {
  label: string;
  value: string;
  valueClass?: string;
}

function StatusItem({ label, value, valueClass = "" }: StatusItemProps) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-600 dark:text-gray-400">{label}:</span>
      <span className={valueClass || "font-medium"}>{value}</span>
    </div>
  );
}

function getStatusClass(isComplete: boolean, isActive: boolean): string {
  if (isComplete) return "text-green-600 font-medium";
  if (isActive) return "text-blue-600 font-medium";
  return "text-gray-600 font-medium";
}
