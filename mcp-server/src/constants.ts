/** Shared configuration for the eye MCP server. */

/**
 * Base URL of the eye, taken from EYE_URL.
 *
 * The board prints its address on boot, as `eye ready on http://<address>/`.
 * There is no discovery: MicroPython does not advertise the board over mDNS.
 */
export const EYE_URL = (process.env.EYE_URL ?? "").replace(/\/+$/, "");

/**
 * Request timeout.
 *
 * A blink holds the connection for its full 270 ms, and the board answers a
 * single request at a time, so this covers a queued request behind a blink.
 */
export const REQUEST_TIMEOUT_MS = 5000;

export enum ResponseFormat {
  MARKDOWN = "markdown",
  JSON = "json",
}
