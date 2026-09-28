import { expect, test, type APIRequestContext } from "@playwright/test";

const API_URL = "http://localhost:8000";

async function createDeal(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${API_URL}/api/v1/deals`, {
    data: {
      name: "E2E Docs Deal",
      company_name: "Docs Co",
      stage: "series_b",
    },
  });
  expect(res.ok()).toBeTruthy();
  const body = (await res.json()) as { id: string };
  return body.id;
}

test("upload a markdown file and watch it parse", async ({ page, request }) => {
  const dealId = await createDeal(request);
  await page.goto(`/deals/${dealId}/documents`);

  // empty state shows the dropzone prompt
  await expect(page.getByText(/Drag a data room here/)).toBeVisible();

  await page
    .locator('input[type="file"]')
    .setInputFiles({
      name: "notes.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Diligence notes\n\nARR discussed at $12M."),
    });

  await expect(page.getByRole("link", { name: "notes.md" })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("parsed").first()).toBeVisible({
    timeout: 60_000,
  });
});

test("upload a csv shows parsed status and unreadable group hidden", async ({
  page,
  request,
}) => {
  const dealId = await createDeal(request);
  await page.goto(`/deals/${dealId}/documents`);

  await page.locator('input[type="file"]').setInputFiles({
    name: "customers.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("customer,arr\nAcme,6700000\nBorealis,1200000\n"),
  });

  await expect(page.getByRole("link", { name: "customers.csv" })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("parsed").first()).toBeVisible({
    timeout: 60_000,
  });
  // nothing failed → no unreadable group
  await expect(page.getByText("Unreadable files")).toHaveCount(0);
});
