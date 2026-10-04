import React, { useContext, useEffect, useState } from "react";
import { api, list } from "./api";
import { BANKS, Ctx, Modal, Btn, State, Empty, useLoad, money, date } from "./shared";
import { ActionForm } from "./services";

export function registrationStatus(data = {}) {
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

  if (["FAILED", "REJECTED", "DECLINED"].includes(paymentStatus)) {
    return { label: "입금 확인 반려", tone: "rejected", isComplete: false };
  }
  if (contractStatus === "ACTIVE") {
    return { label: "성사 등록 완료", tone: "complete", isComplete: true };
  }
  if (
    contractStatus === "REGISTERED" ||
    [
      "PAID",
      "AWAITING_PAYMENT",
      "AWAITING_CONFIRMATION",
      "PENDING",
      "SUBMITTED",
    ].includes(paymentStatus)
  ) {
    return { label: "관리자 확인 중", tone: "pending", isComplete: false };
  }
  return { label: "입금 확인 전", tone: "pending", isComplete: false };
}

export function Registration({ room, onClose, onUpdated }) {
  const { user, subjects, notify } = useContext(Ctx),
    base = `/tutoring/resources/chatrooms/${room.id}/`;
  const resource = useLoad(base, [], { keepDataOnReload: true }),
    d = resource.data || {},
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const teacher = d.instructor?.id === user.id;
  const currentStatus = registrationStatus(d);
  const submission = d.mySubmission || {};
  const classType =
    submission.classType === "SHORT_TERM" ? "단기 수업" : "정규 수업";
  const startDate = d.startDate
    ? String(d.startDate).replaceAll("-", ".")
    : "날짜 미정";
  const subject = Array.isArray(d.subject)
    ? d.subject.join(", ")
    : d.subject || "과목 미정";
  const shouldPoll =
    (d.studentSubmitted || d.instructorSubmitted) &&
    !currentStatus.isComplete &&
    currentStatus.tone !== "rejected";
  useEffect(() => {
    if (!shouldPoll) return undefined;
    const timer = window.setInterval(() => resource.reload(), 10000);
    return () => window.clearInterval(timer);
  }, [base, shouldPoll]);
  async function submit(e) {
    e.preventDefault();
    if (currentStatus.isComplete) {
      setError("성사 등록이 완료되어 수정할 수 없습니다.");
      return;
    }
    const f = new FormData(e.currentTarget),
      ids = f.getAll("subjectIds").map(Number);
    if (ids.length > 3) {
      setError("과목은 최대 3개입니다.");
      return;
    }
    if (
      !window.confirm("상대방과 협의한 과외 조건으로 성사 등록을 제출할까요?")
    )
      return;
    setBusy(true);
    setError("");
    const body = {
      subject: ids
        .map((id) => subjects.find((s) => s.number === id)?.name)
        .join(", "),
      subjectIds: ids,
      startDate: f.get("startDate"),
      classType: f.get("classType"),
      firstMonthFee: Number(f.get("firstMonthFee")),
    };
    if (!teacher)
      body.paybackAccount = {
        bankCode: f.get("bankCode"),
        accountNumber: f.get("accountNumber"),
        accountHolder: f.get("accountHolder"),
      };
    let payload = body;
    if (teacher) {
      payload = new FormData();
      for (const [key, value] of Object.entries(body)) {
        if (Array.isArray(value)) value.forEach((v) => payload.append(key, v));
        else payload.append(key, value);
      }
      for (const file of f.getAll("feeConfirmationFiles"))
        payload.append("feeConfirmationFiles", file);
    }
    try {
      await api(base + "my-registration/", { method: "PUT", body: payload });
      resource.reload();
      onUpdated?.();
      notify("과외 성사 등록을 제출했습니다.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={currentStatus.isComplete ? "수업 정보" : "과외 성사 등록"}
      onClose={onClose}
      wide
    >
      <State resource={resource}>
        <p className="registration-summary">
          <span className={"registration-status " + currentStatus.tone}>
            {currentStatus.label}
          </span>{" "}
          · 학생{" "}
          {d.studentSubmitted ? "제출 완료" : "미제출"} · 선생님{" "}
          {d.instructorSubmitted ? "제출 완료" : "미제출"}
        </p>
        {shouldPoll && <p className="muted">상태를 자동으로 확인하고 있어요.</p>}
        {currentStatus.isComplete && (
          <p className="muted">성사 등록이 완료되어 수정할 수 없습니다.</p>
        )}
        {d.attributeValidationStatus === "MISMATCHED" && (
          <p className="error">
            서로 제출한 과목·시작일이 다릅니다. 상대방과 확인한 뒤 다시 제출해
            주세요.
          </p>
        )}
        {d.payment && (
          <section className="info-panel">
            <h3>성사 수수료 안내</h3>
            <p>
              {d.payment.bank} {d.payment.accountNumber}
            </p>
            <p>
              {money(d.payment.amount)}원 ·{" "}
              {currentStatus.label}
            </p>
            <small>입금 확인은 운영 검토 후 반영됩니다.</small>
          </section>
        )}
        {currentStatus.isComplete && (
          <section className="info-panel">
            <h3>수업 정보</h3>
            <dl className="class-info-list">
              <div>
                <dt>수업 과목</dt>
                <dd>{subject}</dd>
              </div>
              <div>
                <dt>수업 시작일</dt>
                <dd>{startDate}</dd>
              </div>
              <div>
                <dt>수업 형태</dt>
                <dd>{classType}</dd>
              </div>
              <div>
                <dt>총 수업료</dt>
                <dd>
                  {submission.firstMonthFee == null
                    ? "협의"
                    : `${money(submission.firstMonthFee)}원`}
                </dd>
              </div>
            </dl>
          </section>
        )}
        {!currentStatus.isComplete && (
          <form className="form" onSubmit={submit}>
            <fieldset className="form-fields" disabled={busy}>
            <label>
              과목 (최대 3개)
              <select name="subjectIds" multiple size={5} required>
                {subjects.map((s) => (
                  <option key={s.number} value={s.number}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              수업 시작일
              <input
                key={d.startDate}
                name="startDate"
                type="date"
                defaultValue={d.startDate || ""}
                required
              />
            </label>
            <label>
              수업 유형
              <select
                name="classType"
                defaultValue={d.mySubmission?.classType || "REGULAR"}
              >
                <option value="REGULAR">정규 수업</option>
                <option value="SHORT_TERM">단기 수업</option>
              </select>
            </label>
            <label>
              첫 달 수업료 (원)
              <input
                name="firstMonthFee"
                type="number"
                min="1"
                required
                defaultValue={d.mySubmission?.firstMonthFee}
              />
            </label>
            {teacher ? (
              <label>
                입금 증빙
                <input
                  name="feeConfirmationFiles"
                  type="file"
                  multiple
                  required
                  accept="image/*,application/pdf"
                />
              </label>
            ) : (
              <>
                <label>
                  페이백 은행
                  <select name="bankCode" required defaultValue="">
                    <option value="" disabled>
                      은행을 선택해주세요
                    </option>
                    {BANKS.map((bank) => (
                      <option key={bank} value={bank}>
                        {bank}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  페이백 계좌번호
                  <input
                    name="accountNumber"
                    required
                    inputMode="numeric"
                    pattern="[0-9 -]+"
                  />
                </label>
                <label>
                  예금주
                  <input name="accountHolder" required />
                </label>
              </>
            )}
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
              <Btn className="primary" disabled={busy}>
                성사 등록 제출
              </Btn>
            </fieldset>
          </form>
        )}
      </State>
    </Modal>
  );
}

export function ClassHistory() {
  const { user, notify } = useContext(Ctx),
    [page, setPage] = useState(1),
    [tab, setTab] = useState("all"),
    [edit, setEdit] = useState(null);
  const r = useLoad(`/tutoring/resources/?role=${user.role}&page=${page}`),
    teacher = user.role === "instructor";
  const base =
    "/tutoring/reviews/" + (teacher ? "student" : "instructor") + "/";
  const resources = list(r.data);
  const visibleResources =
    tab === "progress"
      ? resources.filter((resource) => {
          const status = registrationStatus(resource);
          return !status.isComplete && status.tone !== "rejected";
        })
      : resources;
  return (
    <section className="service-section">
      <h2>나의 과외</h2>
      <div className="registration-controls">
        <div className="registration-tabs" role="tablist" aria-label="과외 상태">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "all"}
            className={tab === "all" ? "active" : ""}
            onClick={() => setTab("all")}
          >
            전체
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "progress"}
            className={tab === "progress" ? "active" : ""}
            onClick={() => setTab("progress")}
          >
            성사 등록 진행 중
          </button>
        </div>
        <Btn type="button" onClick={r.reload}>
          새로고침
        </Btn>
      </div>
      <State resource={r}>
        {visibleResources.map((x) => {
          const status = registrationStatus(x);
          return (
            <article key={x.id} className="history-row">
              <div>
                <b>
                  {x.counterpart?.nickname ||
                    x.student_user_name ||
                    x.instructor_user_name ||
                    "과외 수업"}
                </b>
                <p>
                  {date(x.start_date)} · {x.class_type || "협의 중"}
                </p>
                <span className={"registration-status " + status.tone}>
                  {status.label}
                </span>
                <p className="muted">{x.my_review?.comment}</p>
              </div>
              {status.isComplete && (
                <Btn onClick={() => setEdit(x)}>
                  {x.my_review ? "후기 수정" : "후기 작성"}
                </Btn>
              )}
            </article>
          );
        })}
        {!visibleResources.length && (
          <p className="muted">
            {tab === "progress"
              ? "진행 중인 성사 등록이 없습니다."
              : "성사 등록은 상담 채팅방에서 시작할 수 있습니다."}
          </p>
        )}
        <div className="actions">
          {page > 1 && <Btn onClick={() => setPage((p) => p - 1)}>이전</Btn>}
          {r.data?.next && (
            <Btn onClick={() => setPage((p) => p + 1)}>다음</Btn>
          )}
        </div>
      </State>
      {edit && (
        <Modal title="수업 후기" onClose={() => setEdit(null)}>
          <ActionForm
            path={base + (edit.my_review ? edit.my_review.id + "/" : "")}
            method={edit.my_review ? "PATCH" : "POST"}
            submit="후기 저장"
            transform={(f) => {
              const d = Object.fromEntries(f);
              for (const key of teacher
                ? ["rating"]
                : ["professionalism", "teaching_skill", "punctuality"])
                d[key] = Number(d[key]);
              return {
                ...d,
                resource: edit.id,
                [teacher ? "student" : "instructor"]:
                  edit[teacher ? "student" : "instructor"],
              };
            }}
            onDone={() => {
              setEdit(null);
              r.reload();
            }}
          >
            {(teacher
              ? [["rating", "만족도"]]
              : [
                  ["professionalism", "전문성"],
                  ["teaching_skill", "설명력"],
                  ["punctuality", "시간 준수"],
                ]
            ).map(([name, label]) => (
              <label key={name}>
                {label}
                <select name={name} defaultValue={edit.my_review?.[name] || 5}>
                  {[5, 4, 3, 2, 1].map((n) => (
                    <option key={n} value={n}>
                      {n}점
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <label>
              후기
              <textarea
                name="comment"
                required
                maxLength={500}
                defaultValue={edit.my_review?.comment}
              />
            </label>
          </ActionForm>
          {edit.my_review && (
            <Btn
              onClick={async () => {
                if (!window.confirm("후기를 삭제할까요?")) return;
                try {
                  await api(base + edit.my_review.id + "/", {
                    method: "DELETE",
                  });
                  setEdit(null);
                  r.reload();
                } catch (e) {
                  notify(e.message);
                }
              }}
            >
              후기 삭제
            </Btn>
          )}
        </Modal>
      )}
    </section>
  );
}
