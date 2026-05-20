/**
 * spec_049: Bidirectional refs in GraphSidebar.
 *
 * No test runner is wired into the frontend yet (no jest / vitest), so this
 * file mirrors citations.test.ts: it documents the intended behaviour, is
 * tsc-clean, and is ready to run as-is once a runner is added.
 *
 * Each test exercises the bidirectional client helper against a mocked
 * fetch — that's the seam the GraphSidebar relies on, so verifying the
 * shape here covers the rendering paths (forwardlinks section, backlinks
 * section, isolated-node empty state).
 */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
declare function test(name: string, fn: () => void | Promise<void>): void;
declare function expect<T>(actual: T): {
  toEqual(expected: unknown): void;
  toBe(expected: unknown): void;
  toHaveLength(n: number): void;
};

import {
  fetchNeighborsBidirectional,
  type GraphNode,
} from "@/lib/graphClient";

function makeNode(id: string, title = id): GraphNode {
  return { id, title, axes: {}, in_degree: 0, out_degree: 0 };
}

type FetchInput = string | URL | Request;
function installFetchMock(
  byUrl: Record<string, { center: GraphNode; neighbors: GraphNode[]; hop: number }>,
) {
  (globalThis as { fetch: unknown }).fetch = async (input: FetchInput) => {
    const url = typeof input === "string" ? input : input.toString();
    for (const [needle, payload] of Object.entries(byUrl)) {
      if (url.includes(needle)) {
        return { ok: true, json: async () => payload, status: 200 } as Response;
      }
    }
    throw new Error(`unexpected fetch URL: ${url}`);
  };
}

test("renders forwardlinks section: direction=out populates forwardlinks", async () => {
  const center = makeNode("doc_001", "RAG patterns");
  installFetchMock({
    "direction=out": { center, neighbors: [makeNode("doc_002"), makeNode("doc_003")], hop: 1 },
    "direction=in": { center, neighbors: [], hop: 1 },
  });
  const data = await fetchNeighborsBidirectional("doc_001");
  expect(data.center.id).toBe("doc_001");
  expect(data.forwardlinks).toHaveLength(2);
  expect(data.backlinks).toHaveLength(0);
});

test("renders backlinks section: direction=in populates backlinks", async () => {
  const center = makeNode("doc_001", "RAG patterns");
  installFetchMock({
    "direction=out": { center, neighbors: [], hop: 1 },
    "direction=in": {
      center,
      neighbors: [makeNode("doc_007"), makeNode("doc_009")],
      hop: 1,
    },
  });
  const data = await fetchNeighborsBidirectional("doc_001");
  expect(data.forwardlinks).toHaveLength(0);
  expect(data.backlinks).toHaveLength(2);
});

test("isolated doc shows message: empty both sides ⇒ both arrays empty", async () => {
  const center = makeNode("doc_999", "lonely note");
  installFetchMock({
    "direction=out": { center, neighbors: [], hop: 1 },
    "direction=in": { center, neighbors: [], hop: 1 },
  });
  const data = await fetchNeighborsBidirectional("doc_999");
  // The sidebar renders the "独立ノード" message iff both arrays are empty.
  expect(data.forwardlinks).toEqual([]);
  expect(data.backlinks).toEqual([]);
});
