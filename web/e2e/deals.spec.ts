import { expect, test } from "@playwright/test";

test("home shows API status and deals table", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Pine" })).toBeVisible();
  await expect(page.getByText(/^api:/)).toBeVisible();
});

test("create deal via dialog", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "New deal" }).click();
  await page.getByPlaceholder("Deal name").fill("E2E Test Deal");
  await page.getByPlaceholder("Company name").fill("E2E Co");
  await page.getByRole("button", { name: "Create deal" }).click();
  await expect(
    page.getByRole("link", { name: "E2E Test Deal" }),
  ).toBeVisible();
});

test("load demo navigates to documents and ingests", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/");
  await page.getByRole("button", { name: "Load demo" }).click();
  await expect(page).toHaveURL(/\/deals\/[^/]+\/documents/, {
    timeout: 30_000,
  });
  // the Northwind room parses in the background; wait for parsed rows
  await expect(
    page.getByRole("heading", { name: "Northwind SaaS — Series B" }),
  ).toBeVisible({ timeout: 30_000 });
  await expect(
    page.getByRole("cell", { name: "parsed" }).first(),
  ).toBeVisible({ timeout: 120_000 });
});
