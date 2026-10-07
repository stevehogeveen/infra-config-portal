import { expect, type Page } from "@playwright/test";

export async function saveRack(page: Page) {
  await page.getByRole("button", { name: "Save a copy", exact: true }).click();
  await page.getByLabel("Save location", { exact: true }).selectOption("browser");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Save a rack plan copy" })).toBeHidden();
  await expect(page.getByRole("status")).toContainText("Rack plan saved");
}
