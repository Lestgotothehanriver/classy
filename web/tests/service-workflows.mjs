import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
});
const page = await browser.newPage({ viewport: { width: 1280, height: 960 } }),
  errors = [],
  writes = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("dialog", (d) => d.accept());
await page.addInitScript(() => {
  sessionStorage.setItem("classy_token", "mock");
  sessionStorage.setItem("classy_role", "student");
  sessionStorage.setItem("classy_roles", JSON.stringify([{ role: "student" }]));
});
const post = {
  id: 11,
  title: "나의 모집글",
  subjects: ["미적분 I"],
  regions: ["서울 강남구"],
  cost: 100000,
  method: "대면",
  grade: "사회인",
  schedule: "토요일",
  is_active: true,
};
const room = {
  id: 4,
  instructor: 2,
  student: 1,
  opponent_info: { user_id: 2, user_name: "테스트 선생님" },
  messages: [],
};
await page.route("**/api/**", async (route) => {
  const req = route.request(),
    p = new URL(req.url()).pathname.replace("/api", "");
  let d = [];
  if (req.method() !== "GET")
    writes.push({
      path: p,
      method: req.method(),
      body: req.headers()["content-type"]?.includes("application/json")
        ? req.postDataJSON()
        : req.postData(),
    });
  if (p === "/accounts/subjects/") d = [{ number: 36, name: "미적분 I" }];
  else if (p === "/accounts/me/")
    d = { id: 1, nickname: "학생", role: "student", cash: 1000 };
  else if (p === "/accounts/profile-check/")
    d = { available_roles: [{ role: "student" }] };
  else if (p === "/tutoring/my-posts/") d = [post];
  else if (p === "/chatrooms/") d = [room];
  else if (p === "/chatrooms/4/") d = room;
  else if (p === "/tutoring/resources/chatrooms/4/")
    d = {
      student: { id: 1 },
      instructor: { id: 2 },
      contractStatus: "COLLECTING",
    };
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(d),
  });
});
try {
  await page.goto("http://127.0.0.1:4173/#tutoring-manage");
  await page.getByRole("button", { name: "수정", exact: true }).click();
  assert.deepEqual(
    await page
      .locator("select[name=subjects]")
      .evaluate((e) => [...e.selectedOptions].map((x) => x.value)),
    ["36"],
  );
  assert.deepEqual(
    await page
      .locator("select[name=regions]")
      .evaluate((e) => [...e.selectedOptions].map((x) => x.value)),
    ["1"],
  );
  await page.getByLabel("수업 가능 시간").fill("일요일 오후");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await page
    .getByRole("heading", { name: "모집 공고 작성" })
    .waitFor({ state: "hidden" });
  const edit = writes.find((x) => x.path === "/tutoring/posts/write/11/");
  assert.equal(edit.method, "PATCH");
  assert.deepEqual(edit.body.subjects, [36]);
  assert.deepEqual(edit.body.regions, [1]);
  assert.equal(edit.body.cost, 100000);
  await page.goto("http://127.0.0.1:4173/#account");
  await page.getByLabel("새 휴대전화 번호").fill("01098765432");
  await page.getByRole("button", { name: "인증번호 받기" }).click();
  await page.getByLabel("인증번호", { exact: true }).fill("123456");
  await page.getByRole("button", { name: "전화번호 변경 확정" }).click();
  await page
    .getByLabel("인증번호", { exact: true })
    .waitFor({ state: "hidden" });
  assert.deepEqual(
    writes.find((x) => x.path === "/accounts/me/phone/verify/").body,
    { phone: "01098765432", code: "123456" },
  );
  await page.goto("http://127.0.0.1:4173/#chat");
  await page.getByRole("button", { name: /테스트 선생님/ }).click();
  await page.getByRole("button", { name: "성사 등록", exact: true }).click();
  await page.getByLabel("과목 (최대 3개)").selectOption("36");
  await page.getByLabel("수업 시작일").fill("2026-10-01");
  await page.getByLabel("첫 달 수업료 (원)").fill("100000");
  await page
    .getByLabel("페이백 은행")
    .selectOption("국민은행");
  await page.getByLabel("페이백 계좌번호").fill("123456789");
  await page.getByLabel("예금주", { exact: true }).fill("테스트");
  await page
    .getByRole("button", { name: "성사 등록 제출", exact: true })
    .click();
  await page.getByText("과외 성사 등록을 제출했습니다.").first().waitFor();
  const registration = writes.find(
    (x) => x.path === "/tutoring/resources/chatrooms/4/my-registration/",
  );
  assert.equal(registration.method, "PUT");
  assert.deepEqual(registration.body.subjectIds, [36]);
  assert.equal(registration.body.paybackAccount.bankCode, "국민은행");
  assert.equal(registration.body.firstMonthFee, 100000);
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    false,
    "chat overflow",
  );
  assert.deepEqual(errors, []);
  console.log(
    "PASS editing API label-shaped tutoring data, phone verification, student contract payload, mobile chat",
  );
} finally {
  await browser.close();
}
