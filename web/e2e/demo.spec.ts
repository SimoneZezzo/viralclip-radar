import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(message.text());
  });
  page.on("pageerror", (error) => problems.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("list", { name: "Clips ranked by score" }).getByRole("button")).toHaveCount(6);
  // Console errors include CSP violations, which must not happen on the built page.
  expect(problems).toEqual([]);
});

test("shows the synthetic ranking and an honest clip card", async ({ page }) => {
  await expect(page.getByText("Local demo · Synthetic data")).toBeVisible();
  await expect(page.getByText("Simulated model")).toBeVisible();
  await expect(page.getByRole("button", { name: "Open on Twitch" })).toBeDisabled();
  await expect(page.getByRole("status")).toContainText("Synthetic clip: there is no Twitch page");
  await expect(page.getByRole("list", { name: "External editors" }).getByRole("link")).toHaveCount(4);
});

test("copies the clip link", async ({ page }) => {
  await page.getByRole("button", { name: "Copy clip link" }).click();
  await expect(page.getByRole("status")).toContainText("Link copied.");
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toMatch(/^https:\/\/example\.invalid\/synthetic-clips\//);
});

test("switches to the baseline game", async ({ page }) => {
  await page.getByRole("combobox", { name: "Game" }).selectOption("32982");
  await expect(page.getByText("Baseline", { exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "Clips ranked by score" }).getByRole("button")).toHaveCount(4);
});

// DESIGN.md asks for checks at these widths with no horizontal scroll.
for (const width of [1264, 850, 665, 320]) {
  test(`has no horizontal scroll at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
    await expect(page.getByRole("heading", { name: "Twitch Shortlist" })).toBeVisible();
  });
}
