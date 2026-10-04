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
  grade: "고2",
  schedule: "토요일",
  relative_time: "방금 전",
  view_count: 7,
  is_active: true,
};
const postDetail = {
  ...post,
  subjects: [{ label: "미적분 I" }],
  regions: [{ label: "서울 강남구" }],
  sex: "여",
  age: 17,
  field: "이과",
  situation: "내신 수학을 보완하고 싶어요.",
  etc: "고등 수학 지도 경험이 있는 선생님을 원해요.",
  created_at: "2026-10-04T09:00:00+09:00",
  student: { id: 1 },
};
const room = {
  id: 4,
  instructor: 2,
  student: 1,
  opponent_info: { user_id: 2, user_name: "테스트 선생님" },
  messages: [],
};
let registrationComplete = false;
const completedRegistration = {
  chatRoomId: 4,
  subject: "미적분 I",
  startDate: "2026-10-01",
  contractStatus: "ACTIVE",
  studentSubmitted: true,
  instructorSubmitted: true,
  mySubmission: {
    classType: "REGULAR",
    firstMonthFee: 100000,
  },
};
const tutoringResource = {
  id: 9,
  instructor: 2,
  student: 1,
  instructor_user_name: "테스트 선생님",
  class_type: "정규 수업",
  start_date: "2026-10-01",
  fee_payment_status: "AWAITING_CONFIRMATION",
  contract_status: "REGISTERED",
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
  else if (p === "/tutoring/posts/11/") d = postDetail;
  else if (p === "/tutoring/students/1/reviews/")
    d = [
      {
        id: 3,
        instructor_nickname: "수학 선생님",
        rating: 5,
        comment: "성실하게 수업에 참여했어요.",
        created_at: "2026-10-03T09:00:00+09:00",
      },
    ];
  else if (p === "/tutoring/resources/") d = [tutoringResource];
  else if (p === "/chatrooms/") d = [room];
  else if (p === "/chatrooms/4/") d = room;
  else if (p === "/tutoring/resources/chatrooms/4/")
    d = registrationComplete
      ? completedRegistration
      : {
          chatRoomId: 4,
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
  await page.getByText("관리자 확인 중", { exact: true }).waitFor();
  await page
    .getByRole("tab", { name: "성사 등록 진행 중", exact: true })
    .click();
  await page.getByText("관리자 확인 중", { exact: true }).waitFor();
  await page.getByRole("tab", { name: "전체", exact: true }).click();
  await page.getByRole("button", { name: /나의 모집글/ }).click();
  await page.getByText("학생 정보", { exact: true }).waitFor();
  await page.getByText("여 · 만 17세 · 고2 · 이과", { exact: true }).waitFor();
  await page.getByText("서울 강남구", { exact: true }).waitFor();
  await page.getByText("고등 수학 지도 경험이 있는 선생님을 원해요.").waitFor();
  await page.getByRole("tab", { name: "과외 리뷰", exact: true }).click();
  await page.getByText("수학 선생님 · 5점", { exact: true }).waitFor();
  await page.keyboard.press("Escape");
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
  registrationComplete = true;
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "수업 정보", exact: true }).waitFor();
  await page.getByRole("button", { name: "수업 정보", exact: true }).click();
  await page.getByText("수업 과목", { exact: true }).waitFor();
  await page.getByText("미적분 I", { exact: true }).waitFor();
  await page.getByText("수업 시작일", { exact: true }).waitFor();
  await page.getByText("2026.10.01", { exact: true }).waitFor();
  await page.getByText("수업 형태", { exact: true }).waitFor();
  await page.getByText("정규 수업", { exact: true }).waitFor();
  await page.getByText("총 수업료", { exact: true }).waitFor();
  await page.getByText("100,000원", { exact: true }).waitFor();
  assert.equal(
    await page.getByRole("button", { name: "성사 등록 제출", exact: true }).count(),
    0,
  );
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
