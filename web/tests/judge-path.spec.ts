import { expect, test } from "@playwright/test";

// The judge path (handbook p.17). Run: npm run test:e2e (first time: npx playwright install chromium).

test("opens on the sample with every card's numbers above the fold", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Compare winter crop plans" })).toBeVisible();
  await expect(page.getByText(/Union County, NC · Sample field/)).toBeVisible();
  if (testInfo.project.name.startsWith("laptop")) {
    for (const name of ["What you do now", "Add winter cover", "Add a grain crop"]) {
      const card = page.getByRole("article", { name });
      await expect(card.locator(".sc-headline")).toBeInViewport({ ratio: 1 });
    }
  }
});

test("a dry spring changes the weather and the check, not the plan", async ({ page }) => {
  await page.goto("/");
  const cover = page.getByRole("article", { name: "Add winter cover" });
  const plan = cover.locator(".sc-sequence");
  const before = await plan.innerText();
  await page.getByRole("button", { name: /^Dry spring/ }).click();
  await expect(cover.getByText("Check field moisture")).toBeVisible();
  await expect(page.getByRole("article", { name: "What you do now" }).getByText("Check field moisture")).toHaveCount(0);
  expect(await plan.innerText()).toBe(before);
  await expect(page).toHaveURL(/y=\d{4}/);
});

test("evidence keeps the year and returns focus", async ({ page }) => {
  await page.goto("/#s=cover&y=2014");
  const open = page.getByRole("navigation", { name: "Plan actions" }).getByRole("button", { name: "Show evidence" });
  await open.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(open).toBeFocused();
  await expect(page).toHaveURL(/y=2014/);
});

test("a date in the wrong order shows the error beside the field", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Edit farm dates" }).click();
  await page.getByLabel("When would you end the rye cover?").fill("2027-05-20");
  await page.getByRole("button", { name: "Apply dates" }).click();
  await expect(page.getByText("Choose a rye end date after seeding and before soybean planting for this comparison.")).toBeVisible();
  await expect(page.getByLabel("When would you end the rye cover?")).toBeFocused();
});

test("reset and broken links return to the sample", async ({ page }) => {
  await page.goto("/#s=grain&y=1986");
  await page.getByRole("button", { name: "Reset example" }).click();
  await expect(page).toHaveURL(/#s=cover$/);
  await page.goto("/#s=nope&y=1850");
  await expect(page.getByRole("heading", { name: "Compare winter crop plans" })).toBeVisible();
});
