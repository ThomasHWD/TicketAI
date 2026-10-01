import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { useDark } from "../../hooks/useDark";
import TicketAIMark from "../../assets/ticketai_mark_v2.svg";
import { BrandPanel } from "../../components/auth/BrandPanel";
import LoginForm from "./LoginForm";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";

export default function Login() {
  useDocumentTitle("Connexion");
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const dark = useDark();

  const theme = dark
    ? { bg: "#101f18", text: "#eafff2", sub: "#7fb99b", border: "rgba(127,224,166,.18)", field: "rgba(255,255,255,.03)", inputCls: "tk-login-input" }
    : { bg: "#F8FAFC", text: "#112F21", sub: "#5a7166", border: "rgba(17,47,33,.14)", field: "#ffffff", inputCls: "tk-login-input tk-login-input-light" };

  const from = (location.state as { from?: string } | null)?.from ?? "/";

  async function handleLogin(username: string, password: string) {
    await login(username, password);
    navigate(from, { replace: true });
  }

  return (
    <>
      <style>{`
        @keyframes tk-float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-7px)} }
        @keyframes tk-rise  { 0%{opacity:0;transform:translateY(16px)} 100%{opacity:1;transform:translateY(0)} }
        @keyframes tk-grid  { 0%{background-position:0 0} 100%{background-position:44px 44px} }
        @keyframes spin     { to{transform:rotate(360deg)} }

        .tk-login-input {
          width: 100%; padding: 13px 15px; border-radius: 11px;
          border: 1px solid rgba(127,224,166,.18); background: rgba(255,255,255,.03);
          color: #eafff2; font-family: 'Geist Variable', sans-serif; font-size: 14.5px;
          outline: none; transition: border-color .15s, box-shadow .15s; box-sizing: border-box;
        }
        .tk-login-input::placeholder { color: rgba(127,185,155,.4); }
        .tk-login-input:focus { border-color: #2FE272; box-shadow: 0 0 0 3px rgba(47,226,114,.18); }
        .tk-login-input-pw { padding-right: 44px; }
        .tk-login-input-light { border-color: rgba(17,47,33,.14); background: #ffffff; color: #112F21; }
        .tk-login-input-light::placeholder { color: rgba(90,113,102,.5); }

        .tk-submit-btn {
          width: 100%; padding: 14px; border-radius: 11px; border: none;
          background: linear-gradient(100deg, #168B46, #2FE272); color: #06140d;
          font-family: 'Geist Variable', sans-serif; font-size: 15px; font-weight: 700;
          letter-spacing: .01em; cursor: pointer; box-shadow: 0 8px 24px -8px rgba(47,226,114,.6);
          transition: box-shadow .2s, transform .15s;
          display: flex; align-items: center; justify-content: center; gap: 8px;
        }
        .tk-submit-btn:hover:not(:disabled) { box-shadow: 0 10px 30px -6px rgba(47,226,114,.75); transform: translateY(-1px); }
        .tk-submit-btn:disabled { opacity: .6; cursor: not-allowed; transform: none; }

        .tk-pw-toggle {
          position: absolute; right: 4px; top: 50%; transform: translateY(-50%);
          width: 40px; height: 40px; border-radius: 8px; display: flex; align-items: center; justify-content: center;
          border: none; background: transparent; color: var(--tk-sub); cursor: pointer; padding: 0;
          transition: color .15s;
        }
        .tk-pw-toggle:hover { color: var(--tk-text); }
        .tk-pw-toggle:focus-visible { outline: 2px solid #2FE272; outline-offset: 1px; color: var(--tk-text); }

        @media (prefers-reduced-motion: reduce) {
          .tk-illus-float, .tk-grid-bg { animation: none !important; }
        }
      `}</style>

      <div
        style={{
          position: "fixed", inset: 0, display: "flex",
          fontFamily: "'Geist Variable', sans-serif",
          overflow: "auto",
          "--tk-text": theme.text,
          "--tk-sub": theme.sub,
        } as React.CSSProperties}
      >
        <BrandPanel />

        {/* Right form panel */}
        <div
          style={{
            flex: "1 1 54%", minWidth: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: "40px 28px",
            background: theme.bg,
            transition: "background .2s",
          }}
        >
          <div style={{ width: "100%", maxWidth: 392, animation: "tk-rise .7s ease-out both" }}>
            {/* Mobile-only logo */}
            <div style={{ alignItems: "center", gap: 12, marginBottom: 32 }} className="flex md:hidden">
              <img src={TicketAIMark} alt="ONaCVG" style={{ width: 32, height: 32 }} />
              <span style={{ fontWeight: 700, fontSize: 18, color: theme.text, letterSpacing: "-.01em" }}>ONaCVG</span>
            </div>

            <div style={{ marginBottom: 32 }}>
              <h1 style={{ margin: 0, fontSize: 30, fontWeight: 700, letterSpacing: "-.02em", color: theme.text }}>
                Accès à votre compte
              </h1>
              <p style={{ margin: "10px 0 0", fontSize: 15, color: theme.sub }}>
                Connectez-vous pour gérer vos tickets.
              </p>
            </div>

            <LoginForm onLogin={handleLogin} theme={theme} />
          </div>
        </div>
      </div>
    </>
  );
}
