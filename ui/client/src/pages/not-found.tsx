/**
 * 404 surface. Theme-consistent and quiet: the code, and a way home.
 * Theme classes (dark + per-theme overrides) come from ThemeContext on the
 * document root, exactly like every other surface - nothing stamped here.
 * (The previous version was unthemed template scaffolding with dev-facing
 * copy - "Did you forget to add the page to the router?".)
 */
import { Link } from "wouter";

export default function NotFound() {
  return (
    <div className="min-h-screen w-full flex flex-col items-center justify-center gap-6 bg-background">
      <span className="font-mono text-sm tracking-[0.22em] text-muted-foreground">
        [ 404 ]
      </span>
      <Link
        href="/"
        className="font-mono text-xs tracking-[0.22em] text-primary hover:underline underline-offset-4"
      >
        NEXUS
      </Link>
    </div>
  );
}
