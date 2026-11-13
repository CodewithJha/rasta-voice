import { createServer } from "node:http";
import type { AddressInfo } from "node:net";

import { afterEach, describe, expect, it } from "vitest";

import { fetchWithTimeout } from "../../src/http";

let close: (() => Promise<void>) | undefined;

afterEach(async () => {
  if (close) {
    await close();
    close = undefined;
  }
});

function listen(
  handler: (req: import("node:http").IncomingMessage, res: import("node:http").ServerResponse) => void,
): Promise<string> {
  const server = createServer(handler);
  close = () =>
    new Promise((resolve, reject) => {
      server.close((error) => (error ? reject(error) : resolve()));
    });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address() as AddressInfo;
      resolve(`http://127.0.0.1:${address.port}/`);
    });
  });
}

describe("fetchWithTimeout", () => {
  it("aborts when headers arrive promptly but the body never ends", async () => {
    const url = await listen((_req, res) => {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.write('{"ok":');
    });
    const started = Date.now();
    await expect(fetchWithTimeout(url, {}, 200)).rejects.toSatisfy((error: unknown) => {
      return error instanceof DOMException
        ? error.name === "AbortError"
        : error instanceof Error && /abort/i.test(error.message);
    });
    const elapsed = Date.now() - started;
    expect(elapsed).toBeGreaterThanOrEqual(180);
    expect(elapsed).toBeLessThan(450);
  });

  it("returns the completed body when it arrives inside the deadline", async () => {
    const url = await listen((_req, res) => {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end('{"ok":true}');
    });
    const { response, text } = await fetchWithTimeout(url, {}, 500);
    expect(response.status).toBe(200);
    expect(text).toBe('{"ok":true}');
  });
});
