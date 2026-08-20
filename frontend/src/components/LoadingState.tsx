export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="card flex items-center gap-3 p-6 text-sm text-ink-600 dark:text-ink-300">
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-accent-500 border-t-transparent"
        aria-hidden
      />
      <span>{label}</span>
    </div>
  );
}
