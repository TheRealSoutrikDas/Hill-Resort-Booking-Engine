import Link from "next/link";

export default function NotFound() {
  return (
    <div className="page" style={{ paddingBlock: "var(--space-6)" }}>
      <h1>Page not found</h1>
      <p>The address may be mistyped, or the page may have moved.</p>
      <p>
        <Link href="/">Go to the home page</Link>
      </p>
    </div>
  );
}
