import React, { useContext, useState } from "react";
import { api } from "./api";
import { AcademicFields, Ctx, Btn, Modal, RegionFields } from "./shared";

// Mirrors SignupAccountView, SignupVerifyPhoneView and the role-specific surveys.
export function Auth({ onClose, initial = "login" }) {
  const { setUser, setRole, subjects, notify } = useContext(Ctx);
  const [mode, setMode] = useState(initial),
    [role, roleSet] = useState("student");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [phone, setPhone] = useState(""),
    [code, setCode] = useState("");
  const [sent, setSent] = useState(false),
    [verified, setVerified] = useState(false);
  const [resetToken, setResetToken] = useState("");
  const [notice, setNotice] = useState("");
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
    setMode(next);
    setError("");
    setNotice("");
    setSent(false);
    setVerified(false);
    setResetToken("");
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
      onClose();
      notify("CLASSY에 오신 것을 환영해요.");
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
        switchMode("login");
        setNotice("비밀번호를 변경했습니다. 새 비밀번호로 로그인해 주세요.");
        return;
      }
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
      const selected = f.getAll("subjects").map(Number);
      const body = {
        email,
        password: values.password,
        user_name: values.user_name.trim(),
        phone,
        region: values.region,
        sex: values.sex,
        birth_date: values.birth_date,
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
    <Modal
      title={
        mode === "login"
          ? "Classy에 로그인"
          : mode === "reset"
            ? "비밀번호 찾기"
            : "CLASSY 회원가입"
      }
      onClose={onClose}
    >
      <div className="login-intro">
        <img src="/app-icons/logo.svg" alt="" />
        <h3>
          {mode === "login"
            ? "다시 만나서 반가워요!"
            : mode === "signup"
              ? "배움의 시작을 함께해요"
              : "계정을 안전하게 되찾으세요"}
        </h3>
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
              이메일
              <input
                name="email"
                type="email"
                autoComplete="username"
                required
              />
            </label>
          )}
          {mode !== "login" && (
            <>
              <label>
                휴대전화 번호
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => {
                    setPhone(e.target.value.replace(/\D/g, ""));
                    setVerified(false);
                    setSent(false);
                    setResetToken("");
                  }}
                  autoComplete="tel"
                  required
                  placeholder="01012345678"
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
            {mode === "reset" ? "새 비밀번호" : "비밀번호"}
            <input
              name="password"
              type="password"
              required
              minLength={mode === "login" ? 1 : 8}
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
            />
          </label>
          {mode !== "login" && (
            <label>
              비밀번호 확인
              <input
                name="confirm"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
              />
            </label>
          )}
          {mode === "signup" && (
            <>
              <label>
                닉네임
                <input name="user_name" required maxLength={30} />
              </label>
              <div className="form-columns">
                <label>
                  생년월일
                  <input
                    name="birth_date"
                    type="date"
                    required
                    max={new Date().toISOString().slice(0, 10)}
                  />
                </label>
                <label>
                  성별
                  <select name="sex">
                    <option value="">선택 안 함</option>
                    <option>남성</option>
                    <option>여성</option>
                  </select>
                </label>
              </div>
              <RegionFields required />
              <label>
                관심 과목
                <select name="subjects" multiple size={5}>
                  {subjects.map((s) => (
                    <option key={s.number} value={s.number}>
                      {s.name}
                    </option>
                  ))}
                </select>
                <small>여러 과목은 Ctrl 또는 ⌘ 키로 선택하세요.</small>
              </label>
              {role === "instructor" && (
                <>
                  <AcademicFields />
                  <label>
                    선생님 소개
                    <textarea name="instruction" rows={3} />
                  </label>
                  <p className="form-note">
                    가입 후 마이페이지에서 학력 인증 서류를 제출할 수 있습니다.
                  </p>
                </>
              )}
              <label className="check-label">
                <input type="checkbox" required />
                [필수]{" "}
                <a href="/service-terms" target="_blank" rel="noreferrer">
                  이용약관
                </a>{" "}
                동의
              </label>
              <label className="check-label">
                <input type="checkbox" required />
                [필수]{" "}
                <a href="/privacy" target="_blank" rel="noreferrer">
                  개인정보처리방침
                </a>{" "}
                동의
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
      <div className="auth-links">
        {mode !== "login" && (
          <button onClick={() => switchMode("login")}>
            로그인으로 돌아가기
          </button>
        )}
        {mode !== "signup" && (
          <button onClick={() => switchMode("signup")}>회원가입</button>
        )}
        {mode === "login" && (
          <button onClick={() => switchMode("reset")}>비밀번호 찾기</button>
        )}
      </div>
    </Modal>
  );
}
