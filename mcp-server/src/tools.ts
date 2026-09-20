/** Tool registrations for the eye MCP server. */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { ResponseFormat } from "./constants.js";
import { EyeError, EyeState, describeState, request } from "./eyeClient.js";

const stateShape = {
  x: z.number().describe("Horizontal gaze, -1 fully left to 1 fully right"),
  y: z.number().describe("Vertical gaze, -1 fully down to 1 fully up"),
  squint: z.number().describe("Lid closure held between commands, 0 open to 1 shut"),
  lr_ticks: z.number().describe("Raw horizontal servo position in PCA9685 ticks"),
  ud_ticks: z.number().describe("Raw vertical servo position in PCA9685 ticks"),
  mode: z
    .enum(["idle", "driven"])
    .optional()
    .describe("Whether the eye is moving on its own or holding a commanded pose"),
  idle_enabled: z
    .boolean()
    .optional()
    .describe("Whether idle behaviour may resume once commands stop"),
};

const responseFormat = z
  .nativeEnum(ResponseFormat)
  .default(ResponseFormat.MARKDOWN)
  .describe("Output format: 'markdown' for human-readable or 'json' for machine-readable");

type ToolResult = {
  content: Array<{ type: "text"; text: string }>;
  structuredContent?: Record<string, unknown>;
  isError?: boolean;
};

/** Render a state response in the requested format, for every tool that returns one. */
function stateResult(state: EyeState, format: ResponseFormat): ToolResult {
  const text =
    format === ResponseFormat.MARKDOWN
      ? describeState(state)
      : JSON.stringify(state, null, 2);
  return {
    content: [{ type: "text", text }],
    structuredContent: state as unknown as Record<string, unknown>,
  };
}

/** Turn any thrown value into a message the agent can act on. */
function errorResult(error: unknown): ToolResult {
  const message =
    error instanceof EyeError
      ? error.message
      : `Unexpected failure: ${error instanceof Error ? error.message : String(error)}`;
  return { content: [{ type: "text", text: `Error: ${message}` }], isError: true };
}

export function registerTools(server: McpServer): void {
  server.registerTool(
    "eye_look",
    {
      title: "Point the eye",
      description: `Point the animatronic eye at a direction and hold it there.

Both eyeballs move together; the mechanism has one horizontal axis for the pair.
Lids follow the vertical gaze on their own: looking down draws the upper lids
after the pupil, looking up raises the lower lids slightly.

The move takes up to about 135 ms, which is the servo's own speed across the
full horizontal sweep. The call returns once the command is sent, not once the
motion finishes.

Args:
  - x (number): -1 fully left, 0 straight ahead, 1 fully right
  - y (number): -1 fully down, 0 level, 1 fully up
  - response_format ('markdown' | 'json'): Output format (default: 'markdown')

Returns the resulting state: x, y, squint, lr_ticks, ud_ticks.

Examples:
  - "Look at me" -> x=0, y=0
  - "Glance to the upper left" -> x=-0.7, y=0.6
  - Don't use when: you want a blink (use eye_blink instead)

The eye holds the pose until something else moves it. It does not drift back to
a neutral gaze and it does not start moving on its own.`,
      inputSchema: {
        x: z.number().min(-1).max(1).describe("Horizontal gaze, -1 left to 1 right"),
        y: z.number().min(-1).max(1).describe("Vertical gaze, -1 down to 1 up"),
        response_format: responseFormat,
      },
      outputSchema: stateShape,
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async ({ x, y, response_format }) => {
      try {
        const state = await request<EyeState>("/look", "POST", { x, y });
        return stateResult(state, response_format);
      } catch (error) {
        return errorResult(error);
      }
    },
  );

  server.registerTool(
    "eye_blink",
    {
      title: "Blink the eye",
      description: `Close and reopen both eyelids once.

The gaze does not move. A blink takes about 270 ms in total: 93 ms closing,
80 ms shut, 93 ms opening.

Args:
  - ms (number): Closing time in milliseconds, 93 to 400 (default: 93)
  - response_format ('markdown' | 'json'): Output format (default: 'markdown')

Returns {"blinked": true}.

Below 93 ms the lids do not reach each other: the servo cannot cross the upper
lid's travel any faster, so the eye never actually shuts. The schema rejects
smaller values rather than producing a blink nobody can see.

Examples:
  - "Blink" -> no arguments
  - "Blink slowly" -> ms=250`,
      inputSchema: {
        ms: z
          .number()
          .int()
          .min(93, "Below 93 ms the lids do not meet")
          .max(400)
          .default(93)
          .describe("Closing time in milliseconds"),
        response_format: responseFormat,
      },
      outputSchema: { blinked: z.boolean().describe("Always true when the blink ran") },
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: false,
        openWorldHint: true,
      },
    },
    async ({ ms, response_format }) => {
      try {
        const result = await request<{ blinked: boolean }>("/blink", "POST", { ms });
        const text =
          response_format === ResponseFormat.MARKDOWN
            ? `Blinked, ${ms} ms closing.`
            : JSON.stringify(result, null, 2);
        return { content: [{ type: "text", text }], structuredContent: result };
      } catch (error) {
        return errorResult(error);
      }
    },
  );

  server.registerTool(
    "eye_wink",
    {
      title: "Wink one eye",
      description: `Close one eye and reopen it, leaving the other open.

The gaze does not move, and a held squint stays on the eye that is not
winking. Timing matches eye_blink: 93 ms closing, 80 ms shut, 93 ms opening.

Args:
  - side ('left' | 'right'): Which eye closes, as the viewer sees it
  - ms (number): Closing time in milliseconds, 93 to 400 (default: 93)
  - response_format ('markdown' | 'json'): Output format (default: 'markdown')

Returns {"winked": "left" | "right"}.

Examples:
  - "Wink at me" -> side='right'
  - "Wink slowly with your left eye" -> side='left', ms=250
  - Don't use when: both eyes should close (use eye_blink instead)`,
      inputSchema: {
        side: z.enum(["left", "right"]).describe("Which eye closes, as the viewer sees it"),
        ms: z
          .number()
          .int()
          .min(93, "Below 93 ms the lids do not meet")
          .max(400)
          .default(93)
          .describe("Closing time in milliseconds"),
        response_format: responseFormat,
      },
      outputSchema: { winked: z.string().describe("The eye that closed") },
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: false,
        openWorldHint: true,
      },
    },
    async ({ side, ms, response_format }) => {
      try {
        const result = await request<{ winked: string }>("/wink", "POST", { side, ms });
        const text =
          response_format === ResponseFormat.MARKDOWN
            ? `Winked with the ${result.winked} eye, ${ms} ms closing.`
            : JSON.stringify(result, null, 2);
        return { content: [{ type: "text", text }], structuredContent: result };
      } catch (error) {
        return errorResult(error);
      }
    },
  );

  server.registerTool(
    "eye_express",
    {
      title: "Play an expression",
      description: `Play a short gesture: a sequence of gaze and lid moves that ends where it began.

  alert       wide and still, then two fast blinks. Asking for attention.
  suspicious  lids to a slit, one slow sweep across, no blink. "Are you sure?"
  curious     a glance up and away, a blink on the return.
  tired       heavy lids, the gaze sagging, one long blink.

Args:
  - name ('alert' | 'suspicious' | 'curious' | 'tired'): Which gesture to play
  - response_format ('markdown' | 'json'): Output format (default: 'markdown')

Returns {"expressed": name}.

The call returns when the gesture finishes, which takes 1 to 2 seconds. A
command arriving meanwhile cuts it short: the newest instruction wins rather
than queueing behind the theatre. A held squint survives, because a gesture
restores the pose it started from.

Examples:
  - "Look like you don't believe me" -> name='suspicious'
  - "Get my attention" -> name='alert'
  - Don't use when: you want a lasting pose (use eye_look or eye_squint)`,
      inputSchema: {
        name: z
          .enum(["alert", "suspicious", "curious", "tired"])
          .describe("Which gesture to play"),
        response_format: responseFormat,
      },
      outputSchema: { expressed: z.string().describe("The gesture that played") },
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: false,
        openWorldHint: true,
      },
    },
    async ({ name, response_format }) => {
      try {
        const result = await request<{ expressed: string }>("/express", "POST", { name });
        const text =
          response_format === ResponseFormat.MARKDOWN
            ? `Played the ${result.expressed} expression.`
            : JSON.stringify(result, null, 2);
        return { content: [{ type: "text", text }], structuredContent: result };
      } catch (error) {
        return errorResult(error);
      }
    },
  );

  server.registerTool(
    "eye_squint",
    {
      title: "Hold the lids partly closed",
      description: `Set how far the eyelids stay closed between commands.

This is a held position, not a movement: it stays until changed. A blink still
reaches full closure while a squint is held, then returns to the squint.

Args:
  - v (number): 0 fully open, 1 fully shut
  - response_format ('markdown' | 'json'): Output format (default: 'markdown')

Returns the resulting state: x, y, squint, lr_ticks, ud_ticks.

Values above about 0.8 leave a gap too small to see through, which reads as a
closed eye rather than a squint.

Examples:
  - "Narrow your eyes" -> v=0.45
  - "Open your eyes fully" -> v=0`,
      inputSchema: {
        v: z.number().min(0).max(1).describe("Lid closure, 0 open to 1 shut"),
        response_format: responseFormat,
      },
      outputSchema: stateShape,
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async ({ v, response_format }) => {
      try {
        const state = await request<EyeState>("/squint", "POST", { v });
        return stateResult(state, response_format);
      } catch (error) {
        return errorResult(error);
      }
    },
  );

  server.registerTool(
    "eye_set_idle",
    {
      title: "Switch idle behaviour on or off",
      description: `Allow or forbid the eye's own idle behaviour.

The eye is still by default and stays still. Switching idle behaviour on makes
it saccade, drift and blink every two to four seconds once 8 s pass with no
command. Switching it off again holds the last commanded pose.

Args:
  - enabled (boolean): true lets idle behaviour resume, false holds the pose
  - response_format ('markdown' | 'json'): Output format (default: 'markdown')

Returns {"idle_enabled": boolean}.

Off does not mean frozen: eye_look, eye_blink and eye_squint still work, and
the pose stays put between them. The setting lives in memory, so a power cycle
returns the eye to still.

Movement is how the eye says a session is waiting on an answer. Leaving idle
behaviour on spends that signal on nothing, so turn it on only when asked.

Examples:
  - "Let the eye do its own thing" -> enabled=true
  - "Stop the eye fidgeting" -> enabled=false`,
      inputSchema: {
        enabled: z.boolean().describe("Whether idle behaviour may resume"),
        response_format: responseFormat,
      },
      outputSchema: {
        idle_enabled: z.boolean().describe("The setting now in force"),
      },
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async ({ enabled, response_format }) => {
      try {
        const result = await request<{ idle_enabled: boolean }>("/idle", "POST", {
          enabled,
        });
        const text =
          response_format === ResponseFormat.MARKDOWN
            ? result.idle_enabled
              ? "Idle behaviour on: the eye moves on its own after 8 s of silence."
              : "Idle behaviour off: the eye holds its pose until commanded."
            : JSON.stringify(result, null, 2);
        return { content: [{ type: "text", text }], structuredContent: result };
      } catch (error) {
        return errorResult(error);
      }
    },
  );

  server.registerTool(
    "eye_get_state",
    {
      title: "Read the eye's pose",
      description: `Report where the eye is looking and what its lids are doing.

Args:
  - response_format ('markdown' | 'json'): Output format (default: 'markdown')

Returns:
  {
    "x": number,          // Horizontal gaze, -1 left to 1 right
    "y": number,          // Vertical gaze, -1 down to 1 up
    "squint": number,     // Held lid closure, 0 open to 1 shut
    "lr_ticks": number,   // Raw horizontal servo position
    "ud_ticks": number,   // Raw vertical servo position
    "mode": string        // "idle" when moving on its own, "driven" when holding a command
  }

The mode is "driven" unless eye_set_idle turned idle behaviour on. In "idle" the
values change between calls, because the eye saccades and drifts; two identical
reads there mean it is holding a command, not that it is broken.`,
      inputSchema: { response_format: responseFormat },
      outputSchema: stateShape,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true,
      },
    },
    async ({ response_format }) => {
      try {
        const state = await request<EyeState>("/state", "GET");
        return stateResult(state, response_format);
      } catch (error) {
        return errorResult(error);
      }
    },
  );
}
