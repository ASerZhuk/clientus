import { defineConfig, devices } from "@playwright/test";

// PW_CHROMIUM lets CI/dev machines point at an already installed Chromium build.
const executablePath = process.env.PW_CHROMIUM || undefined;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:13100", trace: "retain-on-failure", launchOptions: { executablePath, args: ["--host-resolver-rules=MAP *.test 127.0.0.1", "--no-proxy-server"] } },
  projects: [
    { name: "mobile", use: { ...devices["iPhone 14"], defaultBrowserType: "chromium" }, testIgnore: /desktop\.spec\.ts/ },
    { name: "desktop", use: { viewport: { width: 1280, height: 800 } }, testMatch: /desktop\.spec\.ts/ },
  ],
  webServer: [
    { command: "sh ../scripts/e2e-api.sh", url: "http://127.0.0.1:18100/api/health", reuseExistingServer: false, timeout: 60_000 },
    { command: "sh scripts/serve.sh 13100", url: "http://127.0.0.1:13100/s/graphite", reuseExistingServer: false, timeout: 60_000, env: { INTERNAL_API_URL: "http://127.0.0.1:18100", PLATFORM_HOSTS: "127.0.0.1,localhost" } },
  ],
});
