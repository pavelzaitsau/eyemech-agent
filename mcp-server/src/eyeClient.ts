/** HTTP client for the eye's control surface. */

import { EYE_URL, REQUEST_TIMEOUT_MS } from "./constants.js";

/** The eye's reported pose. Ticks are raw PCA9685 counts, useful for logs. */
export interface EyeState {
  x: number;
  y: number;
  squint: number;
  lr_ticks: number;
  ud_ticks: number;
  mode?: "idle" | "driven";
  idle_enabled?: boolean;
}

/** Thrown for anything the caller can act on: no address, no route, refusal. */
export class EyeError extends Error {}

export async function request<T>(
  path: string,
  method: "GET" | "POST",
  body?: unknown,
): Promise<T> {
  if (!EYE_URL) {
    throw new EyeError(
      "EYE_URL is not set. The board prints its address on boot as " +
        "'eye ready on http://<address>/'. Set EYE_URL to that address.",
    );
  }

  let response: Response;
  try {
    response = await fetch(`${EYE_URL}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new EyeError(
      `Cannot reach the eye at ${EYE_URL}: ${reason}. Check that the board is ` +
        "powered, joined the network, and that EYE_URL matches the address it printed.",
    );
  }

  const text = await response.text();
  if (!response.ok) {
    throw new EyeError(
      `The eye refused ${method} ${path} with ${response.status}: ${text.slice(0, 200)}`,
    );
  }

  try {
    return JSON.parse(text) as T;
  } catch {
    throw new EyeError(`The eye returned a body that is not JSON: ${text.slice(0, 200)}`);
  }
}

/** Render a pose the way a person reads it, rather than as raw numbers. */
export function describeState(state: EyeState): string {
  const horizontal =
    Math.abs(state.x) < 0.1 ? "centred" : state.x < 0 ? "left" : "right";
  const vertical =
    Math.abs(state.y) < 0.1 ? "level" : state.y < 0 ? "down" : "up";
  const lines = [
    "# Eye state",
    "",
    `- **Gaze**: ${horizontal} ${Math.abs(state.x).toFixed(2)}, ${vertical} ${Math.abs(state.y).toFixed(2)}`,
    `- **Squint**: ${state.squint.toFixed(2)}`,
    `- **Servo ticks**: horizontal ${state.lr_ticks}, vertical ${state.ud_ticks}`,
  ];
  if (state.mode) {
    const note =
      state.mode === "idle"
        ? "moving on its own; the next command takes over"
        : state.idle_enabled === false
          ? "holding a commanded pose; idle behaviour is switched off"
          : "holding a commanded pose; idle behaviour resumes after 8 s of silence";
    lines.push(`- **Mode**: ${state.mode} — ${note}`);
  }
  return lines.join("\n");
}
