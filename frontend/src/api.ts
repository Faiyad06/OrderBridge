// Thin fetch wrapper. Session is an HttpOnly cookie; state changes carry the CSRF header.
export type ApiError = { code: string; user_message: string; field_errors?: Record<string, string>; request_id?: string; status: number };

let csrfToken = "";
export const setCsrf = (t: string) => { csrfToken = t; };

async function call<T>(method: string, url: string, body?: unknown, extraHeaders: Record<string, string> = {}): Promise<T> {
  const headers: Record<string, string> = { ...extraHeaders };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  const res = await fetch(url, { method, headers, body: payload, credentials: "same-origin" });
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await res.json() : await res.text();
  if (!res.ok) {
    const err = (isJson ? data : { code: "FAILED", user_message: String(data) }) as ApiError;
    err.status = res.status;
    throw err;
  }
  return data as T;
}

export const api = {
  get: <T,>(url: string) => call<T>("GET", url),
  post: <T,>(url: string, body?: unknown, headers?: Record<string, string>) => call<T>("POST", url, body ?? {}, headers),
  patch: <T,>(url: string, body: unknown) => call<T>("PATCH", url, body),
  upload: <T,>(url: string, form: FormData) => call<T>("POST", url, form),
};
