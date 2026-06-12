/**
 * Relocatifier worker.
 *
 * Serves the static app from the ASSETS binding, except for `/data/*`, which it
 * range-serves from the R2 `relocatifier-data` bucket. PMTiles reads the suburb
 * tiles via HTTP Range requests, so faithful 206/Content-Range handling here is
 * the whole reason the worker exists (ADR-0005).
 */

interface Env {
  ASSETS: Fetcher;
  DATA: R2Bucket;
}

const DATA_PREFIX = "/data/";

function contentTypeFor(key: string): string {
  if (key.endsWith(".json")) return "application/json";
  if (key.endsWith(".pmtiles")) return "application/octet-stream";
  return "application/octet-stream";
}

function cacheControlFor(key: string): string {
  // Data refreshes quarterly. metrics.json is small and re-fetched on load, so
  // keep it short-lived; pmtiles is large and immutable between publishes.
  if (key.endsWith(".json")) return "public, max-age=300, must-revalidate";
  return "public, max-age=86400";
}

async function serveData(request: Request, env: Env, key: string): Promise<Response> {
  // R2 accepts the request Headers directly for both Range and conditional gets.
  const object = await env.DATA.get(key, {
    range: request.headers,
    onlyIf: request.headers,
  });

  if (object === null) {
    return new Response("Not found", { status: 404 });
  }

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("Content-Type", contentTypeFor(key));
  headers.set("Cache-Control", cacheControlFor(key));
  headers.set("ETag", object.httpEtag);
  headers.set("Accept-Ranges", "bytes");

  // `body` is absent when the object matched an onlyIf precondition (304) or
  // when this is a HEAD-style metadata-only result.
  if (!("body" in object) || object.body === undefined) {
    return new Response(null, { status: 304, headers });
  }

  const range = object.range;
  if (range !== undefined && "offset" in range) {
    const offset = range.offset ?? 0;
    const length = range.length ?? object.size - offset;
    const end = offset + length - 1;
    headers.set("Content-Range", `bytes ${offset}-${end}/${object.size}`);
    headers.set("Content-Length", String(length));
    return new Response(object.body, { status: 206, headers });
  }

  headers.set("Content-Length", String(object.size));
  return new Response(request.method === "HEAD" ? null : object.body, {
    status: 200,
    headers,
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed", {
        status: 405,
        headers: { Allow: "GET, HEAD" },
      });
    }

    const url = new URL(request.url);
    if (url.pathname.startsWith(DATA_PREFIX)) {
      const key = decodeURIComponent(url.pathname.slice(DATA_PREFIX.length));
      if (key === "") {
        return new Response("Not found", { status: 404 });
      }
      return serveData(request, env, key);
    }

    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
