"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex items-center justify-center h-screen bg-bg-primary">
      <div className="text-center space-y-4 max-w-md px-6">
        <div className="text-4xl font-bold text-text-muted">oops</div>
        <h1 className="text-xl font-semibold text-text-primary">
          Something went wrong
        </h1>
        <p className="text-sm text-text-muted">
          {error.message || "An unexpected error occurred."}
        </p>
        <button
          onClick={reset}
          className="px-4 py-2 bg-accent hover:bg-accent-hover text-white text-sm font-medium rounded-lg transition-colors"
        >
          Try again
        </button>
        <p className="text-xs text-text-muted">
          dipeen v0.1.0
        </p>
      </div>
    </div>
  );
}
