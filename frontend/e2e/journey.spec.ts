// Full acceptance journey in a real browser against a freshly reset demo database (run scripts/reset_demo.py first).
import { expect, test, type Page } from "@playwright/test";

const SHOTS = process.env.OB_SHOTS ?? "../docs/screenshots";
const metric = (page: Page, label: string) => page.locator(".metric").filter({ has: page.locator(".metric-label", { hasText: new RegExp(`^${label}`) }) });
const shot = async (page: Page, name: string) => {
  await page.addStyleTag({ content: ".topbar{position:static !important} .table-scroll{overflow:visible !important} table.data th{position:static !important}" }); // sticky header repeats mid-page in full-page captures
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
};

test("owner journey: evidence -> decision -> conditional terms -> approved sandbox payment -> receipt", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Password").fill(process.env.ORDERBRIDGE_DEMO_PASSWORD ?? "orderbridge-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Synthetic demo", { exact: true })).toBeVisible();
  await expect(page.getByText("Rule-based replay, no live model").first()).toBeVisible();

  // 1-2 load example and inspect evidence
  await page.getByRole("button", { name: "Load synthetic example" }).click();
  await expect(page.getByText(/Synthetic example loaded: 9 records added/)).toBeVisible();
  await shot(page, "01-overview");
  await page.getByRole("link", { name: "2 Evidence" }).click();
  await page.getByRole("button", { name: "ORD-001-MAT", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Original source values vs normalized" })).toBeVisible();
  await shot(page, "02-evidence");

  // 3-5 decision on current terms
  await page.getByRole("link", { name: "3 Order decision" }).click();
  await expect(page.getByText("Conditional terms").first()).toBeVisible();
  await expect(metric(page, "Lowest balance")).toContainText("-CNY 90,000.00");
  await expect(metric(page, "First shortfall")).toContainText("2026-10-04");
  await expect(metric(page, "Support needed")).toContainText("CNY 110,000.00");
  await page.getByRole("button", { name: /Why this result/ }).click();
  await expect(page.getByText("← lowest")).toBeVisible();
  await page.getByRole("button", { name: "Run replay" }).click();
  await expect(page.locator(".card .decision")).toContainText("Conditional terms");
  await shot(page, "03-decision");

  // 6-7 compare and record acceptance explicitly
  await page.getByRole("link", { name: "4 Compare plans" }).click();
  const combined = page.locator("tr", { hasText: "Deposit + supplier deferral" });
  await expect(combined).toContainText("Conditional");
  await expect(combined).toContainText("CNY 46,000.00");
  await expect(page.locator("tr", { hasText: "Current terms + illustrative loan" })).toContainText("CNY 237,944.93");
  for (const label of ["Buyer pays 30% deposit", "Supplier accepts"]) {
    const row = page.locator(".condition", { hasText: label });
    await row.getByRole("button", { name: "Mark accepted in this synthetic case" }).click();
    await row.getByRole("button", { name: "Confirm: counterparty agreed" }).click();
    await expect(row).toContainText("Accepted");
  }
  await expect(combined).toContainText("Terms accepted");
  await shot(page, "04-compare");

  // 8-10 sandbox, prepare, blocked attempt, approve, execute
  await page.getByRole("button", { name: "Continue to sandbox action" }).click();
  await page.getByRole("button", { name: /Initialize synthetic sandbox/ }).click();
  await expect(page.getByText("Simulated date 2026-10-04").first()).toBeVisible();
  await expect(page.getByText("Available sandbox cash:")).toContainText("CNY 176,000.00");
  await page.getByRole("button", { name: "Prepare payment preview" }).click();
  const preview = page.locator(".preview");
  await expect(preview).toContainText("CNY 176,000.00 → CNY 106,000.00");
  await expect(preview).toContainText("Demo Pearl Materials Co.");
  await preview.getByRole("button", { name: "Demo: execute without approval" }).click();
  await expect(page.getByRole("alert")).toContainText("APPROVAL_REQUIRED");
  await shot(page, "05-action-preview");
  await preview.getByRole("button", { name: "Approve this exact CNY 70,000.00 payment" }).click();
  await expect(preview).toContainText("approved");
  await page.reload(); // state survives reload
  await expect(page.locator(".preview")).toContainText("approved");
  await page.locator(".preview").getByRole("button", { name: "Execute approved sandbox payment" }).click();
  await expect(page.locator(".preview")).toContainText("succeeded");

  // 11 receipt, refresh does not re-execute
  await page.getByRole("button", { name: "View receipt" }).click();
  await expect(page.locator(".receipt")).toContainText("CNY 176,000.00 → CNY 106,000.00");
  await page.getByRole("button", { name: "Refresh action state" }).click();
  await expect(page.getByText(/Refreshing never re-executes/)).toBeVisible();
  await expect(page.locator(".receipt")).toContainText("CNY 106,000.00");
  await shot(page, "06-receipt");

  // 12 blocked request (over per-payment limit)
  await page.getByRole("link", { name: "5 Approval & action" }).click();
  await page.getByRole("button", { name: "Demo: try CNY 120,000 (over limit)" }).click();
  await expect(page.locator(".preview")).toContainText("blocked");
  await expect(page.locator(".checks li.fail", { hasText: "per_payment_limit" })).toBeVisible();
  await shot(page, "07-blocked");
  await expect(page.getByText("Available sandbox cash:")).toContainText("CNY 106,000.00");

  // returning between screens keeps state
  await page.getByRole("link", { name: "4 Compare plans" }).click();
  await expect(page.locator("tr", { hasText: "Deposit + supplier deferral" })).toContainText("Terms accepted");
  await page.getByRole("link", { name: "6 Receipt & audit" }).click();
  await expect(page.locator("table").last()).toContainText("action_executed");
});

test("narrow viewport renders without horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("Password").fill(process.env.ORDERBRIDGE_DEMO_PASSWORD ?? "orderbridge-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  for (const r of ["overview", "decision", "compare", "action", "receipt"]) {
    await page.goto(`/#/${r}`);
    await page.waitForTimeout(400);
    const { overflow, offenders } = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      offenders: [...document.querySelectorAll("body *")]
        .filter((e) => e.getBoundingClientRect().right > window.innerWidth + 1 && !e.closest(".table-scroll, .tabs"))
        .slice(0, 5).map((e) => `${e.tagName}.${e.className}`),
    }));
    expect(overflow, `horizontal overflow on ${r}: ${offenders.join(", ")}`).toBeLessThanOrEqual(1);
  }
  await page.goto("/#/decision");
  await page.waitForTimeout(400);
  await shot(page, "08-mobile-decision");
});

test("viewer is read-only", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("viewer@demo-gba");
  await page.getByLabel("Password").fill(process.env.ORDERBRIDGE_DEMO_PASSWORD ?? "orderbridge-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("button", { name: "Load synthetic example" })).toBeDisabled();
  await page.goto("/#/action");
  await expect(page.getByRole("button", { name: /Approve this exact/ })).toHaveCount(0);
});
