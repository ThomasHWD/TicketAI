import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import TicketAIMark from "../../assets/ticketai_mark_v2.svg";
import LoginForm from "./LoginForm";

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

const TICKET_EXAMPLES = [
  {
    domain: "RH",
    color: "#2FE272",
    bg: "rgba(47,226,114,.15)",
    text: "Quels sont les délais légaux pour valider un arrêt de travail ?",
  },
  {
    domain: "Comptabilité",
    color: "#60a5fa",
    bg: "rgba(96,165,250,.15)",
    text: "Quelle est la procédure de remboursement des frais de déplacement ?",
  },
  {
    domain: "Juridique",
    color: "#fb923c",
    bg: "rgba(251,146,60,.15)",
    text: "Quelles pièces sont requises pour une demande d'allocation ?",
  },
];

function TicketAnimation() {
  const [idx, setIdx] = useState(0);
  const [charIdx, setCharIdx] = useState(0);
  const [phase, setPhase] = useState<"typing" | "hold" | "erasing">("typing");
  const [cursor, setCursor] = useState(true);

  const ticket = TICKET_EXAMPLES[idx];
  const displayText = ticket.text.slice(0, charIdx);
  const showSend = charIdx === ticket.text.length && phase !== "erasing";

  useEffect(() => {
    let t: ReturnType<typeof setTimeout>;
    if (phase === "typing") {
      if (charIdx < ticket.text.length) {
        t = setTimeout(() => setCharIdx((c) => c + 1), 42 + Math.random() * 28);
      } else {
        t = setTimeout(() => setPhase("hold"), 1800);
      }
    } else if (phase === "hold") {
      t = setTimeout(() => setPhase("erasing"), 500);
    } else {
      if (charIdx > 0) {
        t = setTimeout(() => setCharIdx((c) => c - 1), 18);
      } else {
        setIdx((i) => (i + 1) % TICKET_EXAMPLES.length);
        setPhase("typing");
      }
    }
    return () => clearTimeout(t);
  }, [phase, charIdx, ticket.text.length]);

  useEffect(() => {
    const t = setInterval(() => setCursor((v) => !v), 530);
    return () => clearInterval(t);
  }, []);

  return (
    <div
      className="tk-illus-float"
      style={{ animation: "tk-float 4.2s ease-in-out infinite", width: 320 }}
    >
      <div
        style={{
          background: "rgba(5,20,14,.9)",
          border: `1px solid ${ticket.color}2e`,
          borderRadius: 16,
          padding: "22px 22px 18px",
          boxShadow: `0 0 56px -12px ${ticket.color}1a, 0 24px 48px -16px rgba(0,0,0,.65)`,
          backdropFilter: "blur(12px)",
          transition: "border-color .8s ease, box-shadow .8s ease",
        }}
      >
        {/* Header row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 18,
          }}
        >
          <span
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: "rgba(234,255,242,.7)",
              letterSpacing: "-.01em",
            }}
          >
            Nouvelle question
          </span>
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              padding: "3px 10px",
              borderRadius: 20,
              background: ticket.bg,
              color: ticket.color,
              transition: "background .8s ease, color .8s ease",
              letterSpacing: ".01em",
            }}
          >
            {ticket.domain}
          </span>
        </div>

        {/* Question text area */}
        <div
          style={{
            background: "rgba(255,255,255,.03)",
            border: "1px solid rgba(127,224,166,.1)",
            borderRadius: 10,
            padding: "13px 14px",
            minHeight: 88,
            fontSize: 13.5,
            color: "#eafff2",
            lineHeight: 1.6,
            letterSpacing: "-.005em",
          }}
        >
          {displayText.length === 0 ? (
            <span style={{ color: "rgba(127,185,155,.28)" }}>
              Décrivez votre demande…
            </span>
          ) : (
            <>
              {displayText}
              <span
                style={{
                  opacity: cursor ? 1 : 0,
                  color: ticket.color,
                  fontWeight: 300,
                  transition: "opacity .06s",
                }}
              >
                |
              </span>
            </>
          )}
        </div>

        {/* Footer: progress pips + send button */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 5,
            marginTop: 14,
          }}
        >
          {TICKET_EXAMPLES.map((_, i) => (
            <div
              key={i}
              style={{
                height: 5,
                width: i === idx ? 20 : 5,
                borderRadius: 3,
                background: i === idx ? ticket.color : "rgba(127,224,166,.18)",
                transition: "all .5s cubic-bezier(.16,1,.3,1)",
              }}
            />
          ))}
          <div style={{ flex: 1 }} />
          <div
            style={{
              padding: "6px 16px",
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: ".01em",
              background: showSend
                ? "linear-gradient(100deg,#168B46,#2FE272)"
                : "rgba(127,224,166,.08)",
              color: showSend ? "#06140d" : "rgba(127,185,155,.28)",
              boxShadow: showSend ? "0 4px 14px -4px rgba(47,226,114,.5)" : "none",
              transition: "all .4s cubic-bezier(.16,1,.3,1)",
              cursor: "default",
              userSelect: "none" as const,
            }}
          >
            Envoyer
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Login() {
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
          width: 100%;
          padding: 13px 15px;
          border-radius: 11px;
          border: 1px solid rgba(127,224,166,.18);
          background: rgba(255,255,255,.03);
          color: #eafff2;
          font-family: 'Geist Variable', sans-serif;
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
          font-family: 'Geist Variable', sans-serif;
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
        {/* ── Left brand panel (md+) ── */}
        <div
          style={{
            position: "relative", flex: "1 1 46%", minWidth: 0,
            display: "flex", flexDirection: "column", justifyContent: "space-between",
            padding: "48px 52px",
            background: "#081912",
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
          <div
            aria-hidden="true"
            style={{
              position: "absolute", inset: 0,
              background: "radial-gradient(70% 55% at 30% 40%,rgba(47,226,114,.14) 0%,transparent 70%)",
              pointerEvents: "none",
            }}
          />

          {/* Logo */}
          <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 12 }}>
            <img src={TicketAIMark} alt="ONaCVG" style={{ width: 34, height: 34 }} />
            <span style={{ fontWeight: 700, fontSize: 19, letterSpacing: "-.01em", color: "#eafff2" }}>
              ONaCVG
            </span>
          </div>

          {/* Ticket animation + tagline */}
          <div
            style={{
              position: "relative", display: "flex", flexDirection: "column",
              alignItems: "center", gap: 32, padding: "20px 0",
            }}
          >
            <TicketAnimation />
            <div style={{ textAlign: "center", maxWidth: 300 }}>
              <div
                style={{
                  fontSize: 22, fontWeight: 600, lineHeight: 1.3,
                  color: "#eafff2", letterSpacing: "-.01em",
                }}
              >
                Toutes vos demandes, une réponse juste et rapide.
              </div>
            </div>
          </div>

          {/* Footer */}
          <div style={{ position: "relative", display: "flex", gap: 24, fontSize: 12.5, color: "#5fb886" }}>
            <span>© 2026 ONaCVG</span>
            <span>Confidentialité</span>
            <span>Sécurité</span>
          </div>
        </div>

        {/* ── Right form panel ── */}
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
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 32 }} className="md:hidden">
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
