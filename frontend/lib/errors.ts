import type { ErrorResponse } from "./types";

/** Every failed API call becomes one of these, from the backend's one error format. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;
  readonly retryAfterSeconds: number | null; // from Retry-After, on 429 and 503

  constructor(
    status: number,
    code: string,
    message: string,
    details?: unknown,
    requestId?: string | null,
    retryAfterSeconds?: number | null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details ?? null;
    this.requestId = requestId ?? null;
    this.retryAfterSeconds = retryAfterSeconds ?? null;
  }
}

export const UNREACHABLE = "unreachable";

/** Turn any response that is not ok into an ApiError, even if its body is not JSON. */
export async function toApiError(response: Response): Promise<ApiError> {
  let body: Partial<ErrorResponse> | null = null;
  try {
    body = (await response.json()) as Partial<ErrorResponse>;
  } catch {
    body = null;
  }
  const error = body?.error;
  const retryAfter = Number.parseInt(response.headers.get("retry-after") ?? "", 10);
  return new ApiError(
    response.status,
    error?.code ?? "unexpected_response",
    error?.message ?? "Something went wrong. Please try again.",
    error?.details,
    body?.request_id ?? response.headers.get("x-request-id"),
    Number.isFinite(retryAfter) ? retryAfter : null,
  );
}

export function unreachable(): ApiError {
  return new ApiError(0, UNREACHABLE, "We could not reach our booking system. Please try again shortly.");
}

/** "Try again in 12 minutes" for a rate-limited request, from Retry-After. */
export function waitMessage(error: ApiError): string {
  const seconds = error.retryAfterSeconds;
  if (!seconds || seconds <= 0) return "Too many attempts. Please wait a little and try again.";
  if (seconds < 90) return `Too many attempts. Try again in ${seconds} seconds.`;
  return `Too many attempts. Try again in ${Math.ceil(seconds / 60)} minutes.`;
}
