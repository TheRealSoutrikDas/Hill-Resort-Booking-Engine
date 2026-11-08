"use client";

import Link from "next/link";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="page" style={{ paddingBlock: "var(--space-6)" }}>
      <h1>This page could not be shown</h1>
      <p>Something went wrong while loading it. Try again, or go back to the home page.</p>
      <p>
        <button type="button" className="button" onClick={reset}>
          Try again
        </button>{" "}
        <Link href="/">Go to the home page</Link>
      </p>
    </div>
  );
}
