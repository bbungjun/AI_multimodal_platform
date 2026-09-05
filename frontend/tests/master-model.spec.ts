import { test, expect } from "@playwright/test";
import { createCommand, formatCredit, parseReceipt, parseUser } from "../src/ui/master";

const id = "00000000-0000-4000-8000-000000000001";
test("decimal Credit preserves microprecision beyond safe integer totals", () => {
  expect(formatCredit("9007199254740991000001")).toBe("9,007,199,254,740,991.000001");
  expect(formatCredit("1")).toBe("0.000001");
});
for (const amount of ["1e3", "-1", "0", "1.0000001", " 1", "9000000001"]) {
  test(`invalid amount form ${amount}`, () => {
    expect(() => createCommand("bonus_grant", "support_adjustment", "free", amount, "", id)).toThrow();
  });
}
test("command is immutable and exact, with stable supplied request ID", () => {
  const c = createCommand("bonus_grant", "support_adjustment", "free", "10.000001", "", id);
  expect(c.amount_microcredits).toBe(10_000_001); expect(c.request_id).toBe(id);
  expect(Object.isFrozen(c)).toBe(true);
});
test("expired bonus and arbitrary reason refused", () => {
  expect(() => createCommand("bonus_grant", "support_adjustment", "free", "1", "2020-01-01", id)).toThrow();
  expect(() => createCommand("suspend", "private text", "free", "", "", id)).toThrow();
});
test("malformed user and unsafe receipt value refused", () => {
  expect(() => parseUser({ id })).toThrow();
  expect(() => parseReceipt({ request_id: id, action: "suspend", before: {},
    after: { email: "forbidden" }, created_at: "2025-01-01T00:00:00Z", replayed: false })).toThrow();
});
