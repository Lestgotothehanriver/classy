import React, { useContext, useState } from "react";
import { api, list } from "./api";
import { Ctx, Modal, Btn, State, Empty, useLoad, money, date } from "./shared";
import { ActionForm } from "./services";

export function Registration({ room, onClose }) {
  const { user, subjects, notify } = useContext(Ctx),
    base = `/tutoring/resources/chatrooms/${room.id}/`;
  const resource = useLoad(base),
    d = resource.data || {},
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const teacher = d.instructor?.id === user.id;
  async function submit(e) {
    e.preventDefault();
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
      notify("과외 성사 등록을 제출했습니다.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const status = {
    COLLECTING: "양측 정보 수집 중",
    ACTIVE: "진행 중",
    AWAITING_PAYMENT: "수수료 입금 대기",
    PENDING: "확인 대기",
    PAID: "입금 확인 완료",
    MISMATCHED: "조건 불일치",
  };
  return (
    <Modal title="과외 성사 등록" onClose={onClose} wide>
      <State resource={resource}>
        <p>
          {status[d.contractStatus] || "등록 확인 중"} · 학생{" "}
          {d.studentSubmitted ? "제출 완료" : "미제출"} · 선생님{" "}
          {d.instructorSubmitted ? "제출 완료" : "미제출"}
        </p>
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
              {status[d.payment.status] || "처리 중"}
            </p>
            <small>입금 확인은 운영 검토 후 반영됩니다.</small>
          </section>
        )}
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
                  <select name="bankCode" required>
                    {[
                      "국민은행",
                      "신한은행",
                      "우리은행",
                      "하나은행",
                      "농협은행",
                      "기업은행",
                      "카카오뱅크",
                      "토스뱅크",
                      "케이뱅크",
                      "새마을금고",
                      "우체국",
                    ].map((x) => (
                      <option key={x}>{x}</option>
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
      </State>
    </Modal>
  );
}
export function ClassHistory() {
  const { user, notify } = useContext(Ctx),
    [page, setPage] = useState(1),
    [edit, setEdit] = useState(null);
  const r = useLoad(`/tutoring/resources/?role=${user.role}&page=${page}`),
    teacher = user.role === "instructor";
  const base =
    "/tutoring/reviews/" + (teacher ? "student" : "instructor") + "/";
  return (
    <section className="service-section">
      <h2>성사된 과외 · 수업 후기</h2>
      <State resource={r}>
        {list(r.data).map((x) => (
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
              <p className="muted">{x.my_review?.comment}</p>
            </div>
            {x.fee_payment_status === "PAID" && (
              <Btn onClick={() => setEdit(x)}>
                {x.my_review ? "후기 수정" : "후기 작성"}
              </Btn>
            )}
          </article>
        ))}
        {!list(r.data).length && (
          <p className="muted">
            성사 등록은 상담 채팅방에서 시작할 수 있습니다.
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
