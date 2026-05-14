/**
 * Tests for frontend/src/lib/citations.ts — spec_039 code-fence handling.
 *
 * No test runner is wired into the frontend yet (no jest / vitest in
 * package.json), so this file exists to (a) document the intended
 * behaviour and (b) be ready to run as-is once a runner is added.
 * Minimal ambient declarations below keep `tsc --noEmit` green without
 * pulling in @types/jest.
 */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
declare function test(name: string, fn: () => void | Promise<void>): void;
declare function expect<T>(actual: T): {
  toEqual(expected: unknown): void;
};

import { parseCitations, Segment } from "@/lib/citations";

test("code fence skips marker", () => {
  const text = "Outside [1].\n```python\nx = arr[1]\n```\nAlso [2].";
  const segs = parseCitations(text);
  const citations = segs.filter((s) => s.kind === "citation");
  expect(citations).toEqual([
    { kind: "citation", n: 1 },
    { kind: "citation", n: 2 },
  ]);
});

test("inline code skips marker", () => {
  const text = "Use `arr[1]` then [1].";
  const segs = parseCitations(text);
  const citations = segs.filter((s) => s.kind === "citation");
  expect(citations).toEqual([{ kind: "citation", n: 1 }]);
});

test("fence with language identifier", () => {
  const text = "```ts\nconst x = arr[2];\n```\nCite [1].";
  const segs = parseCitations(text);
  const citations = segs.filter((s) => s.kind === "citation");
  expect(citations).toEqual([{ kind: "citation", n: 1 }]);
});

test("multiple fences", () => {
  const text = "Start [1].\n```\narr[1]\n```\nMiddle [2].\n```\narr[3]\n```\n";
  const segs = parseCitations(text);
  const citations = segs.filter((s) => s.kind === "citation");
  expect(citations).toEqual([
    { kind: "citation", n: 1 },
    { kind: "citation", n: 2 },
  ]);
});

test("no fence: regression check unchanged from v0.7", () => {
  const text = "A[1] B[2].";
  const segs: Segment[] = parseCitations(text);
  expect(segs).toEqual([
    { kind: "text", text: "A" },
    { kind: "citation", n: 1 },
    { kind: "text", text: " B" },
    { kind: "citation", n: 2 },
    { kind: "text", text: "." },
  ]);
});
