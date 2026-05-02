import assert from "node:assert/strict";
import test from "node:test";
import { streamDiscussion, watchGatewayInvocations, watchVideoJob } from "../src/api.js";

test("streamDiscussion emits parsed turn and done events", async () => {
  const originalFetch = globalThis.fetch;
  const chunks = ['event: turn\ndata: {"event":"turn","speaker":"A"}\n\n', 'event: done\ndata: {"event":"done"}\n\n'];
  const encoder = new TextEncoder();
  globalThis.fetch = async () => ({
    ok: true,
    body: {
      getReader() {
        let index = 0;
        return {
          async read() {
            if (index >= chunks.length) return { done: true, value: undefined };
            const value = encoder.encode(chunks[index]);
            index += 1;
            return { done: false, value };
          }
        };
      }
    }
  });

  const events = [];
  try {
    await streamDiscussion("sess-1", (evt) => events.push(evt));
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(events, [{ event: "turn", speaker: "A" }, { event: "done" }]);
});

test("watchVideoJob reports disconnect error and closes source", () => {
  const OriginalEventSource = globalThis.EventSource;
  const instances = [];
  class MockEventSource {
    constructor() {
      this.closed = false;
      this.listeners = new Map();
      this.onerror = null;
      instances.push(this);
    }

    addEventListener(name, handler) {
      this.listeners.set(name, handler);
    }

    close() {
      this.closed = true;
    }

    emit(name, data) {
      const handler = this.listeners.get(name);
      if (handler) handler({ data: JSON.stringify(data) });
    }
  }
  globalThis.EventSource = MockEventSource;

  const received = [];
  let disconnected = false;
  try {
    const unsubscribe = watchVideoJob(
      "job-1",
      (evt) => {
        received.push(evt);
      },
      {
        onDisconnect: () => {
          disconnected = true;
        }
      }
    );
    const source = instances[0];
    source.onerror();
    assert.equal(disconnected, true);
    assert.equal(received.at(-1)?.event, "error");
    unsubscribe();
    assert.equal(source.closed, true);
  } finally {
    globalThis.EventSource = OriginalEventSource;
  }
});

test("watchGatewayInvocations pushes invocation and disconnect event", () => {
  const OriginalEventSource = globalThis.EventSource;
  const instances = [];
  class MockEventSource {
    constructor() {
      this.listeners = new Map();
      this.onerror = null;
      this.closed = false;
      instances.push(this);
    }

    addEventListener(name, handler) {
      this.listeners.set(name, handler);
    }

    close() {
      this.closed = true;
    }

    emit(name, data) {
      const handler = this.listeners.get(name);
      if (handler) handler({ data: JSON.stringify(data) });
    }
  }
  globalThis.EventSource = MockEventSource;

  const received = [];
  let disconnected = false;
  try {
    const stop = watchGatewayInvocations(
      (evt) => {
        received.push(evt);
      },
      {
        onDisconnect: () => {
          disconnected = true;
        }
      }
    );
    const source = instances[0];
    source.emit("invocation", { event: "invocation", status: "ok" });
    source.onerror();
    assert.equal(received[0]?.event, "invocation");
    assert.equal(received.at(-1)?.event, "error");
    assert.equal(disconnected, true);
    stop();
    assert.equal(source.closed, true);
  } finally {
    globalThis.EventSource = OriginalEventSource;
  }
});
