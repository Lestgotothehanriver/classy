import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, QrCode, X } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import {
  appDownloadQrUrl,
  appStoreUrl,
  playStoreUrl,
} from "./app_download";
import "./landing.css";

/** Landing-page navigation targets in visual order. */
const landingSections = [
  { id: "class-preview", label: "강의와 과외" },
  { id: "lecture-upload", label: "수업 미리보기" },
  { id: "consultation", label: "무료 상담" },
  { id: "verification", label: "학력 인증" },
];

/**
 * CLASSY's public product introduction page.
 *
 * The authenticated application remains at /home and the legacy #home route.
 * This page intentionally makes no authenticated API calls.
 */
export function LandingPage() {
  const [activeSection, setActiveSection] = useState("hero");
  const [isQrDialogOpen, setIsQrDialogOpen] = useState(false);

  useEffect(() => {
    const targets = ["hero", ...landingSections.map(({ id }) => id)]
      .map((id) => document.getElementById(id))
      .filter(Boolean);
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort(
            (first, second) =>
              second.intersectionRatio - first.intersectionRatio,
          )[0];
        if (visible) setActiveSection(visible.target.id);
      },
      { rootMargin: "-35% 0px -45% 0px", threshold: [0.01, 0.3] },
    );

    targets.forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, []);

  return (
    <div className="landing-page">
      <a className="skip" href="#landing-main">
        본문으로 이동
      </a>
      <header className="site-header landing-header">
        <div className="header-inner">
          <a href="/home" className="brand" aria-label="CLASSY 홈으로 이동">
            <img src="/app-icons/logo.svg" alt="" />
            <span>CLASSY</span>
          </a>
        </div>
      </header>

      <main id="landing-main">
        <section
          id="hero"
          className="landing-hero"
          aria-labelledby="landing-title"
        >
          <div className="landing-container landing-hero-inner">
            <div className="landing-hero-copy">
              <h1 id="landing-title">
                클래씨에서는 강의와 과외를
                <br />
                {" "}동시에 만나 볼 수 있어요.
              </h1>
              <p>강의를 듣고, 마음에 드는 선생님과 상담해 보세요.</p>
              <a className="landing-web-cta" href="/home">
                웹에서 바로 만나보기
                <ArrowUpRight size={22} aria-hidden="true" />
              </a>
              <div className="landing-downloads" aria-label="클래씨 앱 다운로드">
                <a
                  href={playStoreUrl}
                  target="_blank"
                  rel="noreferrer"
                  aria-label="Google Play에서 클래씨 다운로드"
                >
                  <img src="/app-icons/google-play-badge.png" alt="" />
                </a>
                <a
                  href={appStoreUrl}
                  target="_blank"
                  rel="noreferrer"
                  aria-label="App Store에서 클래씨 다운로드"
                >
                  <img src="/app-icons/app-store-badge.png" alt="" />
                </a>
                <button
                  type="button"
                  className="app-download-qr-button"
                  onClick={() => setIsQrDialogOpen(true)}
                  aria-label="QR 코드로 클래씨 앱 다운로드"
                >
                  <QrCode size={18} aria-hidden="true" />
                  QR로 다운로드
                </button>
              </div>
            </div>
            <div className="landing-hero-symbol" aria-hidden="true">
              <img src="/app-icons/logo.svg" alt="" />
            </div>
          </div>
        </section>

        <section
          id="class-preview"
          className="landing-section landing-section-tint"
          aria-labelledby="class-preview-title"
        >
          <div className="landing-container landing-section-inner">
            <div className="landing-section-copy">
              <h2 id="class-preview-title">
                강의와 과외를 한 곳에서
              </h2>
              <p>강의를 보고, 마음에 드는 선생님에게 과외를 문의해보세요.</p>
            </div>
            <img
              className="landing-feature-art"
              src="/landing/lecture-preview-illustration.webp"
              alt="강의 미리보기를 나타내는 영상 플레이어 일러스트"
              width="1536"
              height="1024"
              loading="lazy"
              decoding="async"
            />
          </div>
        </section>

        <section
          id="lecture-upload"
          className="landing-section"
          aria-labelledby="lecture-upload-title"
        >
          <div className="landing-container landing-section-inner">
            <div className="landing-section-copy">
              <h2 id="lecture-upload-title">
                이제 검증 없는 과외 선택은 그만
              </h2>
              <p>온라인으로 선생님의 수업을 먼저 확인할 수 있어요.</p>
            </div>
            <img
              className="landing-feature-art"
              src="/landing/lecture-upload-illustration.webp"
              alt="강의 업로드를 나타내는 클라우드 일러스트"
              width="1312"
              height="1199"
              loading="lazy"
              decoding="async"
            />
          </div>
        </section>

        <section
          id="consultation"
          className="landing-section landing-section-tint"
          aria-labelledby="consultation-title"
        >
          <div className="landing-container landing-section-inner">
            <div className="landing-section-copy">
              <h2 id="consultation-title">
                비용 걱정 없는 무제한 상담
              </h2>
              <p>마음에 드는 학생/선생님에게 무제한으로 문의할 수 있어요.</p>
            </div>
            <img
              className="landing-feature-art"
              src="/landing/consultation-illustration.webp"
              alt="무료 상담을 나타내는 말풍선 일러스트"
              width="1536"
              height="1024"
              loading="lazy"
              decoding="async"
            />
          </div>
        </section>

        <section
          id="verification"
          className="landing-section"
          aria-labelledby="verification-title"
        >
          <div className="landing-container landing-section-inner">
            <div className="landing-section-copy">
              <h2 id="verification-title">
                안전한 과외를 위한 노력
              </h2>
              <p>클래씨는 신원 및 학력 인증을 통해 신뢰할 수 있는 과외 서비스를 제공해요.</p>
            </div>
            <img
              className="landing-feature-art"
              src="/landing/verification-illustration.webp"
              alt="학력 인증을 나타내는 방패와 인증서 일러스트"
              width="1536"
              height="1024"
              loading="lazy"
              decoding="async"
            />
          </div>
        </section>
      </main>

      <nav className="landing-page-indicator" aria-label="랜딩 섹션 바로가기">
        <a
          href="#hero"
          className={activeSection === "hero" ? "active" : ""}
          aria-label="첫 화면"
          aria-current={activeSection === "hero" ? "location" : undefined}
        />
        {landingSections.map(({ id, label }) => (
          <a
            key={id}
            href={`#${id}`}
            className={activeSection === id ? "active" : ""}
            aria-label={label}
            aria-current={activeSection === id ? "location" : undefined}
          />
        ))}
      </nav>

      <footer className="site-footer landing-footer">
        <div className="footer-identity">
          <span className="footer-brand">CLASSY</span>
        </div>
        <div className="footer-details">
          <nav aria-label="서비스 안내">
            <a href="/service-terms">이용약관</a>
            <a href="/privacy">개인정보처리방침</a>
            <a href="/home#notices">공지사항</a>
            <a href="/home#support">고객센터</a>
          </nav>
          <address className="footer-company-info">
            <span>주식회사 클래씨</span>
            <span>대표이사 우해강</span>
            <span>사업자등록번호 471-86-03936</span>
            <span>통신판매업 신고번호 2026-경기양주-1974</span>
            <span>주소 경기도 양주시 옥정동로7다길 74, 6층 6116호 (옥정동)</span>
            <span>대표 전화번호 010-8259-5284</span>
            <span>
              문의 <a href="mailto:classycompany@classystudy.com">classycompany@classystudy.com</a>
            </span>
          </address>
        </div>
        <small>© {new Date().getFullYear()} CLASSY</small>
      </footer>
      {isQrDialogOpen && (
        <LandingDownloadDialog onClose={() => setIsQrDialogOpen(false)} />
      )}
    </div>
  );
}

/** App-download QR dialog, matching the existing Home download interaction. */
function LandingDownloadDialog({ onClose }) {
  const dialogRef = useRef(null);

  useEffect(() => {
    dialogRef.current?.showModal();
    return () => dialogRef.current?.close();
  }, []);

  return (
    <dialog
      ref={dialogRef}
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === dialogRef.current) onClose();
      }}
    >
      <div className="modal-head">
        <h2>클래씨 앱 다운로드</h2>
        <button className="icon-button" aria-label="닫기" onClick={onClose}>
          <X />
        </button>
      </div>
      <div className="app-download-qr-dialog">
        <QRCodeSVG
          value={appDownloadQrUrl}
          size={208}
          level="M"
          includeMargin
          aria-label="클래씨 앱 다운로드 QR 코드"
        />
        <p>QR 코드를 스캔해주세요</p>
        <button className="btn primary app-download-qr-confirm" onClick={onClose}>
          확인
        </button>
      </div>
    </dialog>
  );
}
