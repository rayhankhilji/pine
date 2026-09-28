import { expect, test, type APIRequestContext } from "@playwright/test";

const API_URL = "http://localhost:8000";

async function createDeal(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${API_URL}/api/v1/deals`, {
    data: { name: "E2E Viewer Deal", company_name: "Viewer Co", stage: "seed" },
  });
  expect(res.ok()).toBeTruthy();
  const body = (await res.json()) as { id: string };
  return body.id;
}

async function uploadDoc(
  request: APIRequestContext,
  dealId: string,
  file: { name: string; mimeType: string; buffer: Buffer },
): Promise<string> {
  const res = await request.post(`${API_URL}/api/v1/deals/${dealId}/documents`, {
    multipart: { files: file },
  });
  expect(res.ok()).toBeTruthy();
  const body = (await res.json()) as { documents: { id: string }[] };
  return body.documents[0].id;
}

async function waitParsed(request: APIRequestContext, docId: string) {
  await expect
    .poll(
      async () => {
        const res = await request.get(`${API_URL}/api/v1/documents/${docId}`);
        const body = (await res.json()) as { status: string };
        return body.status;
      },
      { timeout: 60_000, intervals: [1_000] },
    )
    .toBe("parsed");
}

test("viewer renders a text document with page text panel", async ({
  page,
  request,
}) => {
  const dealId = await createDeal(request);
  const docId = await uploadDoc(request, dealId, {
    name: "summary.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Summary\n\nRevenue grew to $9.7M in FY2025."),
  });
  await waitParsed(request, docId);

  await page.goto(`/deals/${dealId}/documents/${docId}`);
  await expect(
    page.getByRole("heading", { name: "summary.md" }),
  ).toBeVisible();
  await expect(
    page.getByText("Revenue grew to $9.7M in FY2025.").first(),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /Original/ })).toBeVisible();
});

test("viewer renders a csv as a spreadsheet table", async ({
  page,
  request,
}) => {
  const dealId = await createDeal(request);
  const docId = await uploadDoc(request, dealId, {
    name: "cap_table.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("holder,shares\nFounders,6000000\nInvestors,3000000\n"),
  });
  await waitParsed(request, docId);

  await page.goto(`/deals/${dealId}/documents/${docId}`);
  await expect(page.getByRole("cell", { name: "Founders" })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByRole("cell", { name: "6000000" })).toBeVisible();
});
