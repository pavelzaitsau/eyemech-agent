#!/usr/bin/env node
/**
 * MCP server for the EyeMech e3.2 animatronic eye.
 *
 * The eye runs MicroPython on an ESP32 and serves four HTTP endpoints on the
 * local network. This server exposes them as tools over stdio.
 *
 * Set EYE_URL to the address the board prints on boot.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { EYE_URL } from "./constants.js";
import { registerTools } from "./tools.js";

const server = new McpServer({
  name: "eye-mcp-server",
  version: "1.0.0",
});

registerTools(server);

async function main(): Promise<void> {
  // A missing EYE_URL is reported per call rather than at startup: the board is
  // often powered after the client, and failing here would need a restart.
  if (!EYE_URL) {
    console.error("eye-mcp-server: EYE_URL is not set; every tool call will fail");
  }
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`eye-mcp-server: ready, eye at ${EYE_URL || "<unset>"}`);
}

main().catch((error: unknown) => {
  console.error("eye-mcp-server:", error instanceof Error ? error.message : error);
  process.exit(1);
});
