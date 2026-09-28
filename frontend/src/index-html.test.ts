import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const root = resolve(__dirname, "..");
const html = readFileSync(resolve(root, "index.html"), "utf8");

describe("index.html public metadata", () => {
  it("declares a favicon that ships in public/", () => {
    const iconPath = html.match(/<link rel="icon"[^>]*href="\/([^"]+)"/)?.[1] ?? "";
    expect(iconPath).not.toBe("");
    expect(existsSync(resolve(root, "public", iconPath))).toBe(true);
  });

  it("gives shared links a real title and description card", () => {
    expect(html).toMatch(/<meta property="og:title" content="[^"]+"/);
    expect(html).toMatch(/<meta\s+property="og:description"\s+content="[^"]+"/);
    expect(html).toMatch(/<meta name="twitter:card" content="summary"/);
  });
});

describe("dark-mode primary text contrast", () => {
  it("routes small primary-colored text through a token that meets WCAG AA on dark cards", () => {
    const css = readFileSync(resolve(__dirname, "index.css"), "utf8");
    expect(css).toMatch(/\.dark \{[\s\S]*?--primary-text:\s*#956af7;/);
    expect(css).toMatch(/\.dark \.text-primary\s*\{\s*color:\s*var\(--primary-text\);/);
    expect(css).toMatch(/\.cp-kicker\s*\{[^}]*color:\s*var\(--primary-text\);/);
  });
});
