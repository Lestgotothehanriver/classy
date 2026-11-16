import test from "node:test";
import assert from "node:assert/strict";
import {
  getRegistrationFlow,
  getRegistrationResultScreen,
  getRegistrationStatus,
  getLatestClassResource,
} from "../src/tutoring-state.js";

test("maps completed and rejected registration contracts", () => {
  assert.deepEqual(getRegistrationStatus({ contractStatus: "ACTIVE", payment: { status: "PAID" } }), {
    label: "성사 등록 완료",
    tone: "complete",
    isComplete: true,
  });
  assert.equal(
    getRegistrationStatus({ contractStatus: "ACTIVE", payment: { status: "PENDING" } })
      .isComplete,
    false,
  );
  assert.deepEqual(getRegistrationStatus({ payment: { status: "PAYMENT_PENDING" } }), {
    label: "관리자 확인 중",
    tone: "pending",
    isComplete: false,
  });
  assert.equal(
    getRegistrationFlow({ attributeValidationStatus: "MISMATCHED" }).isRejected,
    true,
  );
});

test("selects the latest non-cancelled class resource for a chat room", () => {
  const resource = getLatestClassResource(
    [
      { id: 1, chat_room_id: 7, created_at: "2026-11-16T01:00:00Z" },
      { id: 2, chatRoomId: 7, createdAt: "2026-11-16T02:00:00Z" },
      { id: 3, chat_room_id: 7, is_cancelled: true, created_at: "2026-11-16T03:00:00Z" },
      { id: 4, chat_room_id: 8, created_at: "2026-11-16T04:00:00Z" },
    ],
    "7",
  );

  assert.equal(resource?.id, 2);
});

test("maps role-specific waiting copy and resumable teacher proof", () => {
  const waiting = getRegistrationFlow(
    { mySubmissionFinalized: true, counterpartySubmission: { submitted: false } },
    { isTeacher: false },
  );
  assert.equal(waiting.waitingForCounterparty, true);
  assert.match(waiting.pendingDescription, /선생님의 성사 등록/);

  const proof = getRegistrationFlow(
    { mySubmission: { isFinalized: false }, mySubmissionFinalized: false, payment: { status: "READY" } },
    { isTeacher: true },
  );
  assert.equal(proof.canResumeTeacherProof, true);
});

test("identifies counterparty-first and rejected registration rounds", () => {
  const counterpartyFirst = getRegistrationFlow(
    { mySubmissionFinalized: false, counterpartySubmission: { submitted: true } },
    { isTeacher: true },
  );
  assert.equal(counterpartyFirst.counterpartySubmitted, true);
  assert.equal(counterpartyFirst.mineFinalized, false);

  const rejected = getRegistrationFlow({ payment: { status: "FAILED" } });
  assert.equal(rejected.isPaymentRejected, true);
  assert.equal(rejected.isRejected, true);

  assert.equal(
    getRegistrationFlow({ contractStatus: "CANCELLED" }).isCancelled,
    true,
  );
});

test("matches app result-screen branches for success, failure, and pending", () => {
  assert.equal(
    getRegistrationResultScreen({ contractStatus: "ACTIVE", payment: { status: "PAID" } }),
    "success",
  );
  assert.equal(
    getRegistrationResultScreen({ payment: { status: "FAILED" } }, { submitted: true }),
    "failure",
  );
  assert.equal(
    getRegistrationResultScreen({ payment: { status: "FAILED" } }),
    null,
  );
  assert.equal(
    getRegistrationResultScreen({ mySubmissionFinalized: true }),
    "pending",
  );
});
