"use client";

import { useState, useEffect } from "react";
import { Message } from "@/lib/types";
import { cn } from "@/lib/utils";

interface MessageItemProps {
  message: Message;
  imageBaseUrl?: string;
}

export function MessageItem({
  message,
  imageBaseUrl = "http://localhost:8000",
}: MessageItemProps) {
  const [expandedImage, setExpandedImage] = useState<boolean>(false);
  const [expandedError, setExpandedError] = useState<boolean>(false);

  const getMessageColor = () => {
    switch (message.type) {
      case "user":
        return "bg-blue-100 dark:bg-blue-950";
      case "system":
        return "bg-gray-100 dark:bg-gray-800";
      case "result":
        return "bg-green-100 dark:bg-green-950";
      case "error":
        return "bg-red-100 dark:bg-red-950";
      default:
        return "bg-gray-100 dark:bg-gray-800";
    }
  };

  // Format error details in a readable way
  const formatErrorDetails = (errorDetails: any) => {
    if (!errorDetails) return null;

    return (
      <div className="mt-2 text-sm">
        {errorDetails.error_type && (
          <div>
            <span className="font-semibold">Error Type:</span>{" "}
            {errorDetails.error_type}
          </div>
        )}
        {errorDetails.error_message && (
          <div>
            <span className="font-semibold">Error Message:</span>{" "}
            {errorDetails.error_message}
          </div>
        )}
        {errorDetails.action && (
          <div>
            <span className="font-semibold">Failed Action:</span>{" "}
            {errorDetails.action}
          </div>
        )}
        {errorDetails.user_command && (
          <div>
            <span className="font-semibold">Command:</span>{" "}
            {errorDetails.user_command}
          </div>
        )}
        {errorDetails.parameters && (
          <div>
            <span className="font-semibold">Parameters:</span>
            <pre className="mt-1 p-2 bg-gray-200 dark:bg-gray-800 rounded text-xs overflow-auto">
              {JSON.stringify(errorDetails.parameters, null, 2)}
            </pre>
          </div>
        )}
      </div>
    );
  };

  // Check if there are error details to display
  const hasErrorDetails =
    message.type === "error" && message.metadata?.errorDetails;

  return (
    <div className={cn("p-4 rounded-lg mb-4", getMessageColor())}>
      <div className="flex justify-between items-start mb-2">
        <span className="font-bold">
          {message.type === "user"
            ? "You"
            : message.type === "result"
            ? "Result"
            : message.type === "error"
            ? "Error"
            : "System"}
        </span>
        <span className="text-xs text-gray-500">
          {message.timestamp.toLocaleTimeString()}
        </span>
      </div>

      <div className="whitespace-pre-wrap">{message.content}</div>

      {/* Error Details Section */}
      {hasErrorDetails && (
        <div className="mt-3 p-3 bg-red-50 dark:bg-red-900/30 rounded border border-red-200 dark:border-red-800">
          <div
            className="flex justify-between items-center cursor-pointer"
            onClick={() => setExpandedError(!expandedError)}
          >
            <span className="font-semibold text-sm">Error Details</span>
            <span className="text-xs">
              {expandedError ? "Hide Details" : "Show Details"}
            </span>
          </div>

          {expandedError && formatErrorDetails(message.metadata.errorDetails)}
        </div>
      )}

      {message.metadata?.screenshot_path && (
        <div className="mt-4">
          <div
            className="cursor-pointer hover:opacity-90 transition-opacity"
            onClick={() => setExpandedImage(!expandedImage)}
          >
            <img
              src={`${imageBaseUrl}${message.metadata.screenshot_path}`}
              alt="Screenshot"
              className={cn(
                "rounded-md border border-gray-300 dark:border-gray-700",
                expandedImage ? "w-full" : "w-64"
              )}
            />
            <div className="text-xs text-gray-500 mt-1">
              {expandedImage ? "Click to shrink" : "Click to expand"}
            </div>
          </div>
        </div>
      )}

      {message.metadata?.result && (
        <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-900 rounded border border-gray-200 dark:border-gray-800">
          <p className="font-semibold text-sm mb-1">Result Data:</p>
          <pre className="text-xs overflow-auto max-h-40">
            {JSON.stringify(message.metadata.result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
