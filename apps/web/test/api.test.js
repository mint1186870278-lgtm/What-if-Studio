import test from "node:test";
import assert from "node:assert/strict";
import { createVideoJob, parseSseDataLine, resolveApiBase, uploadVideoSource } from "../src/api.js";

test("resolveApiBase falls back to localhost in non-browser runtime", () => {
  assert.equal(resolveApiBase(), "http://localhost:3567");
});

test("resolveApiBase prefers same-origin mode in browser runtime", () => {
  const previousWindow = globalThis.window;
  globalThis.window = { location: { protocol: "http:", hostname: "localhost" } };
  try {
    assert.equal(resolveApiBase(), "");
  } finally {
    globalThis.window = previousWindow;
  }
});

test("parseSseDataLine parses valid data payload", () => {
  const payload = parseSseDataLine("event: turn\ndata: {\"event\":\"turn\",\"speaker\":\"A\"}");
  assert.deepEqual(payload, { event: "turn", speaker: "A" });
});

test("parseSseDataLine ignores malformed data payload", () => {
  assert.equal(parseSseDataLine("event: turn\ndata: {bad json"), null);
});

test("createVideoJob sends uploadId when provided", async () => {
  const originalFetch = globalThis.fetch;
  let payloadBody = null;
  globalThis.fetch = async (_url, options) => {
    payloadBody = JSON.parse(String(options?.body || "{}"));
    return {
      ok: true,
      async json() {
        return { job: { jobId: "job-1" } };
      }
    };
  };
  try {
    await createVideoJob("sess-1", { uploadId: "upload-1" });
    assert.equal(payloadBody?.sessionId, "sess-1");
    assert.equal(payloadBody?.sourceVideoUploadId, "upload-1");
    assert.equal(payloadBody?.sourceVideoPath, "");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("uploadVideoSource includes file body and encoded name header", async () => {
  const originalFetch = globalThis.fetch;
  let sentHeaders = null;
  let sentBody = null;
  globalThis.fetch = async (_url, options) => {
    sentHeaders = options?.headers;
    sentBody = options?.body;
    return {
      ok: true,
      async json() {
        return { upload: { uploadId: "upload-1", originalName: "clip.mp4" } };
      }
    };
  };
  try {
    const file = new globalThis.Blob(["video-data"], { type: "video/mp4" });
    Object.defineProperty(file, "name", { value: "clip one.mp4" });
    await uploadVideoSource(file);
    assert.equal(sentHeaders["x-file-name"], "clip%20one.mp4");
    assert.equal(sentBody, file);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
