import { defineConfig } from "@playwright/test";

const API_URL = "http://localhost:8000";
const WEB_URL = "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  // serial: all tests share one SQLite file; parallel writers lock it
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html"]] : [["list"]],
  use: {
    baseURL: WEB_URL,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command:
        "uv run --directory ../api alembic upgrade head && uv run --directory ../api pine serve --port 8000",
      url: `${API_URL}/api/v1/health`,
      env: {
        LLM_PROVIDER: "fake",
        EMBEDDINGS_PROVIDER: "hash",
        DATABASE_URL: "sqlite:////tmp/pine-e2e.db",
        STORAGE_DIR: "/tmp/pine-e2e-storage",
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "pnpm dev --port 3000",
      url: WEB_URL,
      env: {
        NEXT_PUBLIC_API_URL: API_URL,
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
