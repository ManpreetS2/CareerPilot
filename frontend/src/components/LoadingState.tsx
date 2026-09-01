export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-4 text-sm text-muted-foreground">
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent"
        aria-hidden
      />
      <span>{label}</span>
    </div>
  );
}
