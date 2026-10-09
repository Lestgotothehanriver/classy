import React, { useContext, useState } from "react";
import { api, list } from "./api";
import {
  Ctx,
  Btn,
  Empty,
  State,
  useLoad,
  money,
  date,
  Modal,
  Subjects,
  AcademicFields,
  BANKS,
} from "./shared";
import { PageHeading, pageNames } from "./design";
import regions from "./regions.json";
import { ClassHistory } from "./contracts";

export function ActionForm({
  title,
  path,
  method = "POST",
  children,
  transform = (x) => Object.fromEntries(x),
  onDone,
  confirm,
  submit = "저장",
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
          <Btn className="primary" disabled={busy}>
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
        ) : page === "verification" ? (
          <Verification />
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
            ["누적 수익", "total_revenue"],
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
        onDone={resource.reload}
      >
        <p>정산 가능한 금액: {money(d.settleable_revenue)}</p>
        <p className="form-note">위 계좌 정보를 확인한 후 신청해 주세요.</p>
      </ActionForm>
    </State>
  );
}
function Verification() {
  const resource = useLoad("/pending/"),
    d = resource.data || {};
  const [editing, setEditing] = useState(false);
  const statusCode = d.status || "NOT_SUBMITTED";
  const status = {
    VERIFIED: "인증 완료",
    PENDING: "심사 중",
    RESUBMIT_REQUIRED: "재제출 필요",
    SUSPENDED: "보완 필요",
    REJECTED: "보완 필요",
    NOT_SUBMITTED: "미제출",
  };
  const canEditAcademicInfo = statusCode !== "PENDING";
  const canSubmitDocuments = !["VERIFIED", "PENDING"].includes(statusCode);
  const currentStudentNumber = String(d.student_number || "");

  return (
    <State resource={resource}>
      <section className="service-section">
        <h2>{status[statusCode] || "인증 서류를 제출해 주세요"}</h2>
        <h3>선생님 학력 정보</h3>
        <dl className="class-info-list">
          <div>
            <dt>학교</dt>
            <dd>{d.university || "미입력"}</dd>
          </div>
          <div>
            <dt>학과/전공</dt>
            <dd>{d.field || "미입력"}</dd>
          </div>
          <div>
            <dt>입학연도</dt>
            <dd>{currentStudentNumber ? `${currentStudentNumber}년` : "미입력"}</dd>
          </div>
        </dl>
        {canEditAcademicInfo ? (
          <Btn type="button" onClick={() => setEditing((value) => !value)}>
            {editing ? "수정 취소" : "학력 정보 수정"}
          </Btn>
        ) : (
          <p className="form-note">
            인증 서류 검토 중에는 학력 정보를 수정할 수 없습니다.
          </p>
        )}
        {d.rejection_reason && <p className="error">{d.rejection_reason}</p>}
      </section>
      {editing && (
        <ActionForm
          title="학교 정보 수정"
          path="/accounts/signup/instructor/"
          method="PATCH"
          submit="저장"
          transform={(form) => ({
            university: form.get("university").trim(),
            department: form.get("department").trim(),
            student_number: form.get("student_number").trim(),
          })}
          onDone={() => {
            setEditing(false);
            resource.reload();
          }}
        >
          <AcademicFields
            university={d.university || ""}
            department={d.field || ""}
            studentNumber={currentStudentNumber}
          />
          {statusCode === "VERIFIED" && (
            <p className="form-note">
              인증 완료 후 학력 정보를 변경하면 인증 서류를 다시 제출해야 합니다.
            </p>
          )}
        </ActionForm>
      )}
      {canSubmitDocuments && (
        <ActionForm
          title="학력 인증 서류"
          path={d.exists ? "/pending/upload/" : "/pending/"}
          multipart
          submit={d.exists ? "서류 다시 제출" : "인증 신청"}
          onDone={() => {
            setEditing(false);
            resource.reload();
          }}
        >
          <label>
            재학·졸업 등 증빙 서류
            <input
              name="files"
              type="file"
              multiple
              accept="application/pdf,image/*"
              required
            />
          </label>
          <p className="form-note">
            본인의 학교와 이름을 확인할 수 있는 서류를 선택해 주세요.
          </p>
        </ActionForm>
      )}
    </State>
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

function Support() {
  const [tab, setTab] = useState("hub");
  const [selectedId, setSelectedId] = useState(null);
  const [ticketType, setTicketType] = useState("");
  const tickets = useLoad("/support/tickets/");
  const purchases = useLoad(ticketType === "CASH_PAYMENT" ? "/cash/purchase-history/" : null, [ticketType]);
  const detail = useLoad(selectedId ? `/support/tickets/${selectedId}/` : null, [selectedId]);
  const { notify } = useContext(Ctx);
  if (tab === "mine") return <section className="service-section"><div className="section-title"><h2>내 문의</h2><Btn onClick={() => setTab("hub")}>고객센터</Btn></div><State resource={tickets}>{list(tickets.data).map((ticket) => <button type="button" className="history-row post-management-card" key={ticket.id} onClick={() => setSelectedId(ticket.id)}><b>{ticket.title}</b><p className="muted">{ticket.status} · {date(ticket.updated_at)} {ticket.unread_admin_replies ? "· 새 답변" : ""}</p></button>)}{!list(tickets.data).length && <Empty title="등록한 문의가 없습니다" text="필요한 운영 요청은 1:1 문의로 접수할 수 있어요." />}</State>{selectedId && <TicketThread ticket={detail.data} resource={detail} onClose={() => setSelectedId(null)} onUpdated={() => { tickets.reload(); detail.reload(); }} />}</section>;
  return (
    <>
      <section className="service-section"><h2>고객센터</h2><p className="muted">빠른 안내는 카카오 고객센터에서, 확인·처리가 필요한 요청은 1:1 문의 티켓으로 남겨주세요.</p><div className="actions"><a className="button" href="https://pf.kakao.com/_YxhWxlX" target="_blank" rel="noreferrer">카카오 고객센터 문의</a><Btn onClick={() => setTab("ticket")}>1:1 문의 티켓 접수</Btn><Btn onClick={() => setTab("mine")}>내 문의</Btn></div></section>
      {tab === "ticket" && <ActionForm title="1:1 문의 티켓" path="/support/tickets/" submit="문의 접수" transform={(entries) => { const body = Object.fromEntries(entries); if (!body.related_id) { delete body.related_id; delete body.related_kind; } return body; }} onDone={(_, form) => { form.reset(); setTicketType(""); tickets.reload(); setTab("mine"); }}><label>문의 유형<select name="ticket_type" required value={ticketType} onChange={(event) => setTicketType(event.target.value)}><option value="" disabled>문의 유형을 선택해주세요</option>{SUPPORT_TYPES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>{ticketType === "CASH_PAYMENT" && <label>관련 구매 내역<State resource={purchases}><select name="related_id" required defaultValue=""><option value="" disabled>구매 내역을 선택해주세요</option>{list(purchases.data).map((purchase) => <option key={purchase.id} value={purchase.id}>{date(purchase.date)} · {money(purchase.purchased_cash)} 캐시</option>)}</select></State><input type="hidden" name="related_kind" value="PURCHASE" /></label>}<label>제목 (선택)<input name="title" maxLength={200} /></label><label>문의 내용<textarea name="content" rows={7} required /></label><p className="form-note">접수 후 운영자 답변과 처리 상태는 내 문의에서 확인할 수 있어요.</p></ActionForm>}
    </>
  );
}

function TicketThread({ ticket, resource, onClose, onUpdated }) {
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const { notify } = useContext(Ctx);
  if (!ticket) return <State resource={resource} />;
  const closed = ticket.status === "CLOSED";
  return <Modal title={`문의 #${ticket.id}`} onClose={onClose}><div className="chat-messages">{ticket.messages?.map((message) => <article className="chat-message" key={message.id}><b>{message.sender_name || message.sender_kind}</b><p>{message.content}</p><small>{date(message.created_at)}</small></article>)}</div>{closed ? <p className="muted">종결된 문의는 읽기 전용입니다.</p> : <form className="form" onSubmit={async (event) => { event.preventDefault(); if (!content.trim()) return; setBusy(true); try { await api(`/support/tickets/${ticket.id}/messages/`, { method: "POST", body: new FormData(event.currentTarget) }); setContent(""); onUpdated(); notify("답변을 등록했습니다."); } catch (error) { notify(error.message); } finally { setBusy(false); } }}><label>추가 답변<textarea name="content" value={content} onChange={(event) => setContent(event.target.value)} required /></label><Btn className="primary" disabled={busy}>{busy ? "등록 중…" : "답변 등록"}</Btn></form>}</Modal>;
}

function Tutoring() {
  const { user, subjects, notify, detail } = useContext(Ctx),
    teacher = user.role === "instructor";
  const resource = useLoad(
    teacher ? "/tutoring/instructor-info/mine/" : "/tutoring/my-posts/",
  );
  const [editing, setEditing] = useState(null),
    [postTab, setPostTab] = useState("active");
  const rows = teacher
    ? resource.data
      ? [resource.data]
      : []
    : list(resource.data);
  const base = teacher
    ? "/tutoring/instructor-info/"
    : "/tutoring/posts/write/";
  const visibleRows = teacher
    ? rows
    : rows.filter((post) =>
        postTab === "active" ? post.is_active !== false : post.is_active === false,
      );
  return (
    <State resource={resource}>
      <section className="service-section">
        <div className="section-title">
          <h2>{teacher ? "나의 과외 소개" : "나의 모집 공고"}</h2>
          <Btn onClick={() => setEditing(teacher ? rows[0] || {} : {})}>
            {teacher ? "소개 작성·수정" : "새 모집 공고"}
          </Btn>
        </div>
        {!teacher && (
          <div
            className="registration-tabs"
            role="tablist"
            aria-label="모집 공고 상태"
          >
            <button
              type="button"
              role="tab"
              aria-selected={postTab === "active"}
              className={postTab === "active" ? "active" : ""}
              onClick={() => setPostTab("active")}
            >
              모집 중
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={postTab === "closed"}
              className={postTab === "closed" ? "active" : ""}
              onClick={() => setPostTab("closed")}
            >
              마감
            </button>
          </div>
        )}
        {visibleRows.map((x) => (
          <article className="history-row" key={x.id}>
            <button
              type="button"
              className="post-management-card"
              onClick={() =>
                detail(teacher ? "teachers" : "posts", x.id, x)
              }
            >
              <b>{x.title || "과외 소개"}</b>
              {teacher ? (
                <p className="muted">
                  {x.schedule} · {money(x.cost)}원
                </p>
              ) : (
                <>
                  <Subjects values={x.subjects} />
                  <p className="muted">
                    조회 {x.view_count || 0}회 ·{" "}
                    {x.relative_time || date(x.created_at)}
                  </p>
                </>
              )}
            </button>
            <div className="actions">
              <Btn onClick={() => setEditing(x)}>수정</Btn>
              {!teacher && (
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
              )}
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
          <p className="muted">
            {teacher
              ? "작성한 글이 없습니다."
              : postTab === "active"
                ? "모집 중인 공고가 없습니다."
                : "마감된 공고가 없습니다."}
          </p>
        )}
      </section>
      {editing && (
        <ActionForm
          key={editing.id || "new"}
          title={teacher ? "과외 소개" : "모집 공고 작성"}
          path={base + (editing.id ? editing.id + "/" : "")}
          method={editing.id ? "PATCH" : "POST"}
          onDone={() => {
            setEditing(null);
            resource.reload();
          }}
          transform={(f) => {
            const d = Object.fromEntries(f);
            d.subjects = f.getAll("subjects").map(Number);
            d.regions = f.getAll("regions").map(Number);
            d.cost = Number(d.cost);
            return d;
          }}
        >
          {!teacher && (
            <>
              <label>
                제목
                <input
                  name="title"
                  defaultValue={editing.title}
                  required
                  maxLength={255}
                />
              </label>
              <label>
                학년
                <select name="grade" defaultValue={editing.grade || "사회인"}>
                  {[
                    "유치원생",
                    "초1",
                    "초2",
                    "초3",
                    "초4",
                    "초5",
                    "초6",
                    "중1",
                    "중2",
                    "중3",
                    "고1",
                    "고2",
                    "고3",
                    "N수생",
                    "대학생",
                    "사회인",
                  ].map((x) => (
                    <option key={x}>{x}</option>
                  ))}
                </select>
              </label>
              <label>
                계열
                <select name="field" defaultValue={editing.field || ""}>
                  <option value="">해당 없음</option>
                  {["문과", "이과", "예체능", "특성화", "기타"].map((x) => (
                    <option key={x}>{x}</option>
                  ))}
                </select>
              </label>
              <label>
                학습 상황·목표
                <textarea
                  name="situation"
                  defaultValue={editing.situation}
                  maxLength={255}
                />
              </label>
            </>
          )}
          <label>
            과목
            <select
              name="subjects"
              multiple
              size={5}
              defaultValue={(editing.subjects || []).map((x) =>
                String(
                  x.number || subjects.find((s) => s.name === x)?.number || x,
                ),
              )}
              required
            >
              {subjects.map((x) => (
                <option key={x.number} value={x.number}>
                  {x.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            활동 지역
            <select
              name="regions"
              multiple
              size={5}
              defaultValue={(editing.regions || []).map((x) =>
                String(
                  regions.find((r) => r[1] === (x.label || x))?.[0] ||
                    x.number ||
                    x.id ||
                    x,
                ),
              )}
            >
              {regions.map(([id, name]) => (
                <option value={id} key={id}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            수업 방식
            <select name="method" defaultValue={editing.method || "대면"}>
              <option>대면</option>
              <option>비대면</option>
              <option value="대면,비대면">모두 가능</option>
            </select>
          </label>
          <label>
            과외비 (원)
            <input
              type="number"
              name="cost"
              min="0"
              step="1000"
              defaultValue={editing.cost || 0}
              required
            />
          </label>
          <label>
            수업 가능 시간
            <input
              name="schedule"
              defaultValue={editing.schedule}
              maxLength={255}
              required
            />
          </label>
          {teacher && (
            <label>
              활동 지역
              <input
                name="location"
                defaultValue={editing.location}
                maxLength={255}
              />
            </label>
          )}
          <label>
            기타 소개
            <textarea name="etc" defaultValue={editing.etc} maxLength={255} />
          </label>
          <Btn type="button" onClick={() => setEditing(null)}>
            취소
          </Btn>
        </ActionForm>
      )}
      <ClassHistory />
    </State>
  );
}

export function ReportForm({ source, id }) {
  return (
    <details className="service-section">
      <summary>신고하기</summary>
      <ActionForm
        path="/report/create/"
        submit="신고 접수"
        transform={(f) => ({
          source,
          target_id: id,
          choices: [f.get("reason")],
          description: f.get("description"),
        })}
      >
        <label>
          신고 사유
          <select name="reason">
            {[
              ["inappropriate_content", "부적절한 내용"],
              ["false_information", "허위 정보"],
              ["abusive_language", "욕설·비방"],
              ["other", "기타"],
            ].map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          상세 내용
          <textarea name="description" required />
        </label>
      </ActionForm>
    </details>
  );
}
