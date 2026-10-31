import { defineConfig } from "@playwright/test"

export default defineConfig({
  testDir: "./tests/ui",
  workers: 1,
  timeout: 30000,
  use: {
    channel: "msedge",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    baseURL: "http://127.0.0.1:5187",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5187 --strictPort",
    url: "http://127.0.0.1:5187",
    reuseExistingServer: false,
  },
})
