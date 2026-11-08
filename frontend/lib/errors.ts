import type { ErrorResponse } from "./types";

/** Every failed API call becomes one of these, from the backend's one error format. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;

  constructor(status: number, code: string, message: string, details?: unknown, requestId?: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details ?? null;
    this.requestId = requestId ?? null;
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
  return new ApiError(
    response.status,
    error?.code ?? "unexpected_response",
    error?.message ?? "Something went wrong. Please try again.",
    error?.details,
    body?.request_id ?? response.headers.get("x-request-id"),
  );
}

export function unreachable(): ApiError {
  return new ApiError(0, UNREACHABLE, "We could not reach our booking system. Please try again shortly.");
}
