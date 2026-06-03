import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex items-center justify-center h-screen bg-bg-primary">
      <div className="text-center space-y-4 max-w-md px-6">
        <div className="text-6xl font-bold text-text-muted">404</div>
        <h1 className="text-xl font-semibold text-text-primary">
          Page not found
        </h1>
        <p className="text-sm text-text-muted">
          The page you are looking for does not exist.
        </p>
        <Link
          href="/"
          className="inline-block px-4 py-2 bg-accent hover:bg-accent-hover text-white text-sm font-medium rounded-lg transition-colors"
        >
          Go home
        </Link>
      </div>
    </div>
  );
}
