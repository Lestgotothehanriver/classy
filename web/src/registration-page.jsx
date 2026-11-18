import React, { useContext, useEffect, useRef, useState } from "react";
import { ChevronLeft, CircleAlert, Download, Hourglass, Plus, Search } from "lucide-react";
import { api } from "./api";
import {
  BANKS,
  Btn,
  Ctx,
  FieldLabel,
  FilePicker,
  MobileBackAction,
  money,
  State,
  useLoad,
} from "./shared";
import { ClassInformationCard } from "./contracts";
import { SubjectPicker } from "./studio";
import { getRegistrationFlow, getRegistrationResultScreen } from "./tutoring-state";

/** 숫자로만 된 수업료를 천 단위 표기 문자열로 바꾼다. */
function formatTuition(value) {
  return String(value ?? "")
    .replace(/\D/g, "")
    .replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** 수수료 basis point 값을 화면용 백분율로 바꾼다. */
function formatCommissionRate(rateBps) {
  const rate = Number(rateBps) / 100;
  if (!Number.isFinite(rate)) return "";
  return Number.isInteger(rate) ? String(rate) : String(rate).replace(/0+$/, "");
}

/** 성사 등록의 공통 기본 정보를 전송 형식으로 만든다. */
function registrationPayload({ subjectIds, subjects, startDate, classType, tuition }) {
  return {
    subject: subjectIds
      .map((id) => subjects.find((item) => item.number === id)?.name)
      .filter(Boolean)
      .join(", "),
    subjectIds,
    startDate,
    classType,
    firstMonthFee: Number(tuition.replaceAll(",", "")),
  };
}

/** FormData에 성사 등록 기본 정보를 넣는다. */
function appendRegistrationPayload(formData, payload) {
  Object.entries(payload).forEach(([key, value]) => {
    if (Array.isArray(value)) value.forEach((item) => formData.append(key, item));
    else formData.append(key, value);
  });
}

/** 앱과 같은 성사 등록 전용 페이지다. */
export function RegistrationPage({ roomId }) {
  const { go, notify, subjects, user } = useContext(Ctx);
  const path = `/tutoring/resources/chatrooms/${roomId}/`;
  const resource = useLoad(path, [roomId], { keepDataOnReload: true });
  const data = resource.data || {};
  const isTeacher = user?.role === "instructor";
  const registrationFlow = getRegistrationFlow(data, { isTeacher });
  const [subjectIds, setSubjectIds] = useState([]);
  const [subjectPickerOpen, setSubjectPickerOpen] = useState(false);
  const [startDate, setStartDate] = useState("");
  const [classType, setClassType] = useState("SHORT_TERM");
  const [tuition, setTuition] = useState("");
  const [bankCode, setBankCode] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [accountHolder, setAccountHolder] = useState("");
  const [step, setStep] = useState("basic");
  const [proofFiles, setProofFiles] = useState([]);
  const [payment, setPayment] = useState(null);
  const [submitted, setSubmitted] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loadingPreviousAccount, setLoadingPreviousAccount] = useState(false);
  const [error, setError] = useState("");
  const resolvedSavedProof = useRef(false);

  function proofPath() {
    return `#tutoring-registration/${roomId}/proof`;
  }

  function enterProofStep() {
    if (location.hash !== proofPath())
      history.pushState(null, "", proofPath());
    setStep("proof");
  }

  function returnToBasicStep() {
    if (location.hash === proofPath()) history.back();
    else setStep("basic");
  }

  async function loadPreviousPaybackAccount() {
    setLoadingPreviousAccount(true);
    try {
      const result = await api("/tutoring/payback-accounts/recent/");
      const account = result.paybackAccount;
      if (!account) {
        notify("불러올 이전 계좌 정보가 없습니다.");
        return;
      }
      setBankCode(account.bankCode || "");
      setAccountNumber(account.accountNumber || "");
      setAccountHolder(account.accountHolder || "");
      notify("이전 계좌 정보를 불러왔습니다.");
    } catch (loadError) {
      notify(loadError.message || "이전 계좌 정보를 불러오지 못했습니다.");
    } finally {
      setLoadingPreviousAccount(false);
    }
  }

  useEffect(() => {
    const names = String(data.subject || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    if (names.length) {
      setSubjectIds(
        subjects
          .filter((subject) => names.includes(subject.name))
          .map((subject) => subject.number),
      );
    }

    const submission = data.mySubmission;
    if (!submission) return;
    setStartDate(data.startDate || "");
    setClassType(submission.classType || "SHORT_TERM");
    setTuition(formatTuition(submission.firstMonthFee));
    if (data.myPaybackAccount) {
      setBankCode(data.myPaybackAccount.bankCode || "");
      setAccountNumber(data.myPaybackAccount.accountNumber || "");
      setAccountHolder(data.myPaybackAccount.accountHolder || "");
    }
  }, [data.mySubmission, data.startDate, data.subject, data.myPaybackAccount, subjects]);

  useEffect(() => {
    if (!registrationFlow.canResumeTeacherProof || resolvedSavedProof.current) return;
    resolvedSavedProof.current = true;
    setPayment(data.payment);
    enterProofStep();
  }, [data.payment, registrationFlow.canResumeTeacherProof]);

  useEffect(() => {
    const syncStepFromRoute = () => {
      const [, routeRoomId, routeStep] = location.hash.slice(1).split("/");
      if (String(routeRoomId) === String(roomId))
        setStep(routeStep === "proof" ? "proof" : "basic");
    };
    window.addEventListener("hashchange", syncStepFromRoute);
    return () => window.removeEventListener("hashchange", syncStepFromRoute);
  }, [roomId]);

  const submittedRegistration = submitted?.registration;
  const hasLatestServerSnapshot = Boolean(
    data.registrationId &&
      (!submittedRegistration ||
        Number(data.registrationId) === Number(submittedRegistration.registrationId)),
  );
  const viewData = submittedRegistration && !hasLatestServerSnapshot
    ? { ...data, ...submittedRegistration, payment: submitted.payment }
    : {
        ...submittedRegistration,
        ...data,
        payment: data.payment || submitted?.payment || null,
      };
  const counterpart = isTeacher ? viewData.student : viewData.instructor;
  const counterpartName =
    counterpart?.userName ||
    counterpart?.user_name ||
    counterpart?.nickname ||
    "상대방";
  const flow = getRegistrationFlow(viewData, { isTeacher });
  const hasFinalized = Boolean(submitted || flow.mineFinalized);
  const isComplete = flow.status.isComplete;
  const isRejected = flow.isRejected;
  const resultScreen = getRegistrationResultScreen(viewData, {
    isTeacher,
    submitted: Boolean(submitted),
  });
  const isCounterpartyFirst = flow.counterpartySubmitted && !flow.mineFinalized && !isRejected;
  const tuitionLabel = classType === "SHORT_TERM" ? "총 수업료" : "첫 달 수업료";

  useEffect(() => {
    if (!hasFinalized || flow.status.isComplete || flow.isRejected) return undefined;
    const timer = window.setInterval(() => resource.reload(), 3000);
    return () => window.clearInterval(timer);
  }, [flow.isRejected, flow.status.isComplete, hasFinalized, resource]);

  function validateBasic() {
    if (!startDate) return "수업 시작일을 선택해 주세요.";
    if (!subjectIds.length) return "과목을 하나 이상 선택해 주세요.";
    if (!tuition || Number(tuition.replaceAll(",", "")) <= 0)
      return "수업료를 입력해 주세요.";
    if (!isTeacher && (!bankCode || !accountNumber || !accountHolder))
      return "페이백 계좌 정보를 모두 입력해 주세요.";
    return "";
  }

  async function submitBasic(event) {
    event.preventDefault();
    const validationError = validateBasic();
    if (validationError) return setError(validationError);
    setBusy(true);
    setError("");
    const payload = registrationPayload({ subjectIds, subjects, startDate, classType, tuition });
    try {
      if (!isTeacher) {
        const result = await api(path + "my-registration/", {
          method: "PUT",
          body: {
            ...payload,
            paybackAccount: { bankCode, accountNumber, accountHolder },
          },
        });
        setSubmitted(result);
        resource.reload();
        return;
      }
      const formData = new FormData();
      appendRegistrationPayload(formData, payload);
      formData.append("preparePayment", "true");
      const result = await api(path + "my-registration/", { method: "PUT", body: formData });
      setPayment(result.payment || null);
      enterProofStep();
      resource.reload();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitProof(event) {
    event.preventDefault();
    if (!proofFiles.length) return setError("입금 증빙 파일을 한 개 이상 첨부해 주세요.");
    setBusy(true);
    setError("");
    const payload = registrationPayload({ subjectIds, subjects, startDate, classType, tuition });
    const formData = new FormData();
    appendRegistrationPayload(formData, payload);
    proofFiles.forEach((file) => formData.append("feeConfirmationFiles", file));
    try {
      const result = await api(path + "my-registration/", { method: "PUT", body: formData });
      setSubmitted(result);
      resource.reload();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  function addProofFiles(event) {
    const selectedFiles = Array.from(event.target.files || []);
    const imageFiles = selectedFiles.filter((file) =>
      ["image/jpeg", "image/png"].includes(file.type),
    );
    const remaining = Math.max(0, 3 - proofFiles.length);
    const acceptedFiles = imageFiles.slice(0, remaining);
    setProofFiles((current) => [...current, ...acceptedFiles]);
    event.target.value = "";

    if (imageFiles.length !== selectedFiles.length)
      setError("JPG 또는 PNG 파일만 첨부할 수 있어요.");
    else if (imageFiles.length > remaining)
      setError("증명 자료는 최대 3개까지 첨부할 수 있어요.");
    else setError("");
  }

  async function copyPaymentAccount() {
    const value = payment?.accountNumber;
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      notify("계좌번호를 복사했어요.");
    } catch (_) {
      notify("계좌번호를 복사하지 못했어요.");
    }
  }

  const header = (
    <header className="registration-page-head">
      {!resultScreen && isTeacher && step === "proof" ? (
        <Btn
          type="button"
          className="registration-step-back"
          onClick={returnToBasicStep}
        >
          <ChevronLeft size={16} aria-hidden="true" />
          이전
        </Btn>
      ) : !resultScreen ? (
        <MobileBackAction type="button" onClick={() => go(`chat/${roomId}`)}>
          채팅으로
        </MobileBackAction>
      ) : null}
      <h1>
        {resultScreen === "success"
          ? "성사 완료"
          : resultScreen === "failure"
            ? "성사 등록 실패"
            : resultScreen === "pending"
              ? "성사 등록 대기"
              : "성사 등록"}
      </h1>
    </header>
  );

  if (resultScreen === "failure") {
    const title = flow.isMismatched
      ? "수업 정보가 일치하지 않아요."
      : "수수료 입금 확인이 반려되었어요.";
    const description = flow.isMismatched
      ? "상대방과 입력한 수업 정보 (수업 유형 또는 수업료)가 달라 자동 반려되었어요.\n\n다시 등록을 시작하면 기존 입금 증빙은 삭제되며, 학생과 선생님 모두 다시 최종 제출해야 해요."
      : "제출한 입금 증빙을 다시 확인해 주세요.\n\n재등록을 시작하면 학생과 선생님이 모두 다시 최종 제출해야 하며, 선생님은 새 입금 증빙을 첨부해야 해요.";
    return (
      <main className="form-page registration-page">
        <div className="form-page-content registration-page-content">
          <div className="form-page-body registration-page-body">
            {header}
            <section className="registration-result registration-failure-result">
              <h2>{title}</h2>
              <CircleAlert className="registration-failure-icon" aria-hidden="true" />
              <p>{description}</p>
              <Btn className="primary full" onClick={() => go("tutoring-manage")}>
                {isTeacher ? "과외 내역에서 다시 등록하기" : "수업 관리에서 다시 등록하기"}
              </Btn>
            </section>
          </div>
        </div>
      </main>
    );
  }

  if (resultScreen) {
    return (
      <main className="form-page registration-page">
        <div className="form-page-content registration-page-content">
          <div className="form-page-body registration-page-body">
            {header}
            <State resource={resource}>
              {resultScreen === "success" ? (
                <section className="registration-result registration-success-result">
                  <h2>수업 성사를 축하드려요!</h2>
                  <ClassInformationCard
                    resource={viewData}
                    counterpartName={counterpartName}
                  />
                  <Btn className="primary full" onClick={() => go("tutoring-manage")}>확인</Btn>
                </section>
              ) : (
                <section className="registration-result">
                  <h2>{flow.pendingTitle}</h2>
                  <Hourglass className="registration-pending-icon" aria-hidden="true" />
                  <p className="registration-pending-description">{flow.pendingDescription}</p>
                  <Btn className="primary full" onClick={() => go("tutoring-manage")}>확인</Btn>
                </section>
              )}
            </State>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="form-page registration-page">
      <div className="form-page-content registration-page-content">
        <div className="form-page-body registration-page-body">
          {header}
          <State resource={resource}>
            {isRejected && (
              <section className="registration-rejected">
                <b>
                  {flow.isMismatched
                    ? "수업 정보가 일치하지 않아요."
                    : "수수료 입금 확인이 반려되었어요."}
                </b>
                <p>
                  {flow.isMismatched
                    ? "상대방과 입력한 수업 정보 (수업 유형 또는 수업료)가 달라 자동 반려되었어요. 다시 등록을 시작하면 기존 입금 증빙은 삭제되며, 학생과 선생님 모두 다시 최종 제출해야 해요."
                    : "제출한 입금 증빙을 다시 확인해 주세요. 재등록을 시작하면 학생과 선생님이 모두 다시 최종 제출해야 하며, 선생님은 새 입금 증빙을 첨부해야 해요."}
                </p>
              </section>
            )}
            {isCounterpartyFirst && step !== "proof" && (
              <section className="registration-round-notice" role="status">
                상대방이 이번 성사 등록을 이미 최종 제출했어요. 내 정보를 제출하면 대조가 진행되며, 최종 제출 후에는 수정할 수 없어요.
              </section>
            )}
            {isTeacher && step === "proof" ? (
              <form className="form registration-form" onSubmit={submitProof}>
                <fieldset className="form-fields" disabled={busy}>
              <section className="registration-payment-intro">
                <h2>수업료를 확인할 수 있는 자료를 제출 후 수수료를 납부해주세요.</h2>
                <p>수업료를 입금 받으신 뒤에 등록해주세요. 수업료를 계좌이체로 받으신 경우 입금 내역을, 현금으로 받으신 경우 현금의 사진을 찍어 첨부해주세요. 제출하신 자료는 클래씨 운영팀만 확인 가능하며, 안전하게 보호됩니다.</p>
              </section>
              <section className="registration-payment-details">
                <h3>수수료 납부 계좌 안내</h3>
                <div className="registration-payment-card">
                <dl>
                  <div>
                    <dt>납부하실 금액</dt>
                    <dd className="registration-commission-amount">{money(payment?.amount)}원</dd>
                  </div>
                  <small>
                    {tuitionLabel} {money(Number(tuition.replaceAll(",", "")) || 0)}원 × {formatCommissionRate(payment?.commissionRateBps)}%
                  </small>
                  <div><dt>은행</dt><dd>{payment?.bank || ""}</dd></div>
                  <div>
                    <dt>계좌번호</dt>
                    <dd>
                      {payment?.accountNumber || ""}
                      <button type="button" className="text-button" onClick={copyPaymentAccount}>
                        복사
                      </button>
                    </dd>
                  </div>
                </dl>
                </div>
              </section>
              <div className="registration-proof-field">
                <div className="registration-proof-head">
                  <FieldLabel required>증명 자료 제출</FieldLabel>
                  <span>({proofFiles.length}/3)</span>
                </div>
                <FilePicker
                  accept="image/jpeg,image/png"
                  multiple
                  disabled={proofFiles.length >= 3}
                  placeholder="JPG, 혹은 PNG 파일을 업로드 해주세요"
                  trailing={<Plus size={28} aria-hidden="true" />}
                  onChange={addProofFiles}
                />
              </div>
              {proofFiles.length > 0 && (
                <ul className="registration-proof-files" aria-label="선택한 증명 자료">
                  {proofFiles.map((file, index) => (
                    <li key={`${file.name}-${file.lastModified}`}>
                      <span>{file.name}</span>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => setProofFiles((current) => current.filter((_, fileIndex) => fileIndex !== index))}
                      >
                        삭제
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {error && <p className="error" role="alert">{error}</p>}
              <Btn className="primary full" disabled={busy}>{busy ? "등록 중…" : "등록"}</Btn>
                </fieldset>
            </form>
            ) : (
              <form className="form registration-form" onSubmit={submitBasic}>
                <fieldset className="form-fields" disabled={busy}>
              <h2>{isTeacher ? "이 학생과 수업이 시작되었나요?" : "이 선생님과 수업이 시작되었나요?"}</h2>
              <label>
                <FieldLabel required>수업 시작일</FieldLabel>
                <span className={`date-field${startDate ? " has-value" : ""}`}>
                  <input className="registration-date-input" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required />
                  <span className="date-placeholder" aria-hidden="true">수업 시작일을 선택해주세요.</span>
                </span>
              </label>
              <label>
                <FieldLabel required>수업 유형</FieldLabel>
                <select value={classType} onChange={(event) => setClassType(event.target.value)}>
                  <option value="SHORT_TERM">단기 수업</option>
                  <option value="REGULAR">정규 수업</option>
                </select>
                <small> 4주 미안 수업인 경우 단기 수업을, 4주 이상 수업인 경우 정규 수업을 선택해주세요.</small>
              </label>
              <div className="chip-form-field">
              <div className="subject-field">
                <FieldLabel required>수업 과목</FieldLabel>
                <button type="button" className="subject-picker-trigger" aria-label="과목 선택" onClick={() => setSubjectPickerOpen(true)}>
                  <span>{subjectIds.length ? `${subjectIds.length}개 과목 선택됨` : "관련된 과목을 선택해주세요."}</span>
                  <Search size={24} aria-hidden="true" />
                </button>
              </div>
              {subjectIds.length > 0 && <div className="subject-chips">{subjectIds.map((id) => {
                const subject = subjects.find((item) => item.number === id);
                return subject ? <button type="button" key={id} onClick={() => setSubjectIds((current) => current.filter((item) => item !== id))}>{subject.name} <span aria-hidden="true">×</span></button> : null;
              })}</div>}
              </div>
              <label className="registration-tuition-field">
                <FieldLabel required>{tuitionLabel}</FieldLabel>
                <span className="tuition-input"><input inputMode="numeric" value={tuition} onChange={(event) => setTuition(formatTuition(event.target.value))} placeholder={`${tuitionLabel}를 입력해주세요.`} required /><span className="tuition-input-suffix">(원)</span></span>
              </label>
              {!isTeacher && <section className="registration-payback">
                <div className="registration-payback-head">
                  <h2>페이백 계좌 등록</h2>
                  <Btn type="button" className="compact-action-button" onClick={loadPreviousPaybackAccount} disabled={busy || loadingPreviousAccount}>
                    <Download size={16} aria-hidden="true" />
                    {loadingPreviousAccount ? "불러오는 중…" : "이전 계좌 정보 불러오기"}
                  </Btn>
                </div>
                <p className="registration-payback-description">등록하신 첫 달 수업료의 0.5%를 수업 성사 후 3영업일 이내 입금해드려요.</p>
                <label><FieldLabel required>은행</FieldLabel><select value={bankCode} onChange={(event) => setBankCode(event.target.value)} required><option value="">선택</option>{BANKS.map((bank) => <option key={bank}>{bank}</option>)}</select></label>
                <label><FieldLabel required>계좌번호</FieldLabel><input inputMode="numeric" value={accountNumber} onChange={(event) => setAccountNumber(event.target.value)} placeholder="계좌번호를 입력해주세요." required /></label>
                <label><FieldLabel required>예금주명</FieldLabel><input value={accountHolder} onChange={(event) => setAccountHolder(event.target.value)} placeholder="예금주명을 입력해주세요." required /></label>
              </section>}
              {error && <p className="error" role="alert">{error}</p>}
              <Btn className="primary full" disabled={busy}>{busy ? (isTeacher ? "수수료 확정 중…" : "등록 중…") : isTeacher ? "다음" : "성사 등록하고 페이백 받기"}</Btn>
                </fieldset>
            </form>
            )}
          </State>
        </div>
      </div>
      {subjectPickerOpen && <SubjectPicker subjects={subjects} selectedIds={subjectIds} onChange={setSubjectIds} onClose={() => setSubjectPickerOpen(false)} />}
    </main>
  );
}
