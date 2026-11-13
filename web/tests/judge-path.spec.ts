import { expect, test } from "@playwright/test";

// Phase 0 smoke test. Later phases extend it with the evidence drawer and rye slider (cases A–L).

test("opens on the sample with a result above the fold", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Compare winter crop plans" })).toBeVisible();
  await expect(page.getByText("Union County, NC · Sample field")).toBeVisible();
  // Layout B: on the 1280×720 projector size the cards must start above the fold.
  // On a phone they follow the strip and 3D band in the same order, below the fold by design.
  if (testInfo.project.name.startsWith("laptop")) {
    await expect(page.getByRole("heading", { name: "Protect the soil" })).toBeInViewport();
  }
});

test("picking a year changes the weather line, not the plan", async ({ page }) => {
  await page.goto("/");
  const metric = page.getByText(/12 days before planting/);
  await expect(metric).toBeVisible();
  await page.getByRole("button", { name: /^1986:/ }).click();
  await expect(page.getByText(/^Spring 1986/)).toBeVisible();
  await expect(metric).toBeVisible();
  await expect(page).toHaveURL(/y=1986/);
});

test("reset returns to the sample", async ({ page }) => {
  await page.goto("/#s=earn-more&y=1986");
  await page.getByRole("button", { name: "Reset example" }).click();
  await expect(page).toHaveURL(/s=protect-soil$/);
});

test("a broken link opens the sample", async ({ page }) => {
  await page.goto("/#s=nope&y=1850");
  await expect(page.getByRole("heading", { name: "Compare winter crop plans" })).toBeVisible();
});
