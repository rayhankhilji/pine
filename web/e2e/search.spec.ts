import { expect, test, type APIRequestContext } from "@playwright/test";

const API_URL = "http://localhost:8000";

async function createDeal(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${API_URL}/api/v1/deals`, {
    data: { name: "E2E Search Deal", company_name: "Search Co", stage: "series_b" },
  });
  expect(res.ok()).toBeTruthy();
  return ((await res.json()) as { id: string }).id;
}

async function waitFor(
  fn: () => Promise<boolean>,
  timeoutMs = 60_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await fn()) return;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("timed out waiting");
}

test("search UI returns hits and links to the document page", async ({
  page,
  request,
}) => {
  const dealId = await createDeal(request);

  const upload = await request.post(
    `${API_URL}/api/v1/deals/${dealId}/documents`,
    {
      multipart: {
        files: {
          name: "growth-notes.txt",
          mimeType: "text/plain",
          buffer: Buffer.from(
            "Growth review. Annual recurring revenue reached $12.0M in Q4 2025, " +
              "up 3x year over year. Net revenue retention 118%.",
          ),
        },
      },
    },
  );
  expect(upload.status()).toBe(201);

  // parsing auto-enqueues indexing; poll until the index reports ready
  await request.post(`${API_URL}/api/v1/deals/${dealId}/index`);
  await waitFor(async () => {
    const res = await request.get(`${API_URL}/api/v1/deals/${dealId}/index`);
    if (!res.ok()) return false;
    const body = (await res.json()) as { status: string };
    return body.status === "ready";
  });

  await page.goto(`/deals/${dealId}/search`);
  await page.getByLabel("Search query").fill("annual recurring revenue");
  await page.getByRole("button", { name: "Search", exact: true }).click();

  const hit = page.getByRole("link", { name: /growth-notes\.txt/ });
  await expect(hit).toBeVisible({ timeout: 30_000 });
  await expect(hit.locator("mark").first()).toBeVisible();
  await hit.click();
  await expect(page).toHaveURL(/\/documents\/.+\?page=1/);
});
