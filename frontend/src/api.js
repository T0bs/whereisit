// Thin fetch wrapper. Reads VITE_API_URL (default http://127.0.0.1:8000) and
// VITE_WHEREISIT_TOKEN at build time. Throws ApiError on 4xx/5xx with the
// raw payload preserved so callers can inspect.

const API_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const TOKEN = import.meta.env.VITE_WHEREISIT_TOKEN || "";

export class ApiError extends Error {
  constructor(status, payload, message) {
    super(message || `API ${status}`);
    this.status = status;
    this.payload = payload;
  }
}

async function request(method, path, { body, params } = {}) {
  let url = API_URL + path;
  if (params) {
    const query = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") query.set(k, v);
    }
    const s = query.toString();
    if (s) url += "?" + s;
  }
  const headers = { Accept: "application/json" };
  if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  let payload = null;
  if (response.status !== 204) {
    const text = await response.text();
    payload = text ? safeJson(text) : null;
  }

  if (!response.ok) {
    const message =
      typeof payload === "object" && payload?.detail
        ? typeof payload.detail === "string"
          ? payload.detail
          : payload.detail.message || JSON.stringify(payload.detail)
        : `API ${response.status}`;
    throw new ApiError(response.status, payload, message);
  }
  return payload;
}

function safeJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const api = {
  health: () => request("GET", "/health"),
  // nodes
  listRootNodes: () => request("GET", "/nodes", { params: { parent: "root", limit: 200 } }),
  getChildren: (id) => request("GET", `/nodes/${id}/children`, { params: { limit: 200 } }),
  getNode: (id) => request("GET", `/nodes/${id}`),
  getPath: (id) => request("GET", `/nodes/${id}/path`),
  createNode: (body) => request("POST", "/nodes", { body }),
  updateNode: (id, body) => request("PATCH", `/nodes/${id}`, { body }),
  deleteNode: (id, cascade = false) =>
    request("DELETE", `/nodes/${id}`, { params: { cascade: cascade ? "true" : undefined } }),
  // tags + properties
  addTag: (nodeId, name) => request("POST", `/nodes/${nodeId}/tags`, { body: { name } }),
  removeTag: (nodeId, tagId) => request("DELETE", `/nodes/${nodeId}/tags/${tagId}`),
  listProperties: (nodeId) => request("GET", `/nodes/${nodeId}/properties`),
  setProperty: (nodeId, key, value, value_type) =>
    request("PUT", `/nodes/${nodeId}/properties/${key}`, { body: { value, value_type } }),
  deleteProperty: (nodeId, key) => request("DELETE", `/nodes/${nodeId}/properties/${key}`),
  // kinds + tags
  listKinds: () => request("GET", "/kinds", { params: { limit: 200 } }),
  listTags: () => request("GET", "/tags", { params: { limit: 200 } }),
  // search
  search: ({ q, mode = "keyword", kind, tag, parent, limit = 30 }) =>
    request("GET", "/search", { params: { q, mode, kind, tag, parent, limit } }),
  // ai
  ask: (body) => request("POST", "/ai/ask", { body }),
  suggestPlacement: (body) => request("POST", "/ai/suggest-placement", { body }),
  // embeddings
  embeddingsStatus: () => request("GET", "/embeddings"),
  backfillEmbeddings: (body = {}) => request("POST", "/embeddings/backfill", { body }),
};
