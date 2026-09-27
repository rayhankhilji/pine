export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ErrorEnvelope = {
  error?: { code?: string; message?: string; details?: Record<string, unknown> };
};

function errorFromEnvelope(body: string, status: number): ApiError {
  let envelope: ErrorEnvelope = {};
  try {
    envelope = JSON.parse(body) as ErrorEnvelope;
  } catch {
    // non-JSON error body
  }
  const err = envelope.error;
  return new ApiError(
    err?.code ?? "UNKNOWN",
    err?.message ?? `Request failed with status ${status}`,
    status,
    err?.details ?? {},
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!response.ok) {
    throw errorFromEnvelope(await response.text(), response.status);
  }

  return (await response.json()) as T;
}

export type UploadProgress = { loaded: number; total: number };

function upload<T>(
  path: string,
  form: FormData,
  onProgress?: (progress: UploadProgress) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}${path}`);
    xhr.responseType = "json";
    if (onProgress) {
      xhr.upload.onprogress = (event) => {
        onProgress({ loaded: event.loaded, total: event.total });
      };
    }
    xhr.onload = () => {
      const body =
        typeof xhr.response === "string" ? xhr.response : JSON.stringify(xhr.response);
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response as T);
      } else {
        reject(errorFromEnvelope(body, xhr.status));
      }
    };
    xhr.onerror = () =>
      reject(new ApiError("NETWORK", "Upload failed — check your connection", 0));
    xhr.send(form);
  });
}

export type HealthResponse = { status: string; version: string };

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  upload: <T>(path: string, form: FormData, onProgress?: (p: UploadProgress) => void) =>
    upload<T>(path, form, onProgress),
  health: () => request<HealthResponse>("/api/v1/health"),
};
