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
  { id: "class-preview", label: "강의 미리보기" },
  { id: "lecture-upload", label: "강의 업로드" },
  { id: "fees", label: "수수료" },
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
                강의를 먼저 시청하고,
                <br />
                선생님을 구해보세요.
              </h2>
              <p>시범 과외보다 빠르게 온라인으로 선생님의 수업 스타일을 강의로 먼저 확인해요.</p>
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
                나만의 강의로 선생님의
                <br />
                실력을 보여주세요.
              </h2>
              <p>직접 만든 강의를 올리고, 원하는 가격으로 강의를 판매할 수 있어요.</p>
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
          id="fees"
          className="landing-section landing-section-fee"
          aria-labelledby="fees-title"
        >
          <div className="landing-container landing-section-inner">
            <div className="landing-section-copy">
              <h2 id="fees-title">
                수수료 부담은 Down
                <br />
                수업 집중력은 Up!
              </h2>
              <p>클래씨에서는 과외 수수료로 인한 선생님의 부담을 낮추려 노력하고 있어요.</p>
              <div className="landing-fee-cards" aria-label="과외 성사 수수료">
                <article>
                  <span>단기 수업 (1개월 미만)</span>
                  <strong>7%</strong>
                </article>
                <article>
                  <span>정규 수업 (1개월 이상)</span>
                  <strong>15%</strong>
                </article>
              </div>
            </div>
            <img
              className="landing-feature-art"
              src="/landing/fee-illustration.webp"
              alt="낮은 수수료를 나타내는 저울과 화살표 일러스트"
              width="1536"
              height="1024"
              loading="lazy"
              decoding="async"
            />
          </div>
        </section>

        <section
          id="consultation"
          className="landing-section"
          aria-labelledby="consultation-title"
        >
          <div className="landing-container landing-section-inner">
            <div className="landing-section-copy">
              <h2 id="consultation-title">
                궁금한 건 편하게,
                <br />
                상담은 무료로 할 수 있어요.
              </h2>
              <p>선생님과 학생이 직접 대화하며 나에게 맞는 수업을 찾아요.</p>
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
          className="landing-section landing-section-tint"
          aria-labelledby="verification-title"
        >
          <div className="landing-container landing-section-inner">
            <div className="landing-section-copy">
              <h2 id="verification-title">
                확인된 학력,
                <br />
                더 믿음직한 선택.
              </h2>
              <p>학력 인증 정보를 확인하고 안심하고 수업을 시작해요.</p>
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
