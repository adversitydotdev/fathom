import "server-only";

/**
 * Mock mode serves every `/v1` call from the MSW handlers in `src/mocks`,
 * in-process. No API process, no database, no bearer token.
 */
export const apiMocking = process.env.OGRL_API_MOCKING === "enabled";

/** RFC 0003 section 2: the web process reaches the API on the same task. */
export const apiOrigin = process.env.OGRL_API_ORIGIN ?? "http://127.0.0.1:8080";

/** RFC 0004 requires a bearer token. How it is issued is still open. */
export const apiToken = process.env.OGRL_API_TOKEN;
