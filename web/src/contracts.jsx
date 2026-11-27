import React, { useContext, useEffect, useState } from "react";
import {
  BadgeCheck,
  Banknote,
  BookOpen,
  CalendarDays,
  Clock3,
  Search,
} from "lucide-react";
import { api, list } from "./api";
import { BANKS, Ctx, CustomModal, Btn, State, Empty, FieldLabel, useLoad, money, date } from "./shared";
import { ActionForm } from "./services";
import { SubjectPicker } from "./studio";
import { getRegistrationFlow, getRegistrationStatus } from "./tutoring-state";

function formatTuitionInput(value) {
  const digits = String(value).replace(/\D/g, "");
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

export function registrationStatus(data = {}) {
  return getRegistrationStatus(data);
}

export function Registration({ room, onClose, onUpdated }) {
  const { user, subjects, notify } = useContext(Ctx),
    base = `/tutoring/resources/chatrooms/${room.id}/`;
  const resource = useLoad(base, [], { keepDataOnReload: true }),
    d = resource.data || {},
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [classType, setClassType] = useState("REGULAR"),
    [tuition, setTuition] = useState(""),
    [selectedSubjectIds, setSelectedSubjectIds] = useState([]),
    [isSubjectPickerOpen, setIsSubjectPickerOpen] = useState(false);
  const teacher = d.instructor?.id === user.id;
  const currentStatus = registrationStatus(d);
  const counterpartName =
    room.opponent_info?.nickname ||
    room.opponent_info?.user_name ||
    (teacher ? d.student?.userName : d.instructor?.userName) ||
    "상대방";
  const shouldPoll =
    (d.studentSubmitted || d.instructorSubmitted) &&
    !currentStatus.isComplete &&
    currentStatus.tone !== "rejected";
  useEffect(() => {
    if (!shouldPoll) return undefined;
    const timer = window.setInterval(() => resource.reload(), 10000);
    return () => window.clearInterval(timer);
  }, [base, shouldPoll]);
  useEffect(() => {
    if (d.mySubmission?.classType) setClassType(d.mySubmission.classType);
  }, [d.mySubmission?.classType]);
  useEffect(() => {
    if (d.mySubmission?.firstMonthFee != null)
      setTuition(formatTuitionInput(d.mySubmission.firstMonthFee));
  }, [d.mySubmission?.firstMonthFee]);
  const tuitionLabel =
    classType === "SHORT_TERM" ? "총 수업료" : "첫 달 수업료";
  async function submit(e) {
    e.preventDefault();
    if (currentStatus.isComplete) {
      setError("성사 등록이 완료되어 수정할 수 없습니다.");
      return;
    }
    const f = new FormData(e.currentTarget),
      ids = selectedSubjectIds;
    if (!ids.length) {
      setError("과목을 하나 이상 선택해 주세요.");
      return;
    }
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
      firstMonthFee: Number(String(f.get("firstMonthFee") || "").replaceAll(",", "")),
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
  if (currentStatus.isComplete) {
    return (
      <ClassInformationModal
        resource={d}
        counterpartName={counterpartName}
        onClose={onClose}
      />
    );
  }
  return (
    <>
    <CustomModal
      title="과외 성사 등록"
      onClose={onClose}
    >
      <State resource={resource}>
        {!currentStatus.isComplete && <p className="registration-summary">
          <span className={"registration-status " + currentStatus.tone}>
            {currentStatus.label}
          </span>{" "}
          · 학생{" "}
          {d.studentSubmitted ? "제출 완료" : "미제출"} · 선생님{" "}
          {d.instructorSubmitted ? "제출 완료" : "미제출"}
        </p>}
        {!currentStatus.isComplete && shouldPoll && <p className="muted">상태를 자동으로 확인하고 있어요.</p>}
        {!currentStatus.isComplete && d.attributeValidationStatus === "MISMATCHED" && (
          <p className="error">
            서로 제출한 과목·시작일이 다릅니다. 상대방과 확인한 뒤 다시 제출해
            주세요.
          </p>
        )}
        {!currentStatus.isComplete && d.payment && (
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
        {!currentStatus.isComplete && (
          <form className="form" onSubmit={submit}>
            <fieldset className="form-fields" disabled={busy}>
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
                value={classType}
                onChange={(event) => setClassType(event.target.value)}
              >
                <option value="REGULAR">정규 수업</option>
                <option value="SHORT_TERM">단기 수업</option>
              </select>
            </label>
            <div className="chip-form-field">
            <div className="subject-field">
              <span>과목 (최대 3개)</span>
              <button
                type="button"
                className="subject-picker-trigger"
                aria-label="과목 선택"
                onClick={() => setIsSubjectPickerOpen(true)}
              >
                <span>
                  {selectedSubjectIds.length
                    ? `${selectedSubjectIds.length}개 과목 선택됨`
                    : "관련된 과목을 선택해주세요."}
                </span>
                <Search size={24} aria-hidden="true" />
              </button>
            </div>
            {selectedSubjectIds.length > 0 && (
              <div className="subject-chips" aria-label="선택된 과목">
                {selectedSubjectIds.map((subjectId) => {
                  const subject = subjects.find((item) => item.number === subjectId);
                  if (!subject) return null;
                  return (
                    <button
                      type="button"
                      key={subject.number}
                      onClick={() =>
                        setSelectedSubjectIds((ids) =>
                          ids.filter((id) => id !== subject.number),
                        )
                      }
                      aria-label={`${subject.name} 선택 취소`}
                    >
                      {subject.name} <span aria-hidden="true">×</span>
                    </button>
                  );
                })}
              </div>
            )}
            </div>
            <label>
              {tuitionLabel}
              <span className="tuition-input">
                <input
                  name="firstMonthFee"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9,]+"
                  required
                  value={tuition}
                  onChange={(event) => setTuition(formatTuitionInput(event.target.value))}
                />
                <span className="tuition-input-suffix" aria-hidden="true">(원)</span>
              </span>
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
                  예금주명
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
    </CustomModal>
    {isSubjectPickerOpen && (
      <SubjectPicker
        subjects={subjects}
        selectedIds={selectedSubjectIds}
        onChange={setSelectedSubjectIds}
        onClose={() => setIsSubjectPickerOpen(false)}
      />
    )}
    </>
  );
}

/** 앱의 수업 정보 카드와 같은 항목을 웹 모달에서 표시한다. */
export function ClassInformationCard({ resource, counterpartName }) {
  const classType =
    resource.class_type === "단기 수업" ||
    resource.class_type === "SHORT_TERM" ||
    resource.classType === "SHORT_TERM" ||
    resource.mySubmission?.classType === "SHORT_TERM"
      ? "단기 수업"
      : "정규 수업";
  const counterpart =
    counterpartName ||
    resource.counterpart?.nickname ||
    resource.counterpart?.userName ||
    resource.counterpart?.user_name ||
    resource.instructor?.userName ||
    resource.student?.userName ||
    resource.instructor_user_name ||
    resource.student_user_name ||
    "상대방";
  const subject = (Array.isArray(resource.subject)
    ? resource.subject
    : [resource.subject]
  )
    .map((item) => (typeof item === "object" ? item?.label || item?.name : item))
    .filter(Boolean)
    .join(", ") || "과목 미정";
  const startDate = resource.start_date || resource.startDate
    ? String(resource.start_date || resource.startDate).replaceAll("-", ".")
    : "날짜 미정";
  const feeLabel = classType === "단기 수업" ? "총 수업료" : "첫 달 수업료";
  const fee =
    resource.first_month_fee ??
    resource.firstMonthFee ??
    resource.mySubmission?.firstMonthFee;
  const registration = registrationStatus(resource);

  return (
    <section className="class-information-card">
      <h3>
        <span className="class-information-nickname">{counterpart}</span>{" "}
        님과의 수업
      </h3>
      <dl className="class-info-list">
        <ClassInformationRow icon={BookOpen} label="수업 과목" value={subject} />
        <ClassInformationRow
          icon={CalendarDays}
          label="첫 수업 시작일"
          value={startDate}
        />
        <ClassInformationRow icon={Clock3} label="수업 유형" value={classType} />
        <ClassInformationRow
          icon={Banknote}
          label={feeLabel}
          value={fee == null ? "협의" : `${money(fee)}원`}
        />
        <ClassInformationRow
          icon={BadgeCheck}
          label="성사 등록 여부"
          value={registration.label}
        />
      </dl>
    </section>
  );
}

/** 수업 정보 카드의 아이콘·레이블·값 행입니다. */
function ClassInformationRow({ icon: Icon, label, value }) {
  return (
    <div>
      <dt>
        <Icon
          className="class-information-icon"
          size={18}
          aria-hidden="true"
        />
        {label}
      </dt>
      <dd>{value}</dd>
    </div>
  );
}

/** 리뷰 대상 역할에 맞는 안내 문구와 함께 본문 글자 수를 표시합니다. */
function ReviewCommentField({ defaultValue = "", isTeacher }) {
  const [value, setValue] = useState(defaultValue);
  const characterCount = Array.from(value).length;

  return (
    <label className="review-comment-field">
      <span className="review-comment-label">
        <FieldLabel required>상세 리뷰</FieldLabel>
        <small>({characterCount}/500)</small>
      </span>
      <textarea
        name="comment"
        required
        maxLength={500}
        rows={2}
        value={value}
        placeholder={
          isTeacher
            ? "이 학생과의 수업에 대해 이야기해 주세요."
            : "이 선생님과의 수업에 대해 이야기해 주세요."
        }
        onChange={(event) => setValue(event.target.value)}
      />
    </label>
  );
}

/** 앱의 수업 정보 카드와 같은 항목을 웹 모달에서 표시한다. */
export function ClassInformationModal({ resource, counterpartName, onClose }) {
  return (
    <CustomModal title="수업 정보" onClose={onClose}>
      <ClassInformationCard
        resource={resource}
        counterpartName={counterpartName}
      />
    </CustomModal>
  );
}

export function ClassHistory() {
  const { user, go } = useContext(Ctx),
    [page, setPage] = useState(1),
    [tab, setTab] = useState("all"),
    [edit, setEdit] = useState(null),
    [classInformation, setClassInformation] = useState(null);
  const r = useLoad(`/tutoring/resources/?role=${user.role}&page=${page}`),
    teacher = user.role === "instructor";
  const base =
    "/tutoring/reviews/" + (teacher ? "student" : "instructor") + "/";
  const resources = list(r.data).filter(
    (resource) => !getRegistrationFlow(resource, { isTeacher: teacher }).isCancelled,
  );
  const visibleResources =
    tab === "progress"
      ? resources.filter((resource) => {
          const status = registrationStatus(resource);
          return !status.isComplete;
        })
      : resources;
  const classStatus = (resource) => {
    const completed = registrationStatus(resource).isComplete;
    return {
      completed,
      label: completed
        ? resource.class_type === "단기 수업" || resource.class_type === "SHORT_TERM"
          ? "단기 수업"
          : "정규 수업"
        : "성사 등록 진행 중",
    };
  };
  const subjectLabel = (resource) =>
    (Array.isArray(resource.subject) ? resource.subject : [])
      .map((subject) =>
        typeof subject === "object" ? subject.label || subject.name : subject,
      )
      .filter(Boolean)
      .join(", ") || "과목 미정";
  const createdDate = (value) => {
    const createdAt = new Date(value);
    if (Number.isNaN(createdAt.valueOf())) return "";
    return [
      createdAt.getFullYear(),
      String(createdAt.getMonth() + 1).padStart(2, "0"),
      String(createdAt.getDate()).padStart(2, "0"),
    ].join(".");
  };
  const processingMessage = (resource) => {
    const flow = getRegistrationFlow(resource, { isTeacher: teacher });
    if (flow.isRejected) {
      return resource.rejection_reason || "입력한 수업 정보가 일치하지 않아 자동 반려되었어요. 다시 등록해 주세요.";
    }
    if (!flow.mineFinalized) return "성사 등록을 완료해 주세요.";
    if (flow.waitingForCounterparty)
      return teacher ? "학생의 성사 등록을 기다리고 있어요." : "선생님의 성사 등록을 기다리고 있어요.";
    return "수수료 입금 확인을 기다리고 있어요.";
  };
  return (
    <section className="service-section class-history">
      <div className="registration-controls">
        <label className="tutoring-status-filter">
          <span>수업/과외 상태</span>
          <select value={tab} onChange={(event) => setTab(event.target.value)}>
            <option value="all">전체</option>
            <option value="progress">성사 등록 진행 중</option>
          </select>
        </label>
      </div>
      <State resource={r}>
        {visibleResources.map((x) => {
          const status = registrationStatus(x);
          const studentStatus = classStatus(x);
          const counterpart = teacher
            ? x.counterpart?.nickname || x.student_user_name || "상대방"
            : x.counterpart?.nickname || x.instructor_user_name || "상대방";
          const counterpartRole = teacher ? "학생" : "선생님";
          return (
            <article key={x.id} className="student-class-card">
              <div className="student-class-card-head">
                <b>{counterpart} {counterpartRole}과의 수업</b>
                <span className={studentStatus.completed ? "complete" : "progress"}>
                  {studentStatus.label}
                </span>
              </div>
              <p className="student-class-subject">
                <BookOpen size={16} aria-hidden="true" />
                {subjectLabel(x)}
              </p>
              {createdDate(x.created_at) && <small>{createdDate(x.created_at)}</small>}
              {!studentStatus.completed && <p className="student-class-progress">{processingMessage(x)}</p>}
              <div className="student-class-actions">
                {studentStatus.completed ? (
                  <>
                    <Btn
                      className="primary"
                      onClick={() => setClassInformation(x)}
                    >
                      수업 정보
                    </Btn>
                    <Btn onClick={() => setEdit(x)}>
                      {x.my_review ? "리뷰 수정" : "리뷰 작성"}
                    </Btn>
                  </>
                ) : (
                  <Btn
                    className="primary full"
                    disabled={!x.chat_room_public_id}
                    onClick={() => go(`tutoring-registration/${x.chat_room_public_id}`)}
                  >
                    {status.tone === "rejected" ? "성사 등록 다시 하기" : "성사 등록"}
                  </Btn>
                )}
              </div>
            </article>
          );
        })}
        {!visibleResources.length && (
          <p className="student-class-empty">
            {tab === "progress"
              ? "진행 중인 성사 등록이 없어요."
              : "수업/과외 내역이 없어요."}
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
        <CustomModal
          title={edit.my_review ? "리뷰 수정" : "리뷰 작성"}
          onClose={() => setEdit(null)}
        >
          <ActionForm
            path={base + (edit.my_review ? edit.my_review.id + "/" : "")}
            method={edit.my_review ? "PATCH" : "POST"}
            submit={edit.my_review ? "리뷰 수정" : "리뷰 작성"}
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
              ? [["rating", "수업 후기를 남겨주세요 (1~5점)"]]
              : [
                  ["professionalism", "전문적이에요"],
                  ["teaching_skill", "강의력이 좋아요"],
                  ["punctuality", "시간을 잘 지켜요"],
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
            <ReviewCommentField
              key={edit.my_review?.id || "new"}
              defaultValue={edit.my_review?.comment}
              isTeacher={teacher}
            />
            <p className="review-guidance">
              {teacher
                ? "이 학생의 수업에 대한 리뷰를 남겨주세요.\n리뷰는 수업이 성사 된 후 언제든지 작성 가능하며, 작성하신 리뷰는\n90일 이내에 수정할 수 있습니다.\n\n타인의 권리를 침해하거나 부적절한 내용이 포함된 경우,\n운영 정책에 따라 삭제 및 제재가 가해질 수 있습니다."
                : "이 선생님과의 수업에 대한 리뷰를 남겨주세요.\n리뷰는 수업이 성사 된 후 언제든지 작성 가능하며, 작성하신 리뷰는\n90일 이내에 수정할 수 있습니다.\n\n타인의 권리를 침해하거나 부적절한 내용이 포함된 경우,\n운영 정책에 따라 삭제 및 제재가 가해질 수 있습니다."}
            </p>
          </ActionForm>
        </CustomModal>
      )}
      {classInformation && (
        <ClassInformationModal
          resource={classInformation}
          onClose={() => setClassInformation(null)}
        />
      )}
    </section>
  );
}
