import { config as dotenvConfig } from "dotenv";
import { resolve, dirname } from "node:path";
import { fileURLToPath as toFilePath } from "node:url";

// Load .env from project root (two levels up from src/server/src/)
const __serverDir = dirname(toFilePath(import.meta.url));
dotenvConfig({ path: resolve(__serverDir, "..", "..", "..", ".env") });

import express from "express";
import morgan from "morgan";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadConfig } from "./config.js";
import { CopilotService } from "./services/copilot.service.js";
import { WorkspaceService } from "./services/workspace.service.js";
import { UserMcpService } from "./services/user-mcp.service.js";
import { createChatRoutes } from "./routes/chat.routes.js";
import { createSessionRoutes } from "./routes/sessions.routes.js";
import { createWorkspaceRoutes } from "./routes/workspace.routes.js";
import healthRoutes from "./routes/health.routes.js";
import { easyAuthMiddleware } from "./middleware/auth.middleware.js";

// Application Insights — must be initialized before other imports
const aiConnStr = process.env.APPLICATIONINSIGHTS_CONNECTION_STRING;
if (aiConnStr) {
  const appInsights = await import("applicationinsights");
  appInsights.setup(aiConnStr)
    .setAutoCollectRequests(true)
    .setAutoCollectPerformance(true, true)
    .setAutoCollectExceptions(true)
    .setAutoCollectDependencies(true)
    .setAutoCollectConsole(true, true)
    .start();
  console.log("[AppInsights] Telemetry enabled");
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));

async function main() {
  const config = loadConfig();
  const app = express();

  // Minimal middleware
  app.use(morgan(config.isProduction ? "combined" : "dev"));
  app.use(express.json({ limit: "1mb" }));
  app.use(easyAuthMiddleware);

  // Health routes
  app.use("/api", healthRoutes);

  // User identity
  app.get("/api/me", (req, res) => {
    res.json({ userId: req.userId, userName: req.userName });
  });

  // Initialize services
  const copilot = new CopilotService(config);
  const workspace = new WorkspaceService(config);
  const basePath = config.workspaceMountPath || "/tmp/ghcp-sessions";
  const userMcp = new UserMcpService(basePath);
  copilot.setUserMcpLoader((userId) => userMcp.getUserServers(userId));

  // API routes
  app.use("/api/sessions", createSessionRoutes(copilot, workspace));
  app.use("/api/chat", createChatRoutes(copilot));
  app.use("/api/workspace", createWorkspaceRoutes(workspace));

  // Global MCP servers endpoint (admin-configured, read-only, no secrets)
  app.get("/api/mcp-servers", (_req, res) => {
    const servers = Object.entries(config.mcpServers).map(([name, srv]) => ({
      name,
      type: "type" in srv ? srv.type : "local",
      url: "url" in srv ? srv.url : undefined,
    }));
    res.json({ servers });
  });

  // User MCP servers endpoints (per-user persistent config)
  app.get("/api/mcp-servers/user", (req, res) => {
    const servers = userMcp.getUserServers(req.userId);
    // Return server list with urls but mask sensitive headers
    const safe = Object.entries(servers).map(([name, srv]) => ({
      name,
      type: "type" in srv ? srv.type : "local",
      url: "url" in srv ? srv.url : undefined,
      headers: "headers" in srv && srv.headers
        ? Object.fromEntries(
            Object.entries(srv.headers as Record<string, string>).map(([k, v]) => [k, v.substring(0, 4) + "***"])
          )
        : undefined,
      tools: "tools" in srv ? srv.tools : undefined,
    }));
    res.json({ servers: safe });
  });

  app.put("/api/mcp-servers/user", (req, res) => {
    const { servers } = req.body as { servers?: Record<string, unknown> };
    if (!servers || typeof servers !== "object") {
      res.status(400).json({ error: { message: "servers object required" } });
      return;
    }
    userMcp.setUserServers(req.userId, servers as Record<string, import("@github/copilot-sdk").MCPServerConfig>);
    res.json({ ok: true, count: Object.keys(servers).length });
  });

  app.delete("/api/mcp-servers/user/:name", (req, res) => {
    const removed = userMcp.removeUserServer(req.userId, req.params.name);
    if (removed) {
      res.json({ ok: true });
    } else {
      res.status(404).json({ error: { message: `Server "${req.params.name}" not found` } });
    }
  });

  // Models endpoint — cached, list deployed models from Azure OpenAI via ARM API
  let modelsCache: { data: unknown; expiry: number } | null = null;
  const MODELS_CACHE_TTL = 5 * 60 * 1000; // 5 minutes

  app.get("/api/models", async (_req, res) => {
    const fallback = { models: [{ id: config.azure.foundryModel, label: config.azure.foundryModel }], default: config.azure.foundryModel };

    if (modelsCache && Date.now() < modelsCache.expiry) {
      res.json(modelsCache.data);
      return;
    }

    try {
      const { openAiResourceName, openAiResourceGroup, subscriptionId } = config.azure;
      if (!openAiResourceName || !openAiResourceGroup || !subscriptionId) {
        console.warn("[Models] Missing Azure OpenAI resource config — returning fallback");
        res.json(fallback);
        return;
      }

      // Get ARM token via managed identity (works in ACA)
      const identityEndpoint = process.env.IDENTITY_ENDPOINT;
      const identityHeader = process.env.IDENTITY_HEADER;
      const clientId = process.env.AZURE_CLIENT_ID;
      let armToken: string | undefined;

      if (identityEndpoint && identityHeader) {
        const tokenUrl = `${identityEndpoint}?api-version=2019-08-01&resource=https://management.azure.com${clientId ? `&client_id=${clientId}` : ""}`;
        const tokenResp = await fetch(tokenUrl, {
          headers: { "X-IDENTITY-HEADER": identityHeader },
        });
        if (tokenResp.ok) {
          const tokenData = await tokenResp.json() as { access_token: string };
          armToken = tokenData.access_token;
        } else {
          console.warn(`[Models] Managed identity token failed: ${tokenResp.status} ${await tokenResp.text()}`);
        }
      } else {
        console.warn(`[Models] IDENTITY_ENDPOINT=${!!identityEndpoint} IDENTITY_HEADER=${!!identityHeader}`);
      }

      if (!armToken) {
        // Fallback: try Azure CLI token (dev environment)
        try {
          const { execSync } = await import("node:child_process");
          armToken = execSync("az account get-access-token --resource https://management.azure.com --query accessToken -o tsv", { encoding: "utf-8" }).trim();
        } catch {
          console.warn("[Models] No managed identity or Azure CLI — returning fallback");
          res.json(fallback);
          return;
        }
      }

      const armUrl = `https://management.azure.com/subscriptions/${subscriptionId}/resourceGroups/${openAiResourceGroup}/providers/Microsoft.CognitiveServices/accounts/${openAiResourceName}/deployments?api-version=2024-10-01`;
      const resp = await fetch(armUrl, {
        headers: { Authorization: `Bearer ${armToken}` },
      });
      if (!resp.ok) {
        console.warn(`[Models] ARM deployments list failed: ${resp.status}`);
        res.json(fallback);
        return;
      }
      const data = await resp.json() as { value?: Array<{ name: string; properties: { model: { name: string }; provisioningState: string } }> };
      const chatModels = (data.value ?? [])
        .filter((d) => d.properties.provisioningState === "Succeeded")
        .filter((d) => {
          const m = d.properties.model.name.toLowerCase();
          return !m.includes("embedding") && !m.includes("whisper") && !m.includes("dall") && !m.includes("tts") && !m.includes("rerank");
        })
        .map((d) => ({ id: d.name, label: d.properties.model.name }))
        .sort((a, b) => a.label.localeCompare(b.label));
      const result = { models: chatModels.length > 0 ? chatModels : fallback.models, default: config.azure.foundryModel };
      modelsCache = { data: result, expiry: Date.now() + MODELS_CACHE_TTL };
      res.json(result);
    } catch (err) {
      console.warn("[Models] Error listing models:", err);
      res.json(fallback);
    }
  });

  // Serve static frontend in production (Vite hashes filenames → long-lived cache)
  if (config.isProduction) {
    const clientDist = path.resolve(__dirname, "../../client/dist");
    app.use(express.static(clientDist, { maxAge: "1y", immutable: true }));
    app.use((_req, res, next) => {
      if (_req.path.startsWith("/api")) return next();
      res.set("Cache-Control", "no-cache");
      res.sendFile(path.join(clientDist, "index.html"));
    });
  }

  // Graceful shutdown
  const shutdown = async (signal: string) => {
    console.log(`\n[Server] ${signal} received, shutting down...`);
    await copilot.shutdown();
    process.exit(0);
  };

  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));

  // Start listening FIRST, then init services in background
  app.listen(config.port, () => {
    console.log(`
╔══════════════════════════════════════════════════╗
║   GHCP-UI Server                                 ║
║   Port: ${String(config.port).padEnd(40)}║
║   Mode: ${config.nodeEnv.padEnd(40)}║
║   BYOK: ${String(config.copilot.useByok).padEnd(40)}║
║   Model: ${config.azure.foundryModel.padEnd(39)}║
╚══════════════════════════════════════════════════╝
    `);

    // Initialize heavy services after server is listening
    Promise.all([
      copilot.initialize(),
      workspace.initialize(),
    ]).then(() => {
      console.log("[Server] All services initialized");
    }).catch((err) => {
      console.error("[Server] Service initialization error:", err);
    });
  });
}

main().catch((err) => {
  console.error("[Server] Fatal error:", err);
  process.exit(1);
});
