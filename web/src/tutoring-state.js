/**
 * Normalizes tutoring-registration fields returned by the chat-room and
 * resource endpoints. Both endpoints intentionally expose a slightly
 * different casing, so UI must not interpret their raw values independently.
 */
export function getRegistrationStatus(data = {}) {
  const contractStatus = String(
    data.contractStatus ?? data.contract_status ?? "",
  ).toUpperCase();
  const paymentStatus = String(
    data.payment?.status ??
      data.feePaymentStatus ??
      data.fee_payment_status ??
      data.paymentStatus ??
      data.payment_status ??
      "",
  ).toUpperCase();

  if (["FAILED", "REJECTED", "DECLINED"].includes(paymentStatus))
    return { label: "입금 확인 반려", tone: "rejected", isComplete: false };
  if (
    contractStatus === "ACTIVE" &&
    ["PAID", "VERIFIED", "APPROVED", "CONFIRMED"].includes(paymentStatus)
  )
    return { label: "성사 등록 완료", tone: "complete", isComplete: true };
  if (
    contractStatus === "REGISTERED" ||
    [
      "PAID",
      "AWAITING_PAYMENT",
      "AWAITING_CONFIRMATION",
      "PAYMENT_PENDING",
      "PENDING",
      "SUBMITTED",
    ].includes(paymentStatus)
  )
    return { label: "관리자 확인 중", tone: "pending", isComplete: false };
  return { label: "입금 확인 전", tone: "pending", isComplete: false };
}

/**
 * Returns the newest non-cancelled class resource for [roomId].
 *
 * Chat and class management use this same resource as their source of truth
 * for the completion state and the class-information payload.
 */
export function getLatestClassResource(resources = [], roomId) {
  return [...resources]
    .filter(
      (item) =>
        String(item.chat_room_id ?? item.chatRoomId ?? "") === String(roomId) &&
        !item.is_cancelled &&
        !item.isCancelled,
    )
    .sort(
      (left, right) =>
        new Date(right.created_at ?? right.createdAt ?? 0).valueOf() -
        new Date(left.created_at ?? left.createdAt ?? 0).valueOf(),
    )[0] ?? null;
}

/** Returns the app-equivalent registration step and copy for the active role. */
export function getRegistrationFlow(data = {}, { isTeacher = false } = {}) {
  const status = getRegistrationStatus(data);
  const contractStatus = String(
    data.contractStatus ?? data.contract_status ?? "",
  ).toUpperCase();
  const paymentStatus = String(
    data.payment?.status ??
      data.feePaymentStatus ??
      data.fee_payment_status ??
      data.paymentStatus ??
      data.payment_status ??
      "",
  ).toUpperCase();
  const isMismatched = String(
    data.attributeValidationStatus ?? data.attribute_validation_status ?? "",
  ).toUpperCase() === "MISMATCHED";
  const isRejected = isMismatched || status.tone === "rejected";
  const mineFinalized = Boolean(data.mySubmissionFinalized ?? data.my_submission_finalized);
  const counterpartySubmitted = Boolean(
    data.counterpartySubmission?.submitted ??
      (isTeacher ? data.studentSubmitted ?? data.is_student_confirmed : data.instructorSubmitted ?? data.is_instructor_confirmed),
  );
  const canResumeTeacherProof = Boolean(
    isTeacher && data.mySubmission && !mineFinalized && data.payment && !isRejected,
  );
  const waitingForCounterparty = mineFinalized && !counterpartySubmitted;
  const waitingForPayment = mineFinalized && counterpartySubmitted && !status.isComplete;

  return {
    status,
    isCancelled: contractStatus === "CANCELLED" || paymentStatus === "CANCELLED",
    isRejected,
    isMismatched,
    isPaymentRejected: ["FAILED", "REJECTED", "DECLINED"].includes(paymentStatus),
    mineFinalized,
    counterpartySubmitted,
    canResumeTeacherProof,
    waitingForCounterparty,
    waitingForPayment,
    isLocked: mineFinalized && !isRejected,
    pendingTitle: waitingForCounterparty
      ? "상대방의 성사 등록을 기다리고 있어요."
      : "수수료 입금 확인을 기다리고 있어요.",
    pendingDescription: waitingForCounterparty
      ? isTeacher
        ? "학생의 성사 등록을 기다리고 있어요. 제출하신 정보는 운영팀에서 확인 중이에요.\n\n제출한 수업 정보는 지금 수정할 수 없어요."
        : "선생님의 성사 등록을 기다리고 있어요. 제출하신 정보는 운영팀에서 확인 중이에요.\n\n제출한 수업 정보는 지금 수정할 수 없어요."
      : isTeacher
        ? "제출하신 수업 정보와 수수료 입금 내역을 운영팀에서 확인하고 있어요.\n\n확인되면 성사 등록이 완료돼요."
        : "제출하신 수업 정보와 선생님이 제출한 수수료 입금 내역을 운영팀에서 확인하고 있어요.\n\n확인되면 페이백 지급이 진행돼요.",
  };
}

/**
 * Matches the app's registration-result route selection.
 * A previously rejected registration remains editable when reopened, while a
 * rejection returned by the current submission opens the failure result.
 */
export function getRegistrationResultScreen(
  data = {},
  { isTeacher = false, submitted = false } = {},
) {
  const flow = getRegistrationFlow(data, { isTeacher });
  if (flow.status.isComplete) return "success";
  if (submitted && flow.isRejected) return "failure";
  if ((submitted || flow.mineFinalized) && !flow.isRejected) return "pending";
  return null;
}
