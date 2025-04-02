"use client";

import { useState } from "react";
import { BrowserConfig } from "@/lib/types";
import { cn } from "@/lib/utils";

interface SessionControlsProps {
  onStartSession: (config: BrowserConfig) => void;
  onStopSession: () => void;
  onTakeScreenshot: () => void;
  onGetStatus: () => void;
  isSessionActive: boolean;
  isProcessing: boolean;
  sessionId?: string;
  statusMessage?: string;
}

export function SessionControls({
  onStartSession,
  onStopSession,
  onTakeScreenshot,
  onGetStatus,
  isSessionActive,
  isProcessing,
  sessionId,
  statusMessage,
}: SessionControlsProps) {
  const [browserType, setBrowserType] =
    useState<BrowserConfig["browser_type"]>("chromium");
  const [headless, setHeadless] = useState(false);
  const [timeout, setTimeout] = useState(30);

  const handleStartSession = () => {
    onStartSession({
      browser_type: browserType,
      headless,
      timeout,
    });
  };

  return (
    <div className="border border-gray-200 dark:border-gray-800 rounded-lg p-4 bg-white dark:bg-gray-900 shadow-sm">
      <h2 className="text-lg font-semibold mb-4">Browser Session Controls</h2>

      <div
        className={cn(
          "mb-6",
          isSessionActive && "opacity-50 pointer-events-none"
        )}
      >
        <h3 className="font-medium mb-3">Session Configuration</h3>

        <div className="grid gap-4 grid-cols-1 md:grid-cols-3">
          <div>
            <label className="block text-sm font-medium mb-1">
              Browser Type
            </label>
            <select
              value={browserType}
              onChange={(e) =>
                setBrowserType(e.target.value as BrowserConfig["browser_type"])
              }
              disabled={isSessionActive || isProcessing}
              className="w-full p-2 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-800"
            >
              <option value="chromium">Chromium</option>
              <option value="firefox">Firefox</option>
              <option value="webkit">WebKit</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">
              Timeout (seconds)
            </label>
            <input
              type="number"
              value={timeout}
              onChange={(e) => setTimeout(parseInt(e.target.value) || 30)}
              min={5}
              max={120}
              disabled={isSessionActive || isProcessing}
              className="w-full p-2 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-800"
            />
          </div>

          <div className="flex items-center">
            <label className="flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={headless}
                onChange={(e) => setHeadless(e.target.checked)}
                disabled={isSessionActive || isProcessing}
                className="form-checkbox h-5 w-5 text-blue-500 mr-2"
              />
              <span className="text-sm font-medium">Headless Mode</span>
            </label>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        {!isSessionActive ? (
          <button
            onClick={handleStartSession}
            disabled={isProcessing}
            className="bg-green-500 hover:bg-green-600 text-white px-4 py-2 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Start Session
          </button>
        ) : (
          <>
            <button
              onClick={onStopSession}
              disabled={isProcessing}
              className="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Stop Session
            </button>

            <button
              onClick={onTakeScreenshot}
              disabled={isProcessing}
              className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Take Screenshot
            </button>

            <button
              onClick={onGetStatus}
              disabled={isProcessing}
              className="bg-gray-500 hover:bg-gray-600 text-white px-4 py-2 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Get Status
            </button>
          </>
        )}
      </div>

      {isSessionActive && sessionId && (
        <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-800 rounded text-sm">
          <p className="font-medium">
            Session ID: <span className="font-mono">{sessionId}</span>
          </p>
          {statusMessage && <p className="mt-1">{statusMessage}</p>}
        </div>
      )}
    </div>
  );
}
