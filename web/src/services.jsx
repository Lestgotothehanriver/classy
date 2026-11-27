import React, { useContext, useEffect, useRef, useState } from "react";
import { BookOpen, CheckCircle2, ChevronDown, ChevronRight, CircleAlert, CircleHelp, Eye, Flag, Hourglass, ImagePlus, PauseCircle, PenLine, PlayCircle, ShieldCheck, Star, X } from "lucide-react";
import { api, downloadProtectedFile, list } from "./api";
import {
  Ctx,
  Btn,
  Empty,
  State,
  useLoad,
  money,
  date,
  Modal,
  CustomModal,
  Subjects,
  AcademicFields,
  BANKS,
  FilePicker,
  MobileBackAction,
} from "./shared";
import { Avatar, PageHeading, pageNames } from "./design";
import { ClassHistory } from "./contracts";
import { StudentPostFormFields, toStudentPostPayload } from "./student-post-form";

const VERIFICATION_SUBMIT_PATH = "/studio/verification/submit";

export function ActionForm({
  title,
  path,
  method = "POST",
  children,
  transform = (x) => Object.fromEntries(x),
  onDone,
  confirm,
  submit = "저장",
  submitDisabled = false,
  multipart = false,
}) {
  const { notify } = useContext(Ctx),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <section className="service-section">
      {title && <h2>{title}</h2>}
      <form
        className="form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (submitDisabled) return;
          if (confirm && !window.confirm(confirm)) return;
          const form = e.currentTarget,
            body = new FormData(form);
          setBusy(true);
          setError("");
          try {
            const result = await api(path, {
              method,
              body: multipart ? body : transform(body),
              ...(multipart ? { signal: AbortSignal.timeout(600000) } : {}),
            });
            await onDone?.(result, form);
            notify("요청을 완료했습니다.");
          } catch (e) {
            setError(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <fieldset disabled={busy} className="form-fields">
          {children}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <Btn className="primary" disabled={busy || submitDisabled}>
            {busy ? "처리 중…" : submit}
          </Btn>
        </fieldset>
      </form>
    </section>
  );
}

export function Services({ page, onLogout }) {
  const { user } = useContext(Ctx);
  if (
    ["settlement", "verification"].includes(page) &&
    user.role !== "instructor"
  )
    return <Empty title="선생님 전용 메뉴입니다" />;
  return (
    <>
      <PageHeading title={pageNames[page]} />
      <div className="services-layout">
        {page === "cash" ? (
          <Cash />
        ) : page === "settlement" ? (
          <Settlement />
        ) : page === "account" ? (
          <Account onLogout={onLogout} />
        ) : page === "tutoring-manage" ? (
          <Tutoring />
        ) : (
          <Support />
        )}
      </div>
    </>
  );
}
function Cash() {
  const { user, refreshUser, notify, go } = useContext(Ctx),
    [tab, setTab] = useState("rental");
  const [refund, setRefund] = useState(null);
  const history = useLoad(
    "/cash/" + (tab === "rental" ? "rental" : "purchase") + "-history/",
  );
  return (
    <>
      <section className="service-section">
        <h2>보유 캐시</h2>
        <p className="balance-number">
          {money(user.cash)} <small>캐시</small>
        </p>
        <p className="form-note">
          충전한 캐시는 같은 계정에서 함께 사용할 수 있습니다.
        </p>
      </section>
      <section className="service-section">
        <div className="actions">
          <Btn
            onClick={() => setTab("rental")}
            className={tab === "rental" ? "primary" : ""}
          >
            대여 내역
          </Btn>
          <Btn
            onClick={() => setTab("purchase")}
            className={tab === "purchase" ? "primary" : ""}
          >
            충전 내역
          </Btn>
        </div>
        <State resource={history}>
          {list(history.data).length ? (
            list(history.data).map((x) => (
              <article className="history-row" key={x.id}>
                <div>
                  <b>{x.lecture_title || "캐시 충전"}</b>
                  <p className="muted">
                    {date(x.date)} ·{" "}
                    {x.is_canceled
                      ? "취소됨"
                      : x.is_refunded
                        ? "환불됨"
                        : `${money(x.purchased_cash)} 캐시`}
                  </p>
                  {x.refund_reason && (
                    <p className="form-note">{x.refund_reason}</p>
                  )}
                </div>
                {tab === "purchase" && (
                  <Btn
                    onClick={async () => {
                      try {
                        const d = await api(
                          `/cash/purchases/${x.id}/refund-eligibility/`,
                        );
                        setRefund(d);
                      } catch (e) {
                        notify(e.message);
                      }
                    }}
                  >
                    환불 조건 확인
                  </Btn>
                )}
              </article>
            ))
          ) : (
            <Empty
              title="이용 내역이 없습니다"
              text="캐시 사용 내역을 이곳에서 확인할 수 있어요."
            />
          )}
        </State>
      </section>
      {refund && (
        <Modal title="환불 안내" onClose={() => setRefund(null)}>
          <p>{refund.reason}</p>
          <div className="actions">
            {refund.action === "store_request" && (
              <a
                className="btn primary"
                href={
                  refund.platform === "google"
                    ? "https://play.google.com/store/account/orderhistory"
                    : "https://reportaproblem.apple.com"
                }
                target="_blank"
                rel="noreferrer"
              >
                결제처에서 환불 요청
              </a>
            )}
            {refund.action === "support_inquiry" && (
              <Btn onClick={() => go("support")}>고객센터에 문의</Btn>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
function Settlement() {
  const resource = useLoad("/mypage/instructor/settlement-info/"),
    d = resource.data || {};
  const isSettlementUnavailable = Number(d.settleable_revenue ?? 0) <= 0;
  const currentBank = d.account_info?.bank || "";
  const bankOptions =
    currentBank && !BANKS.includes(currentBank)
      ? [currentBank, ...BANKS]
      : BANKS;
  return (
    <State resource={resource}>
      <section className="service-section">
        <h2>강의 수익</h2>
        <div className="studio-summary">
          {[
            ["누적 캐시 수익", "total_revenue"],
            ["정산 가능", "settleable_revenue"],
            ["정산 진행 중", "pending_revenue"],
            ["정산 완료", "completed_revenue"],
          ].map(([label, key]) => (
            <span key={key}>
              {label}
              <b>{money(d[key])}</b>
            </span>
          ))}
        </div>
      </section>
      <ActionForm
        title="정산 계좌"
        path="/cash/account/"
        onDone={resource.reload}
        key={JSON.stringify(d.account_info)}
      >
        <label>
          은행
          <select name="bank" defaultValue={currentBank} required>
            <option value="" disabled>
              은행을 선택해주세요
            </option>
            {bankOptions.map((bank) => (
              <option key={bank} value={bank}>
                {bank}
              </option>
            ))}
          </select>
        </label>
        {[
          ["account_number", "계좌번호"],
          ["account_holder", "예금주"],
        ].map(([name, label]) => (
          <label key={name}>
            {label}
            <input
              name={name}
              defaultValue={d.account_info?.[name] || ""}
              required
            />
          </label>
        ))}
      </ActionForm>
      <ActionForm
        title="정산 신청"
        path="/mypage/instructor/request-settlement/"
        confirm="정산 가능한 수익의 지급을 신청할까요?"
        submit="정산 신청"
        submitDisabled={isSettlementUnavailable}
        onDone={resource.reload}
      >
        <p>정산 가능한 캐시: {money(d.settleable_revenue)}</p>
        {isSettlementUnavailable && (
          <p className="form-note">정산 가능한 수익이 생기면 신청할 수 있어요.</p>
        )}
        <p className="form-note">위 계좌 정보를 확인한 후 신청해 주세요.</p>
      </ActionForm>
    </State>
  );
}
export function VerificationPage() {
  const { go, user } = useContext(Ctx);
  const resource = useLoad(user?.role === "instructor" ? "/pending/" : null),
    d = resource.data || {};
  const [view, setView] = useState(() =>
    location.pathname === VERIFICATION_SUBMIT_PATH ? "submit" : "manage",
  );
  const statusCode = d.status || "NOT_SUBMITTED";
  const canEditAcademicInfo = statusCode !== "PENDING";
  const canSubmitDocuments = !["VERIFIED", "PENDING"].includes(statusCode);
  const submitLabel = statusCode === "NOT_SUBMITTED"
    ? "제출하러 가기"
    : "재제출하러 가기";
  const currentStudentNumber = String(d.student_number || "");
  const [isReasonOpen, setIsReasonOpen] = useState(false);
  const [proofFileCount, setProofFileCount] = useState(0);
  const [proofFileName, setProofFileName] = useState("");
  const statusCopy = {
    NOT_SUBMITTED: [CircleAlert, "아직 인증 서류를 제출하지 않았어요", "alert"],
    VERIFIED: [CheckCircle2, "대학 인증이 완료되었습니다.", "success"],
    PENDING: [Hourglass, "서류를 성실히 검토하고 있어요. 검토는 최대 24시간 내에 완료돼요.", "pending"],
    RESUBMIT_REQUIRED: [CircleAlert, "학력 정보가 수정되었어요. 서류를 다시 제출해 주세요.", "alert"],
    SUSPENDED: [CircleAlert, "인증 서류가 반려되었어요. 내용을 확인한 뒤 서류를 다시 제출해 주세요.", "alert"],
    REJECTED: [CircleAlert, "인증 서류가 반려되었어요. 내용을 확인한 뒤 다시 제출해 주세요.", "alert"],
  };

  useEffect(() => {
    if (
      location.pathname === VERIFICATION_SUBMIT_PATH &&
      !history.state?.verificationSubmit
    ) {
      history.replaceState({ verificationManage: true }, "", "/studio/verification");
      history.pushState({ verificationSubmit: true }, "", VERIFICATION_SUBMIT_PATH);
    }

    const syncViewFromRoute = () => {
      setView(
        location.pathname === VERIFICATION_SUBMIT_PATH ? "submit" : "manage",
      );
    };
    window.addEventListener("popstate", syncViewFromRoute);
    return () => window.removeEventListener("popstate", syncViewFromRoute);
  }, []);

  function openSubmitView() {
    if (location.pathname !== VERIFICATION_SUBMIT_PATH) {
      history.pushState({ verificationSubmit: true }, "", VERIFICATION_SUBMIT_PATH);
    }
    setView("submit");
  }

  function returnToManageView() {
    setProofFileCount(0);
    setProofFileName("");
    if (
      location.pathname === VERIFICATION_SUBMIT_PATH &&
      history.state?.verificationSubmit
    ) {
      history.back();
      return;
    }
    history.replaceState(null, "", "/studio/verification");
    setView("manage");
  }

  if (user?.role !== "instructor") {
    return <VerificationPageFrame title="인증 서류 관리" onBack={() => go("profile")}><Empty title="선생님 전용 메뉴입니다" /></VerificationPageFrame>;
  }

  if (view === "edit") {
    return (
      <VerificationPageFrame title="학력 정보 수정" onBack={() => setView("manage")}>
        <ActionForm
          title="내 학적 정보"
          path="/accounts/signup/instructor/"
          method="PATCH"
          submit="저장"
          transform={(form) => ({
            university: form.get("university").trim(),
            department: form.get("department").trim(),
            student_number: form.get("student_number").trim(),
          })}
          onDone={() => {
            setView("manage");
            resource.reload();
          }}
        >
          <AcademicFields
            university={d.university || ""}
            department={d.field || ""}
            studentNumber={currentStudentNumber}
          />
          {statusCode === "VERIFIED" && (
            <p className="form-note">학력 정보를 변경하면 인증 서류를 다시 제출해야 합니다.</p>
          )}
        </ActionForm>
      </VerificationPageFrame>
    );
  }

  if (view === "submit") {
    return (
      <VerificationPageFrame
        title="학력 인증"
        onBack={returnToManageView}
        backLabel="인증 서류 관리로"
      >
        <ActionForm
          path={d.exists ? "/pending/upload/" : "/pending/"}
          multipart
          submit={d.exists ? "인증 서류 다시 제출하기" : "인증 서류 제출하기"}
          onDone={() => {
            returnToManageView();
            resource.reload();
          }}
        >
          <div className="verification-submit-form">
            <h2>학력 정보를 확인할 수 있는 자료를 제출해주세요.</h2>
            <div className="verification-submit-file">
              <div className="verification-submit-file-head">
                <p>증명 자료 제출</p>
                <span>({proofFileCount}/1)</span>
              </div>
              <FilePicker
                name="files"
                accept="application/pdf,image/*"
                multiple={false}
                required
                placeholder="PDF 혹은 JPG, PNG 파일을 업로드 해주세요"
                trailing={<ImagePlus size={24} aria-hidden="true" />}
                selectedFileNames={[proofFileName]}
                onChange={(event) => {
                  const [file] = event.target.files || [];
                  setProofFileCount(event.target.files?.length ?? 0);
                  setProofFileName(file?.name || "");
                }}
              />
            </div>
            <p className="verification-submit-note">
              증명 자료 제출은 학생증, 재학증명서, 졸업증명서 등으로 가능해요.<br />
              합격증명서는 증명 자료로 사용할 수 없어요.<br /><br />
              주민등록번호, 카드번호, QR코드 또는 바코드, 거주지 등은 가린 상태로 등록해 주세요. 단, 기본정보(이름, 사진 등), 학력정보(학과, 학번, 학적상태 등)는 반드시 표시되어야 해요.
            </p>
            <div className="verification-reason">
              <button
                type="button"
                className="verification-reason-toggle"
                aria-expanded={isReasonOpen}
                aria-controls="verification-reason-description"
                onClick={() => setIsReasonOpen((isOpen) => !isOpen)}
              >
                <CircleHelp size={16} aria-hidden="true" />
                인증 서류는 왜 제출하나요?
                <ChevronDown
                  size={16}
                  aria-hidden="true"
                  className={isReasonOpen ? "open" : ""}
                />
              </button>
              {isReasonOpen && (
                <p id="verification-reason-description" className="verification-reason-description">
                  클래씨는 학생과 선생님 간의 신뢰를 위해 선생님이 해당 학교의 재학생, 졸업생인지를 확인하고 있어요. 제출해주신 자료는 인증 목적으로만 사용되며 개인정보 처리방침에 따라 안전하게 보호 및 관리돼요.
                </p>
              )}
            </div>
          </div>
        </ActionForm>
      </VerificationPageFrame>
    );
  }

  return (
    <State resource={resource}>
      <VerificationPageFrame title="인증 서류 관리" onBack={() => go("profile")}>
        <section className="verification-guide-card">
          <ShieldCheck aria-hidden="true" />
          <div>
            <p>서비스 이용을 위해 학적 상태를 확인할 수 있는 학생증, 재학·휴학·재적·졸업증명서 등이 필요해요.</p>
          </div>
        </section>
        <section className="verification-section">
          <h2>인증 상태</h2>
          {(() => {
            const [Icon, message, tone] = statusCopy[statusCode] || statusCopy.NOT_SUBMITTED;
            return (
              <div className={`verification-status-card ${tone}`}>
                <Icon aria-hidden="true" />
                <p>{message}</p>
                {canSubmitDocuments && (
                  <Btn type="button" className="verification-status-action" onClick={openSubmitView}>
                    {submitLabel}<ChevronRight size={16} aria-hidden="true" />
                  </Btn>
                )}
              </div>
            );
          })()}
          {statusCode === "REJECTED" && d.rejection_reason && (
            <p className="verification-rejection-reason">{d.rejection_reason}</p>
          )}
        </section>
        <section className="verification-section">
          <div className="verification-section-head">
            <h2>내 학적 정보</h2>
            {canEditAcademicInfo ? <Btn type="button" className="button" onClick={() => setView("edit")}><PenLine size={16} aria-hidden="true" />수정</Btn> : null}
          </div>
          <dl className="verification-academic-card">
            <div><dt>대학교/대학원</dt><dd>{d.university || "-"}</dd></div>
            <div><dt>학과(부)/전공</dt><dd>{d.field || "-"}</dd></div>
            <div><dt>학번</dt><dd>{currentStudentNumber ? `${currentStudentNumber.slice(-2)}학번` : "-"}</dd></div>
          </dl>
          {!canEditAcademicInfo && <p className="form-note">인증 서류 검토 중에는 학력 정보를 수정할 수 없습니다.</p>}
        </section>
      </VerificationPageFrame>
    </State>
  );
}

function VerificationPageFrame({ title, onBack, backLabel = "마이페이지로", children }) {
  return (
    <main className="student-post-editor-page verification-page">
      <div className="student-post-editor-content">
        <PageHeading title={title}>
          <MobileBackAction type="button" onClick={onBack}>
            {backLabel}
          </MobileBackAction>
        </PageHeading>
        <div className="verification-content">{children}</div>
      </div>
    </main>
  );
}
function Account({ onLogout }) {
  const { user, refreshUser, setRole, notify } = useContext(Ctx),
    [phone, setPhone] = useState(""),
    [sent, setSent] = useState(false);
  const roles = useLoad("/accounts/profile-check/"),
    blocks = useLoad("/blocks/");
  const missing = user.role === "instructor" ? "student" : "instructor";
  return (
    <>
      <ActionForm
        title="프로필 사진"
        path="/accounts/me/image/"
        method="PATCH"
        multipart
        onDone={refreshUser}
      >
        <label>
          사진 선택
          <input type="file" name="profile_image" accept="image/*" required />
        </label>
      </ActionForm>
      <ActionForm
        title="휴대전화 변경"
        path="/accounts/me/phone/request/"
        onDone={() => setSent(true)}
        submit="인증번호 받기"
      >
        <label>
          새 휴대전화 번호
          <input
            name="phone"
            type="tel"
            required
            value={phone}
            onChange={(e) => {
              setPhone(e.target.value.replace(/\D/g, ""));
              setSent(false);
            }}
          />
        </label>
      </ActionForm>
      {sent && (
        <ActionForm
          path="/accounts/me/phone/verify/"
          transform={(f) => ({ phone, code: f.get("code") })}
          onDone={async () => {
            setSent(false);
            await refreshUser();
          }}
          submit="전화번호 변경 확정"
        >
          <label>
            인증번호
            <input name="code" required inputMode="numeric" maxLength={6} />
          </label>
        </ActionForm>
      )}
      <State resource={roles}>
        {!(roles.data?.available_roles || []).some(
          (x) => x.role === missing,
        ) && (
          <ActionForm
            title={
              missing === "student" ? "학생 프로필 추가" : "선생님 프로필 추가"
            }
            path={"/accounts/role-add/?role=" + missing}
            onDone={async (d) => {
              sessionStorage.setItem(
                "classy_roles",
                JSON.stringify(d.available_roles),
              );
              await refreshUser();
              setRole(missing);
            }}
          >
            {missing === "instructor" && (
              <>
                <AcademicFields />
                <label>
                  소개
                  <textarea name="instruction" />
                </label>
              </>
            )}
          </ActionForm>
        )}
      </State>
      <section className="service-section">
        <h2>차단 관리</h2>
        <State resource={blocks}>
          {list(blocks.data).map((x) => (
            <div className="history-row" key={x.id}>
              <b>{x.blocked_user_info?.name}</b>
              <Btn
                onClick={async () => {
                  try {
                    await api(`/blocks/${x.id}/`, { method: "DELETE" });
                    blocks.reload();
                  } catch (e) {
                    notify(e.message);
                  }
                }}
              >
                차단 해제
              </Btn>
            </div>
          ))}
          {!list(blocks.data).length && (
            <p className="muted">차단한 사용자가 없습니다.</p>
          )}
        </State>
      </section>
      <ActionForm
        title="회원 탈퇴"
        path="/accounts/withdraw/"
        method="POST"
        confirm="회원 탈퇴 시 계정이 삭제됩니다. 캐시와 정산 내역을 확인했으며 탈퇴하시겠습니까?"
        submit="회원 탈퇴"
        onDone={onLogout}
      >
        <label className="check-label">
          <input type="checkbox" required />
          계정 삭제에 동의합니다.
        </label>
      </ActionForm>
    </>
  );
}
const SUPPORT_TYPES = [
  ["NAME_CHANGE", "이름 변경"],
  ["CASH_PAYMENT", "캐시·결제"],
  ["TUTORING_FEE", "성사 수수료"],
  ["PAYBACK", "페이백"],
  ["VERIFICATION_PROFILE", "인증·프로필"],
];

const SUPPORT_STATUS_LABEL = {
  RECEIVED: "접수됨",
  IN_PROGRESS: "처리 중",
  WAITING_FOR_USER: "추가 정보 필요",
  RESOLVED: "처리 완료",
  CLOSED: "종결됨",
};

function Support() {
  const [tab, setTab] = useState("hub");
  const [selectedId, setSelectedId] = useState(null);
  const [ticketType, setTicketType] = useState("");
  const tickets = useLoad("/support/tickets/");
  const ticketContext = useLoad(tab === "ticket" ? "/support/ticket-context/" : null, [tab]);
  const detail = useLoad(selectedId ? `/support/tickets/${selectedId}/` : null, [selectedId]);
  const { notify, user, openChat } = useContext(Ctx);
  const conversations = useLoad(
    `/support/conversations/?role=${user.role}`,
    [user.role],
  );
  if (tab === "mine") return <section className="service-section"><div className="section-title"><h2>내 문의</h2><Btn onClick={() => setTab("hub")}>고객센터</Btn></div><State resource={tickets}>{list(tickets.data).map((ticket) => <button type="button" className="history-row post-management-card" key={ticket.id} onClick={() => setSelectedId(ticket.id)}><b>{ticket.title}</b><p className="muted">{ticket.status_label || SUPPORT_STATUS_LABEL[ticket.status]} · {date(ticket.updated_at)} {ticket.unread_admin_replies ? "· 새 답변" : ""}</p></button>)}{!list(tickets.data).length && <Empty title="등록한 문의가 없습니다" text="필요한 운영 요청은 1:1 문의로 접수할 수 있어요." />}</State>{selectedId && <TicketThread ticket={detail.data} resource={detail} onClose={() => setSelectedId(null)} onUpdated={() => { tickets.reload(); detail.reload(); }} />}</section>;
  return (
    <>
      <section className="service-section">
        <h2>고객센터</h2>
        <div className="support-actions">
          <a className="btn support-action" href="https://pf.kakao.com/_YxhWxlX" target="_blank" rel="noreferrer">카카오 고객센터 문의</a>
          <Btn className="support-action" onClick={() => {
            const conversation = list(conversations.data)[0];
            if (conversation) openChat(`support:${conversation.id}`);
            else notify("공식 계정 채팅방을 준비 중입니다.");
          }}>공식 계정 채팅</Btn>
          <Btn className="support-action" onClick={() => setTab("ticket")}>1:1 문의 티켓 접수</Btn>
          <Btn className="support-action" onClick={() => setTab("mine")}>내 문의</Btn>
        </div>
        <div className="info-panel support-guide">
          <p>문의 접수 후 처리 절차에 따른 알림을 받을 수 있어요.</p>
          <p>또한 1:1 문의 가능 유형은 아래와 같으며, 신속한 처리를 위해 추가적인 자료가 요구될 수 있습니다.</p>
          <ol>
            <li>캐시 결제/환불</li>
            <li>이름 변경</li>
            <li>과외 성사 수수료</li>
            <li>학생(학부모) 페이백</li>
            <li>강사 학력 인증</li>
          </ol>
          <p>기타 문의사항은 카카오 고객센터를 이용해주세요.</p>
        </div>
      </section>
      {tab === "ticket" && <ActionForm title="1:1 문의 티켓" path="/support/tickets/" submit="문의 접수" multipart transform={(entries) => { const body = Object.fromEntries(entries); if (!body.related_id) { delete body.related_id; delete body.related_kind; } return body; }} onDone={(_, form) => { form.reset(); setTicketType(""); tickets.reload(); setTab("mine"); }}><label>문의 유형<select name="ticket_type" required value={ticketType} onChange={(event) => setTicketType(event.target.value)}><option value="" disabled>문의 유형을 선택해주세요</option>{SUPPORT_TYPES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>{ticketType === "NAME_CHANGE" && <><label>변경할 성<input name="requested_last_name" required maxLength={150} /></label><label>변경할 이름<input name="requested_first_name" required maxLength={150} /></label><label>변경 사유<textarea name="name_change_reason" rows={3} required /></label></>}{ticketType === "CASH_PAYMENT" && <label>관련 구매 내역<State resource={ticketContext}><select name="related_id" required defaultValue=""><option value="" disabled>구매 내역을 선택해주세요</option>{list(ticketContext.data?.purchases).map((purchase) => <option key={purchase.id} value={purchase.id}>{purchase.label} · {date(purchase.created_at)}</option>)}</select></State><input type="hidden" name="related_kind" value="PURCHASE" /></label>}{["TUTORING_FEE", "PAYBACK"].includes(ticketType) && <label>관련 성사등록<State resource={ticketContext}><select name="related_id" required defaultValue=""><option value="" disabled>성사등록을 선택해주세요</option>{list(ticketContext.data?.tutoring_registrations).map((registration) => <option key={registration.id} value={registration.id}>{registration.label} · {registration.status}</option>)}</select></State><input type="hidden" name="related_kind" value="TUTORING_REGISTRATION" /></label>}{ticketType === "VERIFICATION_PROFILE" && <label>관련 학력 인증 신청<State resource={ticketContext}><select name="related_id" required defaultValue=""><option value="" disabled>학력 인증 신청을 선택해주세요</option>{list(ticketContext.data?.instructor_verifications).map((verification) => <option key={verification.id} value={verification.id}>{verification.label} · {verification.status}</option>)}</select></State><input type="hidden" name="related_kind" value="INSTRUCTOR_VERIFICATION" /></label>}<label>제목 (선택)<input name="title" maxLength={200} /></label><label>문의 내용<textarea name="content" rows={7} required /></label><label>첨부 파일 (선택, 최대 5개)<input name="files" type="file" multiple /></label><p className="form-note">접수 후 운영자 답변과 처리 상태는 내 문의에서 확인할 수 있어요.</p></ActionForm>}
    </>
  );
}

function TicketThread({ ticket, resource, onClose, onUpdated }) {
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const { notify } = useContext(Ctx);
  React.useEffect(() => {
    if (ticket?.id) api(`/support/tickets/${ticket.id}/read/`, { method: "POST" }).catch(() => {});
  }, [ticket?.id]);
  if (!ticket) return <State resource={resource} />;
  const closed = ticket.status === "CLOSED";
  return <Modal title={`문의 #${ticket.id} · ${ticket.status_label || SUPPORT_STATUS_LABEL[ticket.status]}`} onClose={onClose}><div className="chat-messages">{ticket.messages?.map((message) => <article className="chat-message" key={message.id}><b>{message.sender_name || message.sender_kind}</b><p>{message.content}</p>{message.attachments?.map((attachment) => <button type="button" className="text-button" key={attachment.id} onClick={async () => { try { await downloadProtectedFile(`/support/tickets/${ticket.id}/attachments/${attachment.id}/`, attachment.filename); } catch (error) { notify(error.message); } }}>첨부: {attachment.filename}</button>)}<small>{date(message.created_at)}</small></article>)}</div>{closed ? <p className="muted">종결된 문의는 읽기 전용입니다.</p> : <form className="form" onSubmit={async (event) => { event.preventDefault(); if (!content.trim()) return; setBusy(true); try { await api(`/support/tickets/${ticket.id}/messages/`, { method: "POST", body: new FormData(event.currentTarget) }); setContent(""); onUpdated(); notify("답변을 등록했습니다."); } catch (error) { notify(error.message); } finally { setBusy(false); } }}><label>추가 답변<textarea name="content" value={content} onChange={(event) => setContent(event.target.value)} required /></label><label>첨부 파일 (선택, 최대 5개)<input name="files" type="file" multiple /></label><Btn className="primary" disabled={busy}>{busy ? "등록 중…" : "답변 등록"}</Btn></form>}</Modal>;
}

/** 과외 리뷰의 항목별 점수와 비율을 표시한다. */
function TutoringReviewRatingGauge({ label, rating }) {
  const normalizedRating = Math.min(5, Math.max(0, Number(rating) || 0));
  const displayRating = Number.isInteger(normalizedRating)
    ? String(normalizedRating)
    : normalizedRating.toFixed(1);

  return (
    <div className="teacher-rating-gauge">
      <div>
        <span>{label}</span>
        <span><b>{displayRating}</b>/5</span>
      </div>
      <span className="teacher-rating-gauge-track" aria-hidden="true">
        <span style={{ width: `${(normalizedRating / 5) * 100}%` }} />
      </span>
    </div>
  );
}

function Tutoring() {
  const { user, subjects, notify, go, openPostDetail } = useContext(Ctx),
    teacher = user.role === "instructor";
  const resource = useLoad(
    teacher ? "/tutoring/instructor-info/mine/" : "/tutoring/my-posts/",
  );
  const tutoringStatus = useLoad(
    teacher && resource.data?.instructor
      ? `/tutoring/instructors/${resource.data.instructor}/info/`
      : null,
    [teacher, resource.data?.instructor],
    { keepDataOnReload: true },
  );
  const [postTab, setPostTab] = useState("active"),
    [managementTab, setManagementTab] = useState("posts"),
    [teacherProfileTab, setTeacherProfileTab] = useState("info"),
    [isTutoringStatusExpanded, setIsTutoringStatusExpanded] = useState(true),
    [tutoringStatusBusy, setTutoringStatusBusy] = useState(false);
  const tutoringReviews = useLoad(
    teacher && teacherProfileTab === "reviews" && resource.data?.instructor
      ? `/tutoring/instructors/${resource.data.instructor}/reviews/`
      : null,
    [teacher, teacherProfileTab, resource.data?.instructor],
  );
  const rows = teacher
    ? resource.data
      ? [resource.data]
      : []
    : list(resource.data);
  const base = "/tutoring/posts/write/";
  const visibleRows = teacher
    ? rows
    : rows.filter((post) =>
        postTab === "active" ? post.is_active !== false : post.is_active === false,
      );
  const postSubjectLabel = (values) => {
    const labels = (Array.isArray(values) ? values : [])
      .map((value) => {
        if (typeof value === "object") return value.label || value.name;
        if (typeof value === "string" && !/^\d+$/.test(value)) return value;
        return subjects.find((subject) => subject.number === Number(value))?.name;
      })
      .filter(Boolean);
    const visible = labels.slice(0, 3).join(", ");
    return labels.length > 3 ? `${visible} 외 ${labels.length - 3}` : visible;
  };
  const isTutoring = Boolean(tutoringStatus.data?.is_tutoring);
  const isTutoringStatusReady = !tutoringStatus.loading && !tutoringStatus.error;
  const tutoringStats = tutoringStatus.data || {};
  const averageRating = Number(tutoringStats.avg_rating);
  const tutoringReviewRows = list(tutoringReviews.data);
  const methodLabel = (method) =>
    method === "ONLINE" || method === "비대면"
      ? "비대면"
      : method === "OFFLINE" || method === "대면"
        ? "대면"
        : method || "협의";
  const reviewAverage = (key) => {
    const scores = tutoringReviewRows.map((review) => Number(review[key])).filter(Number.isFinite);
    return scores.length ? scores.reduce((total, score) => total + score, 0) / scores.length : 0;
  };
  const professionalism = reviewAverage("professionalism");
  const teachingSkill = reviewAverage("teaching_skill");
  const punctuality = reviewAverage("punctuality");
  const totalReviewRating = tutoringReviewRows.length
    ? (professionalism + teachingSkill + punctuality) / 3
    : 0;
  const formatRating = (rating) =>
    Number.isInteger(rating) ? String(rating) : rating.toFixed(1);
  const classTypeLabel = (classType) => {
    if (!classType) return "";
    return classType === "단기 수업" || classType === "SHORT_TERM"
      ? "단기 수업"
      : "정규 수업";
  };

  async function toggleTutoringStatus() {
    if (tutoringStatusBusy) return;
    const next = !isTutoring;
    setTutoringStatusBusy(true);
    try {
      await api("/accounts/signup/instructor/", {
        method: "PUT",
        body: { is_tutoring: next },
      });
      notify(next ? "과외 모집이 재개되었습니다." : "과외 모집이 중지되었습니다.");
      tutoringStatus.reload();
    } catch (error) {
      notify(error.message);
    } finally {
      setTutoringStatusBusy(false);
    }
  }

  return (
    <>
      {!teacher && (
        <section className="student-payback-notice">
          <b>페이백 안내: 성사 등록 시 수업료 일부를 돌려드려요.</b>
          <p>
            수업 성사 등록 시 등록하신 첫 달 수업료의 0.5%를 고객님의 계좌로 입금해드려요.
            페이백은 선생님과 학생 모두 수업 신고를 완료하신 뒤 등록하신 계좌로 3영업일 이내 입금됩니다.
          </p>
        </section>
      )}
      <div
        className="tutoring-manage-tabs"
        role="tablist"
        aria-label="과외 관리 메뉴"
      >
        <button
          type="button"
          role="tab"
          aria-selected={managementTab === "posts"}
          className={managementTab === "posts" ? "active" : ""}
          onClick={() => setManagementTab("posts")}
        >
          {teacher ? "내 과외 프로필" : "내 모집 공고"}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={managementTab === "classes"}
          className={managementTab === "classes" ? "active" : ""}
          onClick={() => setManagementTab("classes")}
        >
          내 수업/과외
        </button>
      </div>
      {managementTab === "posts" && (
        <State resource={resource}>
      <section className="service-section">
        <div className="section-title">
          {teacher && <h2>내 과외 프로필</h2>}
          {!teacher && (
            <label className="tutoring-status-filter">
              <span>모집 공고 상태</span>
              <select
                value={postTab}
                onChange={(event) => setPostTab(event.target.value)}
              >
                <option value="active">모집 중</option>
                <option value="closed">마감</option>
              </select>
            </label>
          )}
          <Btn onClick={() => teacher ? go("tutoring-profile") : go("tutoring-post/new")}>
            {teacher && rows.length ? <><PenLine size={18} aria-hidden="true" /> 수정</> : teacher ? "과외 프로필 만들기" : "새 모집 공고 등록"}
          </Btn>
        </div>
        {!teacher && visibleRows.map((x) => (
          <article className="student-post-management-card" key={x.id}>
            <button
              type="button"
              className="student-post-management-open"
              onClick={() => openPostDetail(x)}
            >
              <b>{x.title || "과외 모집 공고"}</b>
              <span className="student-post-management-subject">
                <BookOpen size={16} aria-hidden="true" />
                {postSubjectLabel(x.subjects) || "과목 협의"}
              </span>
              <span className="student-post-management-meta">
                <Eye size={16} aria-hidden="true" />
                {x.view_count || 0}
                <i aria-hidden="true" />
                {x.relative_time || date(x.created_at)}
              </span>
            </button>
            <div className="student-post-management-actions">
              <Btn onClick={() => go(`tutoring-post/${x.public_id}`)}>수정</Btn>
              <Btn
                onClick={async () => {
                  try {
                    await api(base + x.id + "/", {
                      method: "PATCH",
                      body: { is_active: !x.is_active },
                    });
                    resource.reload();
                  } catch (e) {
                    notify(e.message);
                  }
                }}
              >
                {x.is_active ? "모집 마감" : "모집 재개"}
              </Btn>
              <Btn
                onClick={async () => {
                  if (!window.confirm("이 글을 삭제할까요?")) return;
                  try {
                    await api(base + x.id + "/", { method: "DELETE" });
                    resource.reload();
                  } catch (e) {
                    notify(e.message);
                  }
                }}
              >
                삭제
              </Btn>
            </div>
          </article>
        ))}
        {!visibleRows.length && (
          <p className={teacher ? "tutoring-management-empty" : "student-post-management-empty"}>
            {teacher
              ? "아직 과외 프로필이 없어요."
              : postTab === "active"
                ? "모집 중인 공고가 없어요."
                : "마감된 공고가 없어요."}
          </p>
        )}
        {teacher && rows.length > 0 && (
          <>
            <div className="registration-tabs detail-tabs tutoring-management-profile-tabs" role="tablist" aria-label="내 과외 프로필 상세">
              <button type="button" role="tab" aria-selected={teacherProfileTab === "info"} className={teacherProfileTab === "info" ? "active" : ""} onClick={() => setTeacherProfileTab("info")}>과외 정보</button>
              <button type="button" role="tab" aria-selected={teacherProfileTab === "reviews"} className={teacherProfileTab === "reviews" ? "active" : ""} onClick={() => setTeacherProfileTab("reviews")}>과외 리뷰</button>
            </div>
            {teacherProfileTab === "info" ? (
              <State resource={tutoringStatus}>
                <dl className="class-info-list post-detail-list tutoring-management-info-list">
                  <div><dt>수업 과목</dt><dd>{postSubjectLabel(tutoringStats.subjects) || "협의"}</dd></div>
                  <div><dt>수업 일정</dt><dd>{tutoringStats.schedule || "일정 협의 필요"}</dd></div>
                  <div><dt>수업료</dt><dd>{tutoringStats.cost_display || tutoringStats.cost || "협의 후 결정"}</dd></div>
                  <div><dt>수업 방식</dt><dd>{methodLabel(tutoringStats.method)}</dd></div>
                  <div><dt>수업 가능 지역</dt><dd>{postSubjectLabel(tutoringStats.regions) || tutoringStats.location || "협의"}</dd></div>
                  {tutoringStats.etc && <div><dt>상세</dt><dd>{tutoringStats.etc}</dd></div>}
                </dl>
              </State>
            ) : (
              <State resource={tutoringReviews}>
                {tutoringReviewRows.length ? (
                  <>
                    <section className="teacher-review-summary tutoring-management-review-summary">
                      <div className="teacher-review-total">
                        <Star size={24} fill="currentColor" aria-hidden="true" />
                        <b>{formatRating(totalReviewRating)}<span> /5</span></b>
                        <small>리뷰 {tutoringReviewRows.length}개</small>
                      </div>
                      <div className="teacher-review-summary-gauges">
                        <TutoringReviewRatingGauge label="전문적이에요" rating={professionalism} />
                        <TutoringReviewRatingGauge label="강의력이 좋아요" rating={teachingSkill} />
                        <TutoringReviewRatingGauge label="시간을 잘 지켜요" rating={punctuality} />
                      </div>
                    </section>
                    <div className="teacher-review-list tutoring-management-review-list">
                      {tutoringReviewRows.map((review) => (
                        <article className="teacher-review-card tutoring-management-review-card" key={review.id}>
                          <div className="teacher-review-author tutoring-management-review-head">
                            <Avatar src={review.student_profile_image} name={review.student_label || "학생"} />
                            <div className="teacher-review-identity">
                              <div>
                                <b>{review.student_label || "학생"}</b>
                                {classTypeLabel(review.class_type) && <span>{classTypeLabel(review.class_type)}</span>}
                              </div>
                              <small>{date(review.created_at)}</small>
                            </div>
                          </div>
                          {postSubjectLabel(review.subjects) && <p className="teacher-review-subjects tutoring-management-review-subjects"><BookOpen size={14} aria-hidden="true" />{postSubjectLabel(review.subjects)}</p>}
                          {review.comment && <p className="teacher-review-comment tutoring-management-review-comment">{review.comment}</p>}
                          <div className="teacher-review-scores tutoring-management-review-scores">
                            <TutoringReviewRatingGauge label="전문적이에요" rating={review.professionalism} />
                            <TutoringReviewRatingGauge label="강의력이 좋아요" rating={review.teaching_skill} />
                            <TutoringReviewRatingGauge label="시간을 잘 지켜요" rating={review.punctuality} />
                          </div>
                        </article>
                      ))}
                    </div>
                  </>
                ) : <p className="tutoring-management-empty">아직 리뷰가 없어요.</p>}
              </State>
            )}
            {teacherProfileTab === "info" && <div className="tutoring-profile-status-card">
              <div className="tutoring-profile-status-row">
                <span>과외 상태</span>
                <div>
                  <strong className={isTutoring ? "available" : "inactive"}>
                    {isTutoringStatusReady ? isTutoring ? "모집 중" : "구하지 않음" : "상태 확인 중"}
                  </strong>
                  <button type="button" className="tutoring-profile-status-toggle" aria-expanded={isTutoringStatusExpanded} aria-label={isTutoringStatusExpanded ? "과외 상태 접기" : "과외 상태 펼치기"} onClick={() => setIsTutoringStatusExpanded((expanded) => !expanded)}>
                    <ChevronDown size={20} aria-hidden="true" />
                  </button>
                </div>
              </div>
              {isTutoringStatusExpanded && <>
                {isTutoringStatusReady && (
                  <div className="tutoring-profile-status-details">
                    <div><span>클래씨에서 과외 구한 건 수</span><strong>{tutoringStats.tutoring_count ? `${tutoringStats.tutoring_count}건` : "-"}</strong></div>
                    <div><span>평균 수업료</span><strong>{tutoringStats.average_cost == null ? "-" : `${money(tutoringStats.average_cost)}원`}</strong></div>
                    <div><span>과외 리뷰 평점</span><strong>{tutoringStats.review_count > 0 && Number.isFinite(averageRating) ? averageRating.toFixed(1) : "-"}</strong></div>
                    <div><span>클래씨 랭킹</span><strong>{tutoringStats.current_rank == null ? "랭킹 외" : `${tutoringStats.current_rank}위`}</strong></div>
                  </div>
                )}
              </>}
              <Btn type="button" className="tutoring-profile-status-action" disabled={tutoringStatusBusy || !isTutoringStatusReady} onClick={toggleTutoringStatus}>
                {isTutoring ? <PauseCircle size={18} aria-hidden="true" /> : <PlayCircle size={18} aria-hidden="true" />}
                {tutoringStatusBusy ? "처리 중…" : isTutoring ? "과외 모집 중지" : "과외 모집 재개"}
              </Btn>
            </div>}
          </>
        )}
      </section>
        </State>
      )}
      {managementTab === "classes" && <ClassHistory />}
    </>
  );
}

/** 학생 모집 공고를 전용 페이지에서 작성하거나 수정한다. */
export function StudentPostEditorPage({ postId, returnTo = "" }) {
  const { subjects, go } = useContext(Ctx);
  const isNew = postId === "new";
  const returnDestination = returnTo || "tutoring-manage";
  const returnLabel = returnTo ? "선생님 프로필로" : "과외 관리로";
  const posts = useLoad(isNew ? null : "/tutoring/my-posts/", [postId]);
  const post = isNew
    ? {}
    : list(posts.data).find((item) => String(item.public_id) === String(postId));
  const content = post ? (
    <StudentPostEditorForm
      key={post.id || "new"}
      editing={post}
      subjects={subjects}
      returnDestination={returnDestination}
    />
  ) : (
    <Empty
      title="모집 공고를 찾을 수 없어요"
      text="목록에서 수정할 공고를 다시 선택해 주세요."
    >
      <Btn onClick={() => go(returnDestination)}>{returnLabel}</Btn>
    </Empty>
  );

  return (
    <main className="student-post-editor-page">
      <div className="student-post-editor-content">
        <PageHeading title={isNew ? "모집 공고 작성" : "모집 공고 수정"}>
          <MobileBackAction onClick={() => go(returnDestination)}>
            {returnLabel}
          </MobileBackAction>
        </PageHeading>
        {isNew ? content : <State resource={posts}>{content}</State>}
      </div>
    </main>
  );
}

/** 재사용 학생 모집 공고 폼을 페이지 저장 흐름에 연결한다. */
function StudentPostEditorForm({ editing, subjects, returnDestination }) {
  const { go } = useContext(Ctx);
  return (
    <ActionForm
      path={`/tutoring/posts/write/${editing.id ? `${editing.id}/` : ""}`}
      method={editing.id ? "PATCH" : "POST"}
      submit={editing.id ? "수정 완료" : "모집 공고 등록"}
      transform={toStudentPostPayload}
      onDone={() => go(returnDestination)}
    >
      <StudentPostFormFields editing={editing} subjects={subjects} />
      <Btn type="button" onClick={() => go(returnDestination)}>취소</Btn>
    </ActionForm>
  );
}

export function ReportForm({ source, id, label = "신고하기", className = "" }) {
  const [open, setOpen] = useState(false);
  const [selectedReasons, setSelectedReasons] = useState([]);
  const [description, setDescription] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [attachmentError, setAttachmentError] = useState("");
  const attachmentInputRef = useRef(null);
  const reasons = [
    ["inappropriate_content", "부적절한 내용"],
    ["false_information", "허위 정보 기재"],
    ["abusive_language", "비속어/폭언"],
    ["excessive_request", "불합리함/과도한 요구"],
    ["unreported_class_completion", "수업 성사 미신고"],
    ["other", "기타"],
  ];

  function toggleReason(reason) {
    setSelectedReasons((current) =>
      current.includes(reason)
        ? current.filter((value) => value !== reason)
        : [...current, reason],
    );
  }

  function setAttachmentFiles(files) {
    const imageFiles = Array.from(files).filter((file) =>
      ["image/jpeg", "image/png"].includes(file.type),
    );
    const nextAttachments = [...attachments, ...imageFiles].slice(0, 3);
    const transfer = new DataTransfer();
    nextAttachments.forEach((file) => transfer.items.add(file));
    if (attachmentInputRef.current)
      attachmentInputRef.current.files = transfer.files;
    setAttachments(nextAttachments);
    setAttachmentError(
      imageFiles.length !== files.length
        ? "JPG 또는 PNG 형식의 사진만 첨부할 수 있어요."
        : attachments.length + imageFiles.length > 3
          ? "사진 자료는 최대 3장까지 첨부할 수 있어요."
          : "",
    );
  }

  function removeAttachment(index) {
    const nextAttachments = attachments.filter((_, itemIndex) => itemIndex !== index);
    const transfer = new DataTransfer();
    nextAttachments.forEach((file) => transfer.items.add(file));
    if (attachmentInputRef.current)
      attachmentInputRef.current.files = transfer.files;
    setAttachments(nextAttachments);
    setAttachmentError("");
  }

  function closeReportDialog() {
    setOpen(false);
    setSelectedReasons([]);
    setDescription("");
    setAttachments([]);
    setAttachmentError("");
  }

  return (
    <>
      <Btn
        type="button"
        className={`report-form ${className}`.trim()}
        onClick={() => setOpen(true)}
      >
        <Flag size={16} aria-hidden="true" />
        {label}
      </Btn>
      {open && (
        <CustomModal
          title="신고하기"
          className="report-dialog"
          onClose={closeReportDialog}
        >
          <ActionForm
            path="/report/create/"
            submit="신고하기"
            multipart
            submitDisabled={!selectedReasons.length}
            onDone={closeReportDialog}
          >
            <input type="hidden" name="source" value={source} />
            <input type="hidden" name="target_id" value={id} />
            <fieldset className="report-reason-field">
              <legend>
                신고유형 <span className="required-label">필수</span>
              </legend>
              <p className="report-field-hint">복수 선택 가능</p>
              <div className="report-reason-list">
                {reasons.map(([value, reasonLabel]) => (
                  <label className="check-label" key={value}>
                    <input
                      type="checkbox"
                      name="choices"
                      value={value}
                      checked={selectedReasons.includes(value)}
                      onChange={() => toggleReason(value)}
                    />
                    {reasonLabel}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="report-description-field">
              <span className="report-field-label">
                상세 내용
                <small>{description.length}/500</small>
              </span>
              <textarea
                name="description"
                value={description}
                maxLength={500}
                rows={6}
                placeholder={"자세한 신고 이유 및 상세 내용을 적어주시면 보다 정확한 확인에 도움이 될 수 있습니다.\n작성해주신 내용은 운영팀에서만 확인합니다."}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            <section className="report-attachment-field" aria-labelledby="report-attachment-title">
              <div className="report-field-label">
                <span id="report-attachment-title">사진 자료</span>
                <small>{attachments.length}/3</small>
              </div>
              <FilePicker
                inputRef={attachmentInputRef}
                name="evidence_images"
                accept="image/jpeg,image/png"
                multiple
                placeholder="사진 자료를 업로드 해주세요."
                trailing={<ImagePlus size={18} aria-hidden="true" />}
                onChange={(event) => setAttachmentFiles(event.target.files)}
              />
              {attachmentError && <p className="error">{attachmentError}</p>}
              {attachments.map((file, index) => (
                <div className="report-attachment-row" key={`${file.name}-${file.lastModified}`}>
                  <span>{file.name}</span>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`${file.name} 삭제`}
                    onClick={() => removeAttachment(index)}
                  >
                    <X size={16} />
                  </button>
                </div>
              ))}
            </section>
          </ActionForm>
        </CustomModal>
      )}
    </>
  );
}
