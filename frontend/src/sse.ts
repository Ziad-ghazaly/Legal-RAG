/** Parse Server-Sent Events frames from a text buffer (fetch-based SSE, so we can send the bearer token). */
export function parseSSE(buffer: string): { events: unknown[]; rest: string } {
  const frames = buffer.split("\n\n");
  const rest = frames.pop() ?? "";
  const events: unknown[] = [];
  for (const frame of frames) {
    const data = frame
      .split("\n")
      .filter((l) => l.startsWith("data:"))
      .map((l) => l.slice(5).trimStart())
      .join("\n");
    if (data) events.push(JSON.parse(data));
  }
  return { events, rest };
}
