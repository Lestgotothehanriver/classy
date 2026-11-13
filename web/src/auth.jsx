import React, { useContext, useState } from "react";
import { Eye, EyeOff, Search } from "lucide-react";
import { api } from "./api";
import {
  AcademicFields,
  Btn,
  Ctx,
  FieldLabel,
  RegionFields,
} from "./shared";
import { SubjectPicker } from "./studio";

const appPasswordPattern =
  /^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d\s])(?!.*\s).{8,16}$/;

const authPaths = {
  login: "/login",
  signup: "/signup",
  reset: "/password-reset",
};
const authNoticeStorageKey = "classy_auth_notice";

function formatPhoneNumber(value) {
  const digits = value.replace(/\D/g, "").slice(0, 11);
  if (digits.length <= 3) return digits;
  if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  const middleEnd = digits.length === 10 ? 6 : 7;
  return `${digits.slice(0, 3)}-${digits.slice(3, middleEnd)}-${digits.slice(middleEnd)}`;
}

function signupBirthDateMax() {
  const today = new Date();
  today.setFullYear(today.getFullYear() - 14);
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${today.getFullYear()}-${month}-${day}`;
}

function splitRealName(value) {
  const parts = value.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2)
    return { lastName: parts[0], firstName: parts.slice(1).join(" ") };
  const [name = ""] = parts;
  return name.length >= 2
    ? { lastName: name.slice(0, 1), firstName: name.slice(1) }
    : { lastName: "", firstName: name };
}

// Mirrors SignupAccountView, SignupVerifyPhoneView and the role-specific surveys.
export function Auth({ initial = "login" }) {
  const { setUser, setRole, subjects } = useContext(Ctx);
  const mode = initial;
  const [role, roleSet] = useState("student");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [phone, setPhone] = useState(""),
    [code, setCode] = useState("");
  const [sent, setSent] = useState(false),
    [verified, setVerified] = useState(false);
  const [resetToken, setResetToken] = useState("");
  const [notice, setNotice] = useState(() => {
    const savedNotice = sessionStorage.getItem(authNoticeStorageKey) || "";
    sessionStorage.removeItem(authNoticeStorageKey);
    return savedNotice;
  });
  const [isPasswordVisible, setIsPasswordVisible] = useState(false);
  const [isConfirmPasswordVisible, setIsConfirmPasswordVisible] =
    useState(false);
  const [selectedSubjectIds, setSelectedSubjectIds] = useState([]);
  const [isSubjectPickerOpen, setIsSubjectPickerOpen] = useState(false);
  const [birthDate, setBirthDate] = useState("");
  async function run(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  function switchMode(next) {
    location.assign(authPaths[next]);
  }
  function openPolicy(path) {
    window.open(path, "_blank", "noopener,noreferrer");
  }
  async function authenticate(data, preferred) {
    if (!data.token)
      throw new Error("로그인 정보를 받지 못했습니다. 다시 로그인해 주세요.");
    sessionStorage.setItem("classy_token", data.token);
    const roles = data.available_roles || [{ role: preferred }];
    sessionStorage.setItem("classy_roles", JSON.stringify(roles));
    try {
      const profile = await api("/accounts/me/");
      setUser(profile);
      setRole(preferred || roles[0]?.role || profile.role);
      location.assign("/home");
    } catch (e) {
      sessionStorage.removeItem("classy_token");
      sessionStorage.removeItem("classy_roles");
      throw e;
    }
  }
  function sms(verify) {
    run(async () => {
      if (!/^01\d{8,9}$/.test(phone))
        throw new Error("휴대전화 번호를 확인해 주세요.");
      const prefix =
        mode === "reset" ? "/accounts/password-reset/" : "/accounts/";
      const path =
        mode === "reset"
          ? verify
            ? "verify/"
            : "request/"
          : verify
            ? "verify-auth-sms/"
            : "send-auth-sms/";
      const result = await api(prefix + path, {
        method: "POST",
        body: { phone_number: phone, ...(verify ? { code } : {}) },
      });
      if (verify) {
        setVerified(true);
        setResetToken(result.reset_token || "");
        setNotice("휴대전화 인증을 완료했습니다.");
      } else {
        setSent(true);
        setVerified(false);
        setNotice("인증번호를 보냈습니다. 수신한 문자를 확인해 주세요.");
      }
    });
  }
  function submit(e) {
    e.preventDefault();
    const f = new FormData(e.currentTarget),
      values = Object.fromEntries(f);
    run(async () => {
      if (mode === "login")
        return authenticate(
          await api("/accounts/login/", {
            method: "POST",
            body: { email: values.email.trim(), password: values.password },
          }),
        );
      if (values.password !== values.confirm)
        throw new Error("비밀번호가 서로 다릅니다.");
      if (!appPasswordPattern.test(values.password))
        throw new Error(
          "비밀번호는 영문, 숫자, 특수문자를 포함해 8자 이상 16자 이하로 입력해주세요.",
        );
      if (!verified) throw new Error("휴대전화 인증을 완료해 주세요.");
      if (mode === "reset") {
        await api("/accounts/password-reset/confirm/", {
          method: "POST",
          body: {
            reset_token: resetToken,
            new_password: values.password,
            new_password_confirm: values.confirm,
          },
        });
        const resetConfirmation =
          "비밀번호를 변경했습니다. 새 비밀번호로 로그인해 주세요.";
        sessionStorage.setItem(authNoticeStorageKey, resetConfirmation);
        location.assign(authPaths.login);
        return;
      }
      const subjectLimit = role === "instructor" ? 3 : 9;
      if (!selectedSubjectIds.length)
        throw new Error("관심 과목을 설정해주세요.");
      if (selectedSubjectIds.length > subjectLimit)
        throw new Error(`과목은 최대 ${subjectLimit}개까지 선택할 수 있습니다.`);
      if (role === "instructor" && !values.university)
        throw new Error("학교를 선택해주세요.");
      const email = values.email.trim().toLowerCase();
      const emailCheck = await api(
        "/accounts/check-email/?email=" + encodeURIComponent(email),
      );
      if (!emailCheck.available)
        throw new Error(
          "이미 사용 중인 이메일입니다. 로그인 또는 비밀번호 찾기를 이용해 주세요.",
        );
      const nameCheck = await api(
        "/accounts/check-username/?user_name=" +
          encodeURIComponent(values.user_name.trim()),
      );
      if (!nameCheck.available) throw new Error("이미 사용 중인 닉네임입니다.");
      const selected = selectedSubjectIds;
      const name = splitRealName(values.real_name);
      const body = {
        email,
        password: values.password,
        user_name: values.user_name.trim(),
        first_name: name.firstName,
        last_name: name.lastName,
        phone,
        region: values.region,
        sex: values.sex,
        birth_date: values.birth_date,
        agreed_age: values.agreed_age === "true",
        agreed_terms: values.agreed_terms === "true",
        agreed_privacy: values.agreed_privacy === "true",
        agreed_marketing: values.marketing === "on",
      };
      if (role === "student") body.studentsubject = selected;
      else
        Object.assign(body, {
          university: values.university,
          department: values.department,
          student_number: values.student_number,
          instruction: values.instruction,
          instructorsubject: JSON.stringify(selected),
        });
      await authenticate(
        await api("/accounts/signup/" + role + "/", { method: "POST", body }),
        role,
      );
    });
  }
  return (
    <main className="auth-page">
      <section
        className={`auth-page-content${mode === "signup" || mode === "reset" ? " wide" : ""}`}
      >
        <div className="auth-page-scroll">
          <div className="auth-page-body">
          <div className="login-intro">
        <div className="auth-page-topbar">
          <img src="/app-icons/logo.svg" alt="CLASSY" />
          <h1 className="auth-page-hero">
            {mode === "login"
              ? "로그인"
              : mode === "signup"
                ? "회원가입"
                : "비밀번호 찾기"}
          </h1>
        </div>
        <h3>
          {mode === "login"
            ? "다시 만나서 반가워요!"
            : mode === "signup"
              ? "클래씨에 처음 오신 것을 환영해요!"
              : "가입할 때 등록하신 휴대전화 번호를 입력해주세요."}
        </h3>
        <h4>
          {mode === "login"
            ? "이메일과 비밀번호로 로그인 해주세요."
            : mode === "signup"
              ? "클래씨에서 사용할 회원님의 정보를 입력해주세요."
              : "휴대전화 인증 후 비밀번호를 재설정할 수 있어요."}
        </h4>
      </div>
      {mode === "signup" && (
        <div className="actions">
          <Btn
            className={role === "student" ? "primary" : ""}
            onClick={() => roleSet("student")}
          >
            학생으로 가입
          </Btn>
          <Btn
            className={role === "instructor" ? "primary" : ""}
            onClick={() => roleSet("instructor")}
          >
            선생님으로 가입
          </Btn>
        </div>
      )}
      <form className="form" onSubmit={submit}>
        <fieldset disabled={busy} className="form-fields">
          {mode !== "reset" && (
            <label>
              <FieldLabel required>이메일</FieldLabel>
              <input
                name="email"
                type="email"
                autoComplete="username"
                required
                placeholder="이메일 주소를 입력해주세요."
              />
            </label>
          )}
          {mode !== "login" && (
            <>
              {mode === "signup" && (
                <label>
                  <FieldLabel required>이름</FieldLabel>
                  <input
                    name="real_name"
                    required
                    autoComplete="name"
                    placeholder="실명을 입력해주세요."
                  />
                </label>
              )}
              <label>
                <FieldLabel required>휴대전화 번호</FieldLabel>
                <input
                  type="tel"
                  value={formatPhoneNumber(phone)}
                  onChange={(e) => {
                    setPhone(e.target.value.replace(/\D/g, "").slice(0, 11));
                    setVerified(false);
                    setSent(false);
                    setResetToken("");
                  }}
                  inputMode="numeric"
                  autoComplete="tel"
                  required
                  placeholder="'-' 없이 전화번호를 입력해주세요."
                />
              </label>
              <Btn type="button" onClick={() => sms(false)}>
                {sent ? "인증번호 다시 받기" : "인증번호 받기"}
              </Btn>
              {sent && !verified && (
                <div className="form">
                  <label>
                    인증번호
                    <input
                      inputMode="numeric"
                      value={code}
                      maxLength={6}
                      onChange={(e) => setCode(e.target.value)}
                      autoComplete="one-time-code"
                    />
                  </label>
                  <Btn type="button" onClick={() => sms(true)}>
                    인증 확인
                  </Btn>
                </div>
              )}
            </>
          )}
          <label>
            <FieldLabel required>
              {mode === "reset" ? "새 비밀번호" : "비밀번호"}
            </FieldLabel>
            <span className="password-field">
              <input
                name="password"
                type={isPasswordVisible ? "text" : "password"}
                required
                minLength={mode === "login" ? 1 : 8}
                maxLength={mode === "login" ? undefined : 16}
                autoComplete={
                  mode === "login" ? "current-password" : "new-password"
                }
                placeholder={mode === "login" ? "비밀번호를 입력해주세요." : "새 비밀번호를 입력해주세요."}
              />
              <button
                type="button"
                className="password-visibility-toggle"
                onClick={() => setIsPasswordVisible((visible) => !visible)}
                aria-label={
                  isPasswordVisible ? "비밀번호 숨기기" : "비밀번호 보기"
                }
                aria-pressed={isPasswordVisible}
              >
                {isPasswordVisible ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </span>
            {mode !== "login" && (
              <small>영문, 숫자, 특수문자를 포함해 8~16자로 입력해주세요.</small>
            )}
          </label>
          {mode !== "login" && (
            <label>
              <FieldLabel required>비밀번호 확인</FieldLabel>
              <span className="password-field">
                <input
                  name="confirm"
                  type={isConfirmPasswordVisible ? "text" : "password"}
                  required
                  minLength={8}
                  maxLength={16}
                  autoComplete="new-password"
                  placeholder={mode === "login" ? "비밀번호를 다시 입력해주세요." : "새 비밀번호를 다시 입력해주세요."}
                />
                <button
                  type="button"
                  className="password-visibility-toggle"
                  onClick={() =>
                    setIsConfirmPasswordVisible((visible) => !visible)
                  }
                  aria-label={
                    isConfirmPasswordVisible
                      ? "비밀번호 확인 숨기기"
                      : "비밀번호 확인 보기"
                  }
                  aria-pressed={isConfirmPasswordVisible}
                >
                  {isConfirmPasswordVisible ? (
                    <EyeOff size={20} />
                  ) : (
                    <Eye size={20} />
                  )}
                </button>
              </span>
            </label>
          )}
          {mode === "signup" && (
            <>
              <label>
                <FieldLabel required>닉네임</FieldLabel>
                <input
                  name="user_name"
                  required
                  minLength={2}
                  maxLength={13}
                  pattern="[A-Za-z0-9가-힣]+"
                  title="닉네임은 공백이나 특수문자 없이 2자 이상 13자 이하로 입력해주세요."
                  placeholder="사용하실 닉네임을 입력해주세요."
                />
                <small>공백·특수문자 없이 2~13자로 입력해주세요.</small>
              </label>
              <div className="form-columns">
                <label>
                  <FieldLabel required>생년월일</FieldLabel>
                  <span className={`date-field${birthDate ? " has-value" : ""}`}>
                    <input
                      className="birth-date-input"
                      name="birth_date"
                      type="date"
                      value={birthDate}
                      onChange={(event) => setBirthDate(event.target.value)}
                      required
                      min={signupBirthDateMax().slice(0, 4) - 100 + "-01-01"}
                      max={signupBirthDateMax()}
                      data-placeholder="생년월일 선택"
                    />
                    <span className="date-placeholder" aria-hidden="true">
                      생년월일 선택
                    </span>
                  </span>
                </label>
                <label>
                  <FieldLabel required>성별</FieldLabel>
                  <select name="sex" required defaultValue="">
                    <option value="" disabled>
                      성별 선택
                    </option>
                    <option>남성</option>
                    <option>여성</option>
                  </select>
                </label>
              </div>
              <RegionFields required showRequiredLabel />
              <div className="subject-field">
                <FieldLabel required>
                  {role === "instructor" ? "전문 수업 과목" : "관심 과목"}
                </FieldLabel>
                <button
                  type="button"
                  className="subject-picker-trigger"
                  aria-label="관심 과목 선택"
                  onClick={() => setIsSubjectPickerOpen(true)}
                >
                  <span>
                    {selectedSubjectIds.length
                      ? `${selectedSubjectIds.length}/${role === "instructor" ? 3 : 9}개 과목 선택됨`
                      : `${role === "instructor" ? "전문 수업 과목" : "관심 과목"}을 선택해주세요. (최대 ${role === "instructor" ? 3 : 9}개)`}
                  </span>
                  <Search size={24} aria-hidden="true" />
                </button>
              </div>
              {selectedSubjectIds.length > 0 && (
                <div className="subject-chips" aria-label="선택된 관심 과목">
                  {selectedSubjectIds.map((subjectId) => {
                    const subject = subjects.find(
                      (item) => item.number === subjectId,
                    );
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
              {role === "instructor" && (
                <>
                  <AcademicFields showRequiredLabel schoolSearch />
                  <label>
                    <FieldLabel required>한 줄 소개</FieldLabel>
                    <textarea name="instruction" rows={3} required maxLength={300} />
                  </label>
                  <p className="form-note">
                    가입 후 마이페이지에서 학력 인증 서류를 제출할 수 있습니다.
                  </p>
                </>
              )}
              <label className="check-label">
                <input
                  type="checkbox"
                  name="agreed_age"
                  value="true"
                  required
                />
                <span>[필수] 만 14세 이상입니다.</span>
              </label>
              <label className="check-label">
                <input
                  type="checkbox"
                  name="agreed_terms"
                  value="true"
                  required
                />
                <span>[필수] 서비스 이용약관 동의</span>
                <button
                  type="button"
                  className="terms-view-button"
                  onClick={() => openPolicy("/service-terms")}
                  aria-label="서비스 이용약관 보기"
                >
                  보기
                </button>
              </label>
              <label className="check-label">
                <input
                  type="checkbox"
                  name="agreed_privacy"
                  value="true"
                  required
                />
                <span>[필수] 개인정보 수집 및 이용 동의</span>
                <button
                  type="button"
                  className="terms-view-button"
                  onClick={() => openPolicy("/privacy")}
                  aria-label="개인정보 수집 및 이용 보기"
                >
                  보기
                </button>
              </label>
              <label className="check-label">
                <input type="checkbox" name="marketing" />
                [선택] 마케팅 정보 수신 동의
              </label>
            </>
          )}
          {notice && (
            <p role="status" className="form-note">
              {notice}
            </p>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <Btn className="primary full" disabled={busy}>
            {busy
              ? "처리 중…"
              : mode === "login"
                ? "로그인"
                : mode === "signup"
                  ? "회원가입"
                  : "비밀번호 변경"}
          </Btn>
        </fieldset>
      </form>
      {isSubjectPickerOpen && (
        <SubjectPicker
          subjects={subjects}
          selectedIds={selectedSubjectIds}
          onChange={setSelectedSubjectIds}
          onClose={() => setIsSubjectPickerOpen(false)}
          maxSelections={role === "instructor" ? 3 : 9}
        />
      )}
        <div className="auth-links">
          {mode !== "login" && (
            <button onClick={() => switchMode("login")}>
              로그인으로 돌아가기
            </button>
          )}
          {mode === "reset" && (
            <span className="auth-link-divider" aria-hidden="true" />
          )}
          {mode !== "signup" && (
            <button onClick={() => switchMode("signup")}>회원가입</button>
          )}
          {mode === "login" && (
            <>
              <span className="auth-link-divider" aria-hidden="true" />
              <button onClick={() => switchMode("reset")}>비밀번호 찾기</button>
            </>
          )}
        </div>
      </div>
      </div>
      </section>
    </main>
  );
}
