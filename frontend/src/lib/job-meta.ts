function normalizeMetaValue(value: string): string {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

/** Join visible job metadata, dropping adjacent duplicates such as Remote · Remote. */
export function formatJobCardMeta(parts: Array<string | null | undefined>): string {
  const visible: string[] = [];
  for (const part of parts) {
    if (!part) continue;
    const trimmed = part.trim();
    if (!trimmed) continue;
    const previous = visible[visible.length - 1];
    if (previous && normalizeMetaValue(previous) === normalizeMetaValue(trimmed)) continue;
    visible.push(trimmed);
  }
  return visible.join(" · ");
}
