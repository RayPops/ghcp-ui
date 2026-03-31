import type { MCPServerConfig } from "@github/copilot-sdk";

export interface AppConfig {
  port: number;
  nodeEnv: string;
  isProduction: boolean;

  azure: {
    foundryEndpoint: string;
    foundryApiKey: string;
    foundryBearerToken: string;
    foundryModel: string;
    storageConnectionString: string;
    storageAccountName: string;
    storageContainerName: string;
    openAiResourceName: string;
    openAiResourceGroup: string;
    subscriptionId: string;
  };

  copilot: {
    githubToken?: string;
    useByok: boolean;
  };

  /** Base directory for workspace files (Azure Files mount or local temp) */
  workspaceMountPath: string;

  /** Base directory for SDK session state (ephemeral storage — must support SQLite locking) */
  sessionStatePath: string;

  /** Global MCP servers injected into every session */
  mcpServers: Record<string, MCPServerConfig>;
}

/**
 * Parse MCP_SERVERS_JSON env var.
 * Format: JSON object where keys are server names and values are MCPServerConfig.
 * Example:
 *   {"github":{"type":"http","url":"https://api.githubcopilot.com/mcp","headers":{"Authorization":"Bearer ghp_xxx"},"tools":["*"]}}
 */
function parseMcpServers(): Record<string, MCPServerConfig> {
  const raw = process.env.MCP_SERVERS_JSON;
  if (!raw) return {};

  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      console.warn("[Config] MCP_SERVERS_JSON must be a JSON object, ignoring");
      return {};
    }
    const count = Object.keys(parsed).length;
    console.log(`[Config] Loaded ${count} global MCP server(s): ${Object.keys(parsed).join(", ")}`);
    return parsed as Record<string, MCPServerConfig>;
  } catch (err) {
    console.warn("[Config] Failed to parse MCP_SERVERS_JSON:", (err as Error).message);
    return {};
  }
}

export function loadConfig(): AppConfig {
  const nodeEnv = process.env.NODE_ENV ?? "development";

  const foundryEndpoint = process.env.AZURE_FOUNDRY_ENDPOINT ?? "";
  const foundryApiKey = process.env.AZURE_FOUNDRY_API_KEY ?? "";
  const foundryBearerToken = process.env.AZURE_FOUNDRY_BEARER_TOKEN ?? "";
  const foundryModel = process.env.AZURE_FOUNDRY_MODEL ?? "gpt-5.4";
  const githubToken = process.env.COPILOT_GITHUB_TOKEN;

  const useByok = Boolean(foundryEndpoint && (foundryApiKey || foundryBearerToken));

  return {
    port: parseInt(process.env.PORT ?? "3001", 10),
    nodeEnv,
    isProduction: nodeEnv === "production",
    azure: {
      foundryEndpoint,
      foundryApiKey,
      foundryBearerToken,
      foundryModel,
      storageConnectionString: process.env.AZURE_STORAGE_CONNECTION_STRING ?? "",
      storageAccountName: process.env.AZURE_STORAGE_ACCOUNT_NAME ?? "",
      storageContainerName: process.env.AZURE_STORAGE_CONTAINER_NAME ?? "workspaces",
      openAiResourceName: process.env.AZURE_OPENAI_NAME ?? "",
      openAiResourceGroup: process.env.AZURE_OPENAI_RG ?? "",
      subscriptionId: process.env.AZURE_SUBSCRIPTION_ID ?? "",
    },
    copilot: {
      githubToken,
      useByok,
    },
    workspaceMountPath: process.env.WORKSPACE_MOUNT_PATH ?? "",
    sessionStatePath: process.env.SESSION_STATE_PATH ?? "",
    mcpServers: parseMcpServers(),
  };
}
