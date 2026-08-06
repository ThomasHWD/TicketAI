import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuth } from "../../lib/auth";
import TicketAIMark from "../../assets/ticketai_mark_v2.svg";

function useDark() {
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark")
  );
  useEffect(() => {
    const obs = new MutationObserver(() =>
      setDark(document.documentElement.classList.contains("dark"))
    );
    obs.observe(document.documentElement, { attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return dark;
}

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const dark = useDark();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);

  const theme = dark
    ? { bg: "#071310", text: "#eafff2", sub: "#7fb99b", border: "rgba(127,224,166,.18)", field: "rgba(255,255,255,.03)", inputCls: "tk-login-input" }
    : { bg: "#F8FAFC", text: "#112F21", sub: "#5a7166", border: "rgba(17,47,33,.14)", field: "#ffffff", inputCls: "tk-login-input tk-login-input-light" };

  const from = (location.state as { from?: string } | null)?.from ?? "/";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de la connexion.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <style>{`
        @keyframes tk-float   { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-7px)} }
        @keyframes tk-antenna { 0%,100%{transform:scale(.6);opacity:0} 15%{opacity:.9} 70%{opacity:0} 100%{transform:scale(2.6);opacity:0} }
        @keyframes tk-tip     { 0%,100%{opacity:.55;filter:drop-shadow(0 0 2px #2FE272)} 50%{opacity:1;filter:drop-shadow(0 0 8px #2FE272)} }
        @keyframes tk-blink   { 0%,42%,48%,92%,100%{transform:scaleY(1)} 45%,90.5%{transform:scaleY(.08)} }
        @keyframes tk-code    { 0%,100%{opacity:.35} 50%{opacity:.85} }
        @keyframes tk-rise    { 0%{opacity:0;transform:translateY(16px)} 100%{opacity:1;transform:translateY(0)} }
        @keyframes tk-grid    { 0%{background-position:0 0} 100%{background-position:44px 44px} }
        @keyframes tk-ticket  { 0%{transform:translateX(-14px);opacity:0} 18%{opacity:1} 82%{opacity:1} 100%{transform:translateX(16px);opacity:0} }
        @keyframes tk-scan    { 0%{transform:translateY(0);opacity:0} 12%{opacity:1} 88%{opacity:1} 100%{transform:translateY(26px);opacity:0} }
        @keyframes spin       { to{transform:rotate(360deg)} }

        .tk-login-input {
          width: 100%;
          padding: 13px 15px;
          border-radius: 11px;
          border: 1px solid rgba(127,224,166,.18);
          background: rgba(255,255,255,.03);
          color: #eafff2;
          font-family: 'Space Grotesk', system-ui, sans-serif;
          font-size: 14.5px;
          outline: none;
          transition: border-color .15s, box-shadow .15s;
          box-sizing: border-box;
        }
        .tk-login-input::placeholder { color: rgba(127,185,155,.4); }
        .tk-login-input:focus {
          border-color: #2FE272;
          box-shadow: 0 0 0 3px rgba(47,226,114,.18);
        }
        .tk-login-input-pw { padding-right: 44px; }

        .tk-login-input-light {
          border-color: rgba(17,47,33,.14);
          background: #ffffff;
          color: #112F21;
        }
        .tk-login-input-light::placeholder { color: rgba(90,113,102,.5); }

        .tk-submit-btn {
          width: 100%;
          padding: 14px;
          border-radius: 11px;
          border: none;
          background: linear-gradient(100deg, #168B46, #2FE272);
          color: #06140d;
          font-family: 'Space Grotesk', system-ui, sans-serif;
          font-size: 15px;
          font-weight: 700;
          letter-spacing: .01em;
          cursor: pointer;
          box-shadow: 0 8px 24px -8px rgba(47,226,114,.6);
          transition: box-shadow .2s, transform .15s;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }
        .tk-submit-btn:hover:not(:disabled) {
          box-shadow: 0 10px 30px -6px rgba(47,226,114,.75);
          transform: translateY(-1px);
        }
        .tk-submit-btn:disabled { opacity: .6; cursor: not-allowed; transform: none; }

        .tk-pw-toggle {
          position: absolute; right: 8px; top: 50%; transform: translateY(-50%);
          width: 30px; height: 30px;
          display: flex; align-items: center; justify-content: center;
          border: none; background: transparent; color: var(--tk-sub); cursor: pointer; padding: 0;
          transition: color .15s;
        }
        .tk-pw-toggle:hover { color: var(--tk-text); }

        @media (prefers-reduced-motion: reduce) {
          .tk-robot-float, .tk-grid-bg { animation: none !important; }
        }
      `}</style>

      <div style={{
        position: "fixed", inset: 0, display: "flex",
        fontFamily: "'Space Grotesk', system-ui, sans-serif",
        overflow: "auto",
        "--tk-text": theme.text,
        "--tk-sub": theme.sub,
      } as React.CSSProperties}>
        {/* ── Left brand panel (md+) ── */}
        <div
          style={{
            position: "relative", flex: "1 1 46%", minWidth: 0,
            display: "flex", flexDirection: "column", justifyContent: "space-between",
            padding: "48px 52px",
            background: "#050f0c",
            overflow: "hidden",
          }}
          className="hidden md:flex"
        >
          {/* Animated grid */}
          <div
            aria-hidden="true"
            className="tk-grid-bg"
            style={{
              position: "absolute", inset: 0, opacity: .5,
              backgroundImage: "linear-gradient(rgba(47,226,114,.06) 1px,transparent 1px),linear-gradient(90deg,rgba(47,226,114,.06) 1px,transparent 1px)",
              backgroundSize: "44px 44px",
              animation: "tk-grid 12s linear infinite",
              pointerEvents: "none",
            }}
          />
          {/* Radial glow */}
          <div aria-hidden="true" style={{
            position: "absolute", inset: 0,
            background: "radial-gradient(70% 55% at 30% 40%,rgba(47,226,114,.14) 0%,transparent 70%)",
            pointerEvents: "none",
          }} />

          {/* Logo */}
          <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 12 }}>
            <img src={TicketAIMark} alt="TicketAI" style={{ width: 34, height: 34 }} />
            <span style={{ fontWeight: 700, fontSize: 19, letterSpacing: "-.01em", color: "#eafff2" }}>
              TicketAI
            </span>
          </div>

          {/* Robot + tagline */}
          <div style={{
            position: "relative", display: "flex", flexDirection: "column",
            alignItems: "center", gap: 30, padding: "20px 0",
          }}>
            <div className="tk-robot-float" style={{ animation: "tk-float 4.2s ease-in-out infinite" }}>
              <svg width="150" height="188" viewBox="0 0 190 238" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ display: "block", overflow: "visible" }}>
                <circle cx="95" cy="20" r="9" fill="none" stroke="#2FE272" strokeWidth="2"
                  style={{ transformBox: "fill-box", transformOrigin: "center", animation: "tk-antenna 2.6s ease-out infinite" }} />
                <circle cx="95" cy="20" r="9" fill="none" stroke="#2FE272" strokeWidth="2"
                  style={{ transformBox: "fill-box", transformOrigin: "center", animation: "tk-antenna 2.6s ease-out infinite", animationDelay: "1.3s" }} />
                <line x1="95" y1="46" x2="95" y2="26" stroke="#0f6c37" strokeWidth="4" strokeLinecap="round" />
                <circle cx="95" cy="20" r="6" fill="#2FE272" style={{ animation: "tk-tip 1.6s ease-in-out infinite" }} />
                <rect x="46" y="44" width="98" height="72" rx="22" fill="#168B46" />
                <g style={{ transformBox: "fill-box", transformOrigin: "center", animation: "tk-blink 5s ease-in-out 1s infinite" }}>
                  <circle cx="77" cy="82" r="11" fill="#0d2417" />
                  <circle cx="77" cy="82" r="7" fill="#2FE272" style={{ filter: "drop-shadow(0 0 6px #2FE272)" }} />
                  <circle cx="80" cy="79" r="2.4" fill="#eafff2" />
                  <circle cx="113" cy="82" r="11" fill="#0d2417" />
                  <circle cx="113" cy="82" r="7" fill="#2FE272" style={{ filter: "drop-shadow(0 0 6px #2FE272)" }} />
                  <circle cx="116" cy="79" r="2.4" fill="#eafff2" />
                </g>
                <rect x="82" y="104" width="26" height="5" rx="2.5" fill="#2FE272" opacity="0.5" />
                <rect x="86" y="116" width="18" height="10" fill="#0f6c37" />
                <rect x="24" y="132" width="16" height="52" rx="8" fill="#0f6c37" />
                <rect x="150" y="132" width="16" height="52" rx="8" fill="#0f6c37" />
                <rect x="40" y="126" width="110" height="86" rx="20" fill="#168B46" />
                <rect x="54" y="140" width="82" height="58" rx="10" fill="#06140d" />
                <rect x="54" y="140" width="82" height="58" rx="10" fill="none" stroke="#2FE272" strokeWidth="1.5" opacity="0.35" />
                <clipPath id="tkLoginScreen"><rect x="54" y="140" width="82" height="58" rx="10" /></clipPath>
                <g clipPath="url(#tkLoginScreen)">
                  <line x1="63" y1="150" x2="98" y2="150" stroke="#2FE272" strokeWidth="2" strokeLinecap="round"
                    style={{ animation: "tk-code 1.8s ease-in-out infinite" }} />
                  <line x1="63" y1="158" x2="118" y2="158" stroke="#2FE272" strokeWidth="2" strokeLinecap="round"
                    style={{ animation: "tk-code 1.8s ease-in-out infinite", animationDelay: ".3s" }} />
                  <line x1="63" y1="166" x2="88" y2="166" stroke="#2FE272" strokeWidth="2" strokeLinecap="round"
                    style={{ animation: "tk-code 1.8s ease-in-out infinite", animationDelay: ".6s" }} />
                  <g style={{ transformBox: "fill-box", transformOrigin: "center", animation: "tk-ticket 2.4s cubic-bezier(.6,0,.3,1) infinite" }}>
                    <rect x="63" y="176" width="18" height="14" rx="3" fill="none" stroke="#2FE272" strokeWidth="2" />
                    <line x1="83" y1="183" x2="108" y2="183" stroke="#2FE272" strokeWidth="2.5" strokeLinecap="round" />
                    <path d="M103 178 L110 183 L103 188" fill="none" stroke="#2FE272" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                  </g>
                  <rect x="54" y="142" width="82" height="16" fill="#2FE272" opacity="0.16"
                    style={{ animation: "tk-scan 2.4s ease-in-out infinite" }} />
                </g>
                <rect x="62" y="212" width="18" height="22" rx="7" fill="#0f6c37" />
                <rect x="110" y="212" width="18" height="22" rx="7" fill="#0f6c37" />
              </svg>
            </div>

            <div style={{ textAlign: "center", maxWidth: 340 }}>
              <div style={{
                fontSize: 26, fontWeight: 600, lineHeight: 1.25,
                color: "#eafff2", letterSpacing: "-.01em",
              }}>
                Vos tickets, résolus par l'intelligence artificielle.
              </div>
              <div style={{
                marginTop: 14,
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 11, letterSpacing: ".34em",
                textTransform: "uppercase", color: "#7fe0a6",
              }}>
                Automatisation Intelligente
              </div>
            </div>
          </div>

          {/* Footer */}
          <div style={{ position: "relative", display: "flex", gap: 24, fontSize: 12.5, color: "#5fb886" }}>
            <span>© 2026 TicketAI</span>
            <span>Confidentialité</span>
            <span>Sécurité</span>
          </div>
        </div>

        {/* ── Right form panel ── */}
        <div style={{
          flex: "1 1 54%", minWidth: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          padding: "40px 28px",
          background: theme.bg,
          transition: "background .2s",
        }}>
          <div style={{ width: "100%", maxWidth: 392, animation: "tk-rise .7s ease-out both" }}>

            {/* Mobile-only logo */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 32 }} className="md:hidden">
              <img src={TicketAIMark} alt="TicketAI" style={{ width: 32, height: 32 }} />
              <span style={{ fontWeight: 700, fontSize: 18, color: theme.text, letterSpacing: "-.01em" }}>TicketAI</span>
            </div>

            <div style={{ marginBottom: 32 }}>
              <h1 style={{ margin: 0, fontSize: 30, fontWeight: 700, letterSpacing: "-.02em", color: theme.text }}>
                Bon retour 👋
              </h1>
              <p style={{ margin: "10px 0 0", fontSize: 15, color: theme.sub }}>
                Connectez-vous pour gérer vos tickets.
              </p>
            </div>

            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>

              {/* Identifiant */}
              <label style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 13, fontWeight: 500, color: theme.sub }}>
                Identifiant
                <input
                  type="text"
                  autoComplete="username"
                  autoFocus
                  required
                  placeholder="prénom.nom"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className={theme.inputCls}
                />
              </label>

              {/* Mot de passe */}
              <label style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 13, fontWeight: 500, color: theme.sub }}>
                <span style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  Mot de passe
                </span>
                <span style={{ position: "relative", display: "block" }}>
                  <input
                    type={showPw ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className={`${theme.inputCls} tk-login-input-pw`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw((v) => !v)}
                    className="tk-pw-toggle"
                    aria-label={showPw ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                  >
                    {showPw ? (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                        <line x1="1" y1="1" x2="23" y2="23" />
                      </svg>
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </button>
                </span>
              </label>

              {/* Rester connecté */}
              <label style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 13.5, color: theme.sub, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  style={{ width: 16, height: 16, accentColor: "#2FE272", cursor: "pointer" }}
                />
                Rester connecté
              </label>

              {/* Erreur */}
              {error && (
                <p role="alert" style={{
                  margin: 0, padding: "10px 14px", borderRadius: 10,
                  background: "rgba(239,68,68,.1)", border: "1px solid rgba(239,68,68,.2)",
                  fontSize: 13.5, color: "#f87171",
                }}>
                  {error}
                </p>
              )}

              {/* Submit */}
              <button type="submit" disabled={loading} className="tk-submit-btn" style={{ marginTop: 4 }}>
                {loading ? (
                  <>
                    <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} aria-hidden="true" />
                    Connexion…
                  </>
                ) : (
                  "Se connecter"
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
    </>
  );
}
