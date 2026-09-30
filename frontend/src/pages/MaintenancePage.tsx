import { Wrench } from "lucide-react";
import { useDark } from "../hooks/useDark";
import TicketAIMark from "../assets/ticketai_mark_v2.svg";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

interface Props {
  message?: string;
}

export default function MaintenancePage({ message }: Props) {
  useDocumentTitle("Maintenance en cours");
  const dark = useDark();

  const bg    = dark ? "#0d0d0d" : "#F8FAFC";
  const card  = dark ? "rgba(255,255,255,0.04)" : "#ffffff";
  const border= dark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.07)";
  const title = dark ? "#f0fdf4" : "#111827";
  const sub   = dark ? "#6b7280" : "#6b7280";
  const logo  = dark ? "#eafff2" : "#111827";

  return (
    <>
      <style>{`
        @keyframes tk-grid  { 0%{background-position:0 0} 100%{background-position:44px 44px} }
        @keyframes tk-rise  { 0%{opacity:0;transform:translateY(14px)} 100%{opacity:1;transform:translateY(0)} }
        @keyframes tk-pulse-dot { 0%,100%{opacity:.35} 50%{opacity:1} }
        @media (prefers-reduced-motion: reduce) {
          .tk-maint-grid, .tk-maint-card { animation: none !important; }
        }
      `}</style>

      <div
        style={{
          position: "fixed", inset: 0,
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          background: bg,
          fontFamily: "'Geist Variable', sans-serif",
          padding: "24px",
          overflow: "hidden",
        }}
      >
        {/* Animated grid */}
        <div
          aria-hidden="true"
          className="tk-maint-grid"
          style={{
            position: "absolute", inset: 0, pointerEvents: "none",
            opacity: dark ? 0.5 : 0.25,
            backgroundImage: "linear-gradient(rgba(47,226,114,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(47,226,114,.07) 1px,transparent 1px)",
            backgroundSize: "44px 44px",
            animation: "tk-grid 14s linear infinite",
          }}
        />

        {/* Radial glow */}
        <div
          aria-hidden="true"
          style={{
            position: "absolute", inset: 0, pointerEvents: "none",
            background: "radial-gradient(55% 45% at 50% 52%,rgba(47,226,114,.10) 0%,transparent 70%)",
          }}
        />

        {/* Card */}
        <div
          className="tk-maint-card"
          style={{
            position: "relative",
            width: "100%", maxWidth: 400,
            background: card,
            border: `1px solid ${border}`,
            borderRadius: 20,
            padding: "36px 32px",
            boxShadow: dark
              ? "0 0 0 1px rgba(255,255,255,.04), 0 24px 48px -12px rgba(0,0,0,.6)"
              : "0 4px 6px -1px rgba(0,0,0,.06), 0 20px 40px -12px rgba(0,0,0,.08)",
            animation: "tk-rise .6s ease-out both",
            display: "flex", flexDirection: "column", alignItems: "center", gap: 0,
          }}
        >
          {/* Logo */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 32, alignSelf: "flex-start" }}>
            <img src={TicketAIMark} alt="" aria-hidden="true" style={{ width: 26, height: 26 }} />
            <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-.01em", color: logo }}>
              ONaCVG
            </span>
          </div>

          {/* Icon */}
          <div
            style={{
              width: 56, height: 56, borderRadius: 16,
              background: "rgba(245,158,11,.12)",
              border: "1px solid rgba(245,158,11,.2)",
              display: "flex", alignItems: "center", justifyContent: "center",
              marginBottom: 20,
            }}
          >
            <Wrench size={24} color="#D97706" aria-hidden="true" />
          </div>

          {/* Title */}
          <h1
            style={{
              margin: 0,
              fontSize: 20, fontWeight: 700, letterSpacing: "-.02em",
              color: title, textAlign: "center", lineHeight: 1.25,
            }}
          >
            Site en maintenance
          </h1>

          {/* Message */}
          <p
            style={{
              margin: "10px 0 0",
              fontSize: 14, lineHeight: 1.6,
              color: sub, textAlign: "center",
            }}
          >
            {message || "Nous effectuons des opérations de maintenance. Le service sera bientôt disponible."}
          </p>

          {/* Checking indicator */}
          <div
            style={{
              marginTop: 28,
              display: "flex", alignItems: "center", gap: 7,
              fontSize: 12, color: sub,
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: 6, height: 6, borderRadius: "50%",
                background: "#2FE272",
                animation: "tk-pulse-dot 2s ease-in-out infinite",
                display: "inline-block", flexShrink: 0,
              }}
            />
            Vérification automatique en cours…
          </div>
        </div>
      </div>
    </>
  );
}
