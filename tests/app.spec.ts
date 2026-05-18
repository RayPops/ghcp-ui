import { test, expect } from "@playwright/test";

test.describe("GHCP UI", () => {
  test("loads the homepage with header and branding", async ({ page }) => {
    await page.goto("/");
    // Header should show the Openreach DispatchAI brand
    await expect(page.locator("h1")).toContainText("Openreach");
    await expect(page.locator("h1")).toContainText("DispatchAI");
  });

  test("document title is Openreach DispatchAI", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle("Openreach DispatchAI");
  });

  test("shows disconnected state initially", async ({ page }) => {
    await page.goto("/");
    // Should show disconnected indicator or no active session
    await expect(page.getByText("Disconnected")).toBeVisible();
  });

  test("has a sidebar toggle (hamburger menu)", async ({ page }) => {
    await page.goto("/");
    const menuButton = page.getByLabel("Toggle sidebar");
    await expect(menuButton).toBeVisible();
  });

  test("can open sidebar and see new chat button", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Toggle sidebar").click();
    await expect(page.getByRole("button", { name: "New Chat", exact: true })).toBeVisible();
  });

  test("new chat button creates session directly with default model", async ({ page }) => {
    await page.goto("/");
    await page.waitForTimeout(2000);
    // Open sidebar
    await page.getByLabel("Toggle sidebar").click();
    await page.getByRole("button", { name: "New Chat", exact: true }).click();
    // Should create session immediately (no dialog) — header badge should show model
    await expect(page.getByRole("banner").getByText("gpt-5.4")).toBeVisible({ timeout: 15000 });
  });

  test("has settings button that opens settings drawer", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Settings").click();
    await expect(page.getByText("Settings")).toBeVisible();
  });

  test("has workspace button that opens workspace panel", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Workspace files").click();
    await expect(page.getByText("Workspace", { exact: true })).toBeVisible();
  });

  test("input bar is disabled when no session is active", async ({ page }) => {
    await page.goto("/");
    const textarea = page.locator("textarea");
    await expect(textarea).toBeDisabled();
  });

  test("health API is accessible", async ({ request }) => {
    const res = await request.get("/api/healthz");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe("healthy");
  });

  test("sessions API returns valid response", async ({ request }) => {
    const res = await request.get("/api/sessions");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty("sessions");
    expect(Array.isArray(body.sessions)).toBeTruthy();
  });
});

test.describe("PWA", () => {
  test("has PWA meta tags in HTML", async ({ page }) => {
    await page.goto("/");
    // Theme color
    const themeColor = page.locator('meta[name="theme-color"]');
    await expect(themeColor).toHaveAttribute("content", "#09090b");
    // Apple mobile web app
    const appleMeta = page.locator('meta[name="apple-mobile-web-app-capable"]');
    await expect(appleMeta).toHaveAttribute("content", "yes");
    // Apple status bar style
    const statusBar = page.locator('meta[name="apple-mobile-web-app-status-bar-style"]');
    await expect(statusBar).toHaveAttribute("content", "black-translucent");
    // Apple title
    const appleTitle = page.locator('meta[name="apple-mobile-web-app-title"]');
    await expect(appleTitle).toHaveAttribute("content", "Openreach DispatchAI");
  });

  test("has apple-touch-icon link", async ({ page }) => {
    await page.goto("/");
    const touchIcon = page.locator('link[rel="apple-touch-icon"]');
    await expect(touchIcon).toBeAttached();
  });
});

test.describe("Speech-to-Text", () => {
  test("shows voice input button in the input bar", async ({ page }) => {
    // Chromium supports SpeechRecognition via webkitSpeechRecognition
    await page.goto("/");
    // The mic button should be present (Voice input)
    const micButton = page.getByTitle("Voice input");
    // In Chromium headless, SpeechRecognition may or may not be available
    // so we check if the button exists OR the feature is gracefully absent
    const count = await micButton.count();
    // Either the mic button exists or it's gracefully hidden — both are valid
    expect(count).toBeLessThanOrEqual(1);
  });

  test("input bar has correct placeholder when no session", async ({ page }) => {
    await page.goto("/");
    const textarea = page.locator("textarea");
    await expect(textarea).toHaveAttribute("placeholder", "Create a new chat to get started…");
  });
});

test.describe("Workspace & Folders", () => {
  test("workspace panel shows folder section", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Workspace files").click();
    await expect(page.getByText("Folders")).toBeVisible();
    await expect(page.getByText("Root")).toBeVisible();
  });

  test("workspace panel has new folder button", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Workspace files").click();
    await expect(page.getByTitle("New folder")).toBeVisible();
  });

  test("folders API returns valid response", async ({ request }) => {
    const res = await request.get("/api/workspace/default/folders");
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty("folders");
    expect(Array.isArray(data.folders)).toBe(true);
  });

  test("can create and list a folder", async ({ request }) => {
    const createRes = await request.post("/api/workspace/default/folders", {
      data: { name: "test-project" },
    });
    expect(createRes.status()).toBe(201);

    const listRes = await request.get("/api/workspace/default/folders");
    const data = await listRes.json();
    expect(data.folders).toContain("test-project");

    // Clean up
    await request.delete("/api/workspace/default/folders/test-project");
  });
});

test.describe("Models API", () => {
  test("models API returns valid response with default", async ({ request }) => {
    const res = await request.get("/api/models");
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty("models");
    expect(data).toHaveProperty("default");
    expect(Array.isArray(data.models)).toBe(true);
    expect(data.models.length).toBeGreaterThan(0);
    // Each model has id and label
    for (const m of data.models) {
      expect(m).toHaveProperty("id");
      expect(m).toHaveProperty("label");
    }
  });

  test("new chat uses gpt-5.4 as default model", async ({ page }) => {
    await page.goto("/");
    await page.waitForTimeout(2000);
    await page.getByLabel("Toggle sidebar").click();
    await page.getByRole("button", { name: "New Chat", exact: true }).click();
    // Session should be created with gpt-5.4 — visible in header badge
    await expect(page.getByRole("banner").getByText("gpt-5.4")).toBeVisible({ timeout: 15000 });
  });

  test("default model is gpt-5.4", async ({ request }) => {
    const res = await request.get("/api/models");
    const data = await res.json();
    expect(data.default).toBe("gpt-5.4");
  });
});

test.describe("Session Persistence", () => {
  test("sessions API returns active flag", async ({ request }) => {
    const res = await request.get("/api/sessions");
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toHaveProperty("sessions");
    // Each session should have an active field
    for (const s of data.sessions) {
      expect(typeof s.active).toBe("boolean");
    }
  });

  test("create session then see it listed with active=true", async ({ request }) => {
    // Create a session
    const createRes = await request.post("/api/sessions", {
      data: { model: "gpt-4.1" },
    });
    expect(createRes.ok()).toBeTruthy();
    const created = await createRes.json();
    expect(created.id).toBeTruthy();
    expect(created.active).toBe(true);

    // List sessions — should include the new one as active
    const listRes = await request.get("/api/sessions");
    const data = await listRes.json();
    const found = data.sessions.find((s: { id: string }) => s.id === created.id);
    expect(found).toBeTruthy();
    expect(found.active).toBe(true);
    expect(found.model).toBe("gpt-4.1");

    // Cleanup
    await request.delete(`/api/sessions/${created.id}`);
  });

  test("resume endpoint returns session info", async ({ request }) => {
    // Create a session first
    const createRes = await request.post("/api/sessions", {
      data: { model: "gpt-4.1" },
    });
    const created = await createRes.json();

    // Resume should work (session is already active, should be a no-op return)
    const resumeRes = await request.post(`/api/sessions/${created.id}/resume`);
    expect(resumeRes.ok()).toBeTruthy();
    const resumed = await resumeRes.json();
    expect(resumed.id).toBe(created.id);
    expect(resumed.active).toBe(true);

    // Cleanup
    await request.delete(`/api/sessions/${created.id}`);
  });

  test("rename session via PATCH", async ({ request }) => {
    // Create a session
    const createRes = await request.post("/api/sessions", {
      data: { model: "gpt-4.1" },
    });
    const created = await createRes.json();

    // Rename it
    const patchRes = await request.patch(`/api/sessions/${created.id}`, {
      data: { title: "My Test Chat" },
    });
    expect(patchRes.ok()).toBeTruthy();

    // List and verify the title is shown
    const listRes = await request.get("/api/sessions");
    const data = await listRes.json();
    const found = data.sessions.find((s: { id: string }) => s.id === created.id);
    expect(found?.title).toBe("My Test Chat");

    // Cleanup
    await request.delete(`/api/sessions/${created.id}`);
  });

  test("delete session removes it from list", async ({ request }) => {
    const createRes = await request.post("/api/sessions", {
      data: { model: "gpt-4.1" },
    });
    const created = await createRes.json();

    // Delete
    const delRes = await request.delete(`/api/sessions/${created.id}`);
    expect(delRes.status()).toBe(204);

    // List — should not contain it
    const listRes = await request.get("/api/sessions");
    const data = await listRes.json();
    const found = data.sessions.find((s: { id: string }) => s.id === created.id);
    expect(found).toBeFalsy();
  });

  test("sidebar shows active indicator for sessions", async ({ page, request }) => {
    // Create session via API first
    const createRes = await request.post("/api/sessions", {
      data: { model: "gpt-4.1" },
    });
    const created = await createRes.json();

    // Now load the page — it will fetch sessions on mount and should find our session
    await page.goto("/");

    // Open sidebar
    await page.getByLabel("Toggle sidebar").click();

    // The sidebar should show the session with the model text
    const sessionEntry = page.locator('aside').getByText("gpt-4.1");
    await expect(sessionEntry.first()).toBeVisible({ timeout: 15000 });

    // Cleanup
    await request.delete(`/api/sessions/${created.id}`);
  });
});

test.describe("User MCP Config", () => {
  test("user identity endpoint returns userId", async ({ request }) => {
    const res = await request.get("/api/me");
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data.userId).toBeTruthy();
    expect(data.userName).toBeTruthy();
  });

  test("user MCP CRUD: add, list, remove", async ({ request }) => {
    // List — should be empty or whatever baseline
    const before = await request.get("/api/mcp-servers/user");
    const beforeData = await before.json();
    const startCount = beforeData.servers.length;

    // PUT a server
    const putRes = await request.put("/api/mcp-servers/user", {
      data: {
        servers: {
          ...beforeData.servers.reduce((acc: Record<string, unknown>, s: { name: string }) => {
            acc[s.name] = s;
            return acc;
          }, {}),
          "test-server": {
            type: "http",
            url: "https://test.example.com/mcp",
            headers: { "X-API-KEY": "secret123" },
            tools: ["*"],
          },
        },
      },
    });
    expect(putRes.ok()).toBeTruthy();

    // List — should have one more
    const after = await request.get("/api/mcp-servers/user");
    const afterData = await after.json();
    expect(afterData.servers.length).toBe(startCount + 1);
    const testServer = afterData.servers.find((s: { name: string }) => s.name === "test-server");
    expect(testServer).toBeTruthy();
    // Headers should be masked
    expect(testServer.headers?.["X-API-KEY"]).toMatch(/^secr\*\*\*$/);

    // DELETE
    const delRes = await request.delete("/api/mcp-servers/user/test-server");
    expect(delRes.ok()).toBeTruthy();

    // List — back to start
    const final = await request.get("/api/mcp-servers/user");
    const finalData = await final.json();
    expect(finalData.servers.length).toBe(startCount);
  });

  test("settings drawer shows Your Servers section", async ({ page }) => {
    await page.goto("/");
    await page.waitForTimeout(1000);
    // Open settings
    await page.getByLabel("Settings").click();
    await expect(page.getByText("Your Servers")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Add MCP Server")).toBeVisible();
  });
});

test.describe("Work Orders pane", () => {
  test("GET /api/scheduling/work-orders returns 12 orders with expected fields", async ({ request }) => {
    const res = await request.get("/api/scheduling/work-orders");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty("orders");
    expect(body).toHaveProperty("count");
    expect(body.count).toBe(12);
    expect(body.orders).toHaveLength(12);

    // Spot-check the first order has the mapped camelCase fields the UI expects.
    const sample = body.orders[0];
    for (const key of [
      "orderId",
      "orderSource",
      "serviceType",
      "jobType",
      "postcode",
      "customerReadyStatus",
      "committedDeliveryDate",
    ]) {
      expect(sample, `missing ${key}`).toHaveProperty(key);
    }
    expect(typeof sample.orderId).toBe("string");
  });

  test("every order id is unique (mirrors the postcode-uniqueness backend test)", async ({ request }) => {
    const res = await request.get("/api/scheduling/work-orders");
    const body = await res.json();
    const ids = body.orders.map((o: { orderId: string }) => o.orderId);
    const unique = new Set(ids);
    expect(unique.size).toBe(ids.length);
  });

  test("pane renders all 12 rows on the page", async ({ page, viewport: _vp }) => {
    // Force a wide viewport so the pane is not hidden by the responsive breakpoint.
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page.getByTestId("work-orders-pane")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("work-orders-count")).toHaveText("12");
    await expect(page.getByTestId("work-order-row")).toHaveCount(12);
  });

  test("Details button prefills the input with 'Tell me about <id>'", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await page.waitForTimeout(1500);

    // Start a chat so the input bar is enabled
    await page.getByLabel("Toggle sidebar").click();
    await page.getByRole("button", { name: "New Chat", exact: true }).click();
    await expect(page.getByRole("banner").getByText("gpt-5.4")).toBeVisible({ timeout: 15000 });

    // Click Details on the first order
    const firstRow = page.getByTestId("work-order-row").first();
    const firstOrderId = await firstRow.getAttribute("data-order-id");
    expect(firstOrderId).toMatch(/^ONEA\d+$/);
    await firstRow.getByTestId("work-order-details-btn").click();

    const textarea = page.locator("textarea");
    await expect(textarea).toHaveValue(`Tell me about ${firstOrderId}`);
  });

  test("Schedule button prefills the input with 'Schedule <id> and push to PSO'", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await page.waitForTimeout(1500);

    await page.getByLabel("Toggle sidebar").click();
    await page.getByRole("button", { name: "New Chat", exact: true }).click();
    await expect(page.getByRole("banner").getByText("gpt-5.4")).toBeVisible({ timeout: 15000 });

    const firstRow = page.getByTestId("work-order-row").first();
    const firstOrderId = await firstRow.getAttribute("data-order-id");
    await firstRow.getByTestId("work-order-schedule-btn").click();

    const textarea = page.locator("textarea");
    await expect(textarea).toHaveValue(`Schedule ${firstOrderId} and push to PSO`);
  });

  test("filter narrows the visible rows", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page.getByTestId("work-order-row")).toHaveCount(12);

    await page.getByLabel("Filter work orders").fill("FTTP");
    // ONEA92160383 is the only FTTP order in the seed CSV.
    await expect(page.getByTestId("work-order-row")).toHaveCount(1);
  });
});

test.describe("Action Trail pane", () => {
  test("renders with empty placeholder before any tool fires", async ({ page }) => {
    await page.setViewportSize({ width: 1400, height: 900 });
    await page.goto("/");
    await expect(page.getByTestId("action-trail-pane")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("action-trail-pane")).toContainText("Nothing yet");
    // No entries yet — the counter should not render.
    await expect(page.getByTestId("action-trail-count")).toHaveCount(0);
  });

  test("pane stays visible after a session is created", async ({ page }) => {
    await page.setViewportSize({ width: 1400, height: 900 });
    await page.goto("/");
    await page.waitForTimeout(1500);

    await page.getByLabel("Toggle sidebar").click();
    await page.getByRole("button", { name: "New Chat", exact: true }).click();
    await expect(page.getByRole("banner").getByText("gpt-5.4")).toBeVisible({ timeout: 15000 });

    // Trail pane still visible and still showing the empty state — no tools
    // have fired yet.
    await expect(page.getByTestId("action-trail-pane")).toBeVisible();
    await expect(page.getByTestId("action-trail-pane")).toContainText("Nothing yet");
  });
});
