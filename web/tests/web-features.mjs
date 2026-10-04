const origin=process.env.CLASSY_TEST_ORIGIN || 'http://127.0.0.1:4173';
import { mkdirSync } from "node:fs";
mkdirSync("test-results", { recursive: true });
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }),
  errors = [],
  writes = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console",m=>{if(m.type()==="error")errors.push(m.text());});
let role = "student",
  created = false;
const subjects = [
  { number: 36, name: "미적분 I" },
  { number: 196, name: "Python" },
];
const lecture = {
  id: 7,
  title: "실제 형식의 강의",
  content: "기초부터 배우기",
  subjects: [36],
  price: 1000,
  is_active: true,
  view_count: 3,
};
await page.route("**/api/**", async (route) => {
  const req = route.request(),
    path = new URL(req.url()).pathname.replace("/api", "");
  let d = [],
    status = 200;
  if (req.method() !== "GET")
    writes.push({
      path,
      method: req.method(),
      body: req.headers()["content-type"]?.includes("application/json")
        ? req.postDataJSON()
        : req.postData(),
    });
  if (path === "/accounts/subjects/") d = subjects;
  else if (
    path === "/accounts/check-email/" ||
    path === "/accounts/check-username/"
  )
    d = { available: true };
  else if (path === "/accounts/send-auth-sms/") d = { message: "sent" };
  else if (path === "/accounts/verify-auth-sms/") d = { message: "verified" };
  else if (path === "/accounts/password-reset/verify/")
    d = { reset_token: "one-time-test-token" };
  else if (path.startsWith("/accounts/signup/")) {
    role = path.includes("instructor") ? "instructor" : "student";
    d = { token: "test-token", available_roles: [{ role }] };
  } else if (path === "/accounts/me/")
    d = {
      id: 1,
      nickname: "웹 회원",
      role,
      cash: 1000,
      email: "test@example.invalid",
    };
  else if (path === "/accounts/profile-check/")
    d = { available_roles: [{ role }] };
  else if (path === "/lectures/")
    d = { count: 1, results: [lecture], next: null };
  else if (path === "/mypage/instructor/uploaded-lectures/")
    d = created ? [lecture] : [];
  else if (path === "/lectures/write/") {
    created = true;
    d = lecture;
  } else if (path === "/mypage/instructor/settlement-info/")
    d = { total_revenue: 1000, settleable_revenue: 1000 };
  else if (path === "/pending/") d = { exists: false };
  else if (path === "/tutoring/instructor-info/mine/") {
    d = null;
    status = 204;
  }
  await route.fulfill({
    status,
    contentType: "application/json",
    body: status === 204 ? "" : JSON.stringify(d),
  });
});
try {
  await page.goto(origin+"/#lectures");
  await page.getByRole("heading", { name: "실제 형식의 강의" }).waitFor();
  await page.getByRole("heading", { name: "실제 형식의 강의" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "회원가입", exact: true })
    .click();
  await page.getByLabel("이메일", { exact: true }).fill("test@example.invalid");
  await page.getByLabel("휴대전화 번호", { exact: true }).fill("01012345678");
  await page
    .getByRole("button", { name: "인증번호 받기", exact: true })
    .click();
  await page.getByLabel("인증번호", { exact: true }).fill("123456");
  await page.getByRole("button", { name: "인증 확인", exact: true }).click();
  await page.getByLabel("비밀번호", { exact: true }).fill("test-password");
  await page.getByLabel("비밀번호 확인", { exact: true }).fill("test-password");
  await page.getByLabel("닉네임", { exact: true }).fill("웹 회원");
  await page.getByLabel("생년월일", { exact: true }).fill("2000-01-01");
  await page.getByLabel("활동 지역", { exact: true }).fill("서울 강남구");
  await page.getByLabel("관심 과목").selectOption("36");
  const requiredChecks = page.getByRole("checkbox").filter({ visible: true });
  await requiredChecks.nth(0).check();
  await requiredChecks.nth(1).check();
  await page.getByRole("button", { name: "회원가입", exact: true }).click();
  await page.getByRole("heading", { name: "웹 회원님, 반가워요." }).waitFor();
  await page.goto(origin + "/#lectures");
  await page.getByRole("heading", { name: "실제 형식의 강의" }).waitFor();
  const studentBrowseMenu = page.getByRole("navigation", {
    name: "목록 메뉴",
  });
  assert.equal(
    await studentBrowseMenu.getByRole("link", { name: "학생 찾기" }).count(),
    0,
  );
  assert.equal(
    await studentBrowseMenu.getByRole("link", { name: "선생님 찾기" }).count(),
    1,
  );
  const signup = writes.find((x) => x.path === "/accounts/signup/student/");
  assert.equal(signup.body.phone, "01012345678");
  assert.deepEqual(signup.body.studentsubject, [36]);
  assert.equal(signup.body.agreed_marketing, false);
  // Use mocked identity, never create or mutate production accounts.
  role = "instructor";
  await page.evaluate(() => {
    sessionStorage.setItem("classy_role", "instructor");
    sessionStorage.setItem(
      "classy_roles",
      JSON.stringify([{ role: "instructor" }]),
    );
  });
  await page.goto(origin+"/#upload");
  await page.reload();
  await page.getByRole("heading", { name: "강사 스튜디오" }).waitFor();
  await page.goto(origin + "/#lectures");
  await page.getByRole("heading", { name: "실제 형식의 강의" }).waitFor();
  const instructorBrowseMenu = page.getByRole("navigation", {
    name: "목록 메뉴",
  });
  assert.equal(
    await instructorBrowseMenu
      .getByRole("link", { name: "선생님 찾기" })
      .count(),
    0,
  );
  assert.equal(
    await instructorBrowseMenu.getByRole("link", { name: "학생 찾기" }).count(),
    1,
  );
  await page.goto(origin + "/#upload");
  await page.getByRole("heading", { name: "강사 스튜디오" }).waitFor();
  await page.getByLabel("강의 제목").fill("임시 저장 제목");
  await page.reload();
  await page.getByLabel("강의 제목").waitFor();
  assert.equal(
    await page.getByLabel("강의 제목").inputValue(),
    "임시 저장 제목",
  );
  const video = await page.evaluate(async () => {
    const c = document.createElement("canvas");
    c.width = 320;
    c.height = 180;
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#5f65d7";
    ctx.fillRect(0, 0, 320, 180);
    const stream = c.captureStream(10),
      rec = new MediaRecorder(stream, { mimeType: "video/webm" }),
      chunks = [];
    rec.ondataavailable = (e) => chunks.push(e.data);
    const stopped = new Promise((r) => (rec.onstop = r));
    rec.start();
    await new Promise((r) => setTimeout(r, 350));
    ctx.fillRect(0, 0, 320, 180);
    await new Promise((r) => setTimeout(r, 350));
    rec.stop();
    await stopped;
    stream.getTracks().forEach((t) => t.stop());
    return Array.from(new Uint8Array(await new Blob(chunks).arrayBuffer()));
  });
  await page.locator('input[type=file][accept="video/*"]').setInputFiles({
    name: "sample.webm",
    mimeType: "video/webm",
    buffer: Buffer.from(video),
  });
  await page.waitForFunction(
    () => document.querySelector("video")?.videoWidth > 0,
  );
  await page.getByRole("button", { name: "현재 장면을 썸네일로 사용" }).click();
  await page.getByAltText("선택한 썸네일").waitFor();
  await page.getByLabel("강의 소개").fill("기초 개념을 익히는 강의입니다.");
  await page.getByLabel("과목 (최대 3개)").selectOption("36");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/studio-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "강의 게시", exact: true }).click();
  await page.getByRole("heading", { name: "실제 형식의 강의" }).waitFor();
  const upload = writes.find((x) => x.path === "/lectures/write/");
  assert.match(upload.body, /name="subjects"\r\n\r\n36/);
  assert.match(upload.body, /name="thumbnail"/);
  assert.equal(
    await page.evaluate(() => localStorage.getItem("classy_draft_1")),
    null,
  );
  for (const view of [
    "studio",
    "cash",
    "settlement",
    "verification",
    "account",
    "tutoring-manage",
    "support",
  ]) {
    await page.goto(origin+"/#" + view);
    await page.waitForTimeout(100);
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
      view + " desktop overflow",
    );
  }
  await page.setViewportSize({ width: 390, height: 844 });
  for (const view of ["upload", "account", "tutoring-manage"]) {
    await page.goto(origin+"/#" + view);
    await page.waitForTimeout(100);
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
      view + " mobile overflow",
    );
  }
  await page.goto(origin+"/#upload");
  await page.screenshot({
    path: "test-results/studio-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1280, height: 960 });
  await page.evaluate(() => sessionStorage.clear());
  await page.goto(origin+"/#home");
  await page.reload();
  await page
    .getByRole("button", { name: "로그인", exact: true })
    .first()
    .click();
  await page
    .getByRole("button", { name: "비밀번호 찾기", exact: true })
    .click();
  await page.getByLabel("휴대전화 번호", { exact: true }).fill("01012345678");
  await page
    .getByRole("button", { name: "인증번호 받기", exact: true })
    .click();
  await page.getByLabel("인증번호", { exact: true }).fill("123456");
  await page.getByRole("button", { name: "인증 확인", exact: true }).click();
  await page.getByLabel("새 비밀번호", { exact: true }).fill("new-password");
  await page.getByLabel("비밀번호 확인", { exact: true }).fill("new-password");
  await page
    .getByRole("button", { name: "비밀번호 변경", exact: true })
    .click();
  await page
    .getByText("비밀번호를 변경했습니다. 새 비밀번호로 로그인해 주세요.")
    .waitFor();
  assert.equal(
    writes.find((x) => x.path === "/accounts/password-reset/confirm/").body
      .reset_token,
    "one-time-test-token",
  );
  await page.getByRole("button", { name: "회원가입", exact: true }).click();
  await page
    .getByRole("button", { name: "선생님으로 가입", exact: true })
    .click();
  await page
    .getByLabel("이메일", { exact: true })
    .fill("teacher@example.invalid");
  await page
    .getByRole("button", { name: "인증번호 받기", exact: true })
    .click();
  await page.getByLabel("인증번호", { exact: true }).fill("123456");
  await page.getByRole("button", { name: "인증 확인", exact: true }).click();
  await page.getByLabel("비밀번호", { exact: true }).fill("test-password");
  await page.getByLabel("비밀번호 확인", { exact: true }).fill("test-password");
  await page.getByLabel("닉네임", { exact: true }).fill("웹 선생님");
  await page.getByLabel("생년월일", { exact: true }).fill("2000-01-01");
  await page.getByLabel("활동 지역", { exact: true }).fill("서울 강남구");
  await page.getByLabel("관심 과목").selectOption("196");
  await page.getByLabel("학교", { exact: true }).fill("테스트 대학");
  await page.getByLabel("학과", { exact: true }).fill("컴퓨터공학");
  await page.getByLabel("입학 연도", { exact: true }).fill("2020");
  await page.getByRole("checkbox").nth(0).check();
  await page.getByRole("checkbox").nth(1).check();
  await page.getByRole("button", { name: "회원가입", exact: true }).click();
  await page.getByRole("heading", { name: "웹 회원님, 반가워요." }).waitFor();
  assert.equal(
    writes.find((x) => x.path === "/accounts/signup/instructor/").body
      .instructorsubject,
    "[196]",
  );
  assert.deepEqual(errors, []);
  console.log(
    "PASS guest lectures, SMS signup payload, draft restore, video thumbnail and multipart upload, service routes, desktop/mobile layout",
  );
} finally {
  await browser.close();
}
