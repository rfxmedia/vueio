export function resolveVueioApiBaseUrl(location = window.location) {
  return location.origin
}

// Agents learn Vueio from the MCP server itself, so this text only connects
// them. New features reach agents without new setup text.
export function buildVueioMcpSetup({ baseUrl, keyName, userName, token }) {
  const url = `${baseUrl}/api/mcp`
  return [
    '# Connect an agent to Vueio',
    '',
    `This key lets an agent act as ${userName} in Vueio, with exactly the same permissions. Key: ${keyName}.`,
    'The agent finds every Vueio feature through the MCP server. New features need no new setup.',
    '',
    `MCP server: ${url}`,
    `Header: Authorization: Bearer ${token}`,
    '',
    '## Claude Code',
    '',
    `claude mcp add --scope user --transport http vueio ${url} --header "Authorization: Bearer ${token}"`,
    '',
    '## Codex',
    '',
    'Add the first line to your shell profile, then run the second line once.',
    '',
    `export VUEIO_AGENT_KEY="${token}"`,
    `codex mcp add vueio --url ${url} --bearer-token-env-var VUEIO_AGENT_KEY`,
    '',
    '## OpenClaw',
    '',
    `openclaw mcp add vueio --transport streamable-http --url ${url} --header "Authorization=Bearer ${token}"`,
    '',
    '## Other MCP clients',
    '',
    JSON.stringify({
      mcpServers: {
        vueio: { type: 'http', url, headers: { Authorization: `Bearer ${token}` } },
      },
    }, null, 2),
    '',
    '## Chat apps (Claude, ChatGPT)',
    '',
    `Chat apps need no key. Add a custom connector with the address ${url}, then sign in to Vueio and allow access.`,
    '',
    `Keep this key private. Anyone who has it can act as ${userName}. Revoke it on the Agent keys page in Vueio.`,
  ].join('\n')
}
