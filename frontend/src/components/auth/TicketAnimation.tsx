import { useState, useEffect } from "react";

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

export function TicketAnimation() {
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
    <div className="tk-illus-float" style={{ animation: "tk-float 4.2s ease-in-out infinite", width: 320 }}>
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
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: "rgba(234,255,242,.7)", letterSpacing: "-.01em" }}>
            Nouvelle question
          </span>
          <span
            style={{
              fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 20,
              background: ticket.bg, color: ticket.color,
              transition: "background .8s ease, color .8s ease", letterSpacing: ".01em",
            }}
          >
            {ticket.domain}
          </span>
        </div>

        {/* Question textarea */}
        <div
          style={{
            background: "rgba(255,255,255,.03)", border: "1px solid rgba(127,224,166,.1)",
            borderRadius: 10, padding: "13px 14px", minHeight: 88,
            fontSize: 13.5, color: "#eafff2", lineHeight: 1.6, letterSpacing: "-.005em",
          }}
        >
          {displayText.length === 0 ? (
            <span style={{ color: "rgba(127,185,155,.28)" }}>Décrivez votre demande…</span>
          ) : (
            <>
              {displayText}
              <span style={{ opacity: cursor ? 1 : 0, color: ticket.color, fontWeight: 300, transition: "opacity .06s" }}>|</span>
            </>
          )}
        </div>

        {/* Footer: progress pips + send button */}
        <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 14 }}>
          {TICKET_EXAMPLES.map((_, i) => (
            <div
              key={i}
              style={{
                height: 5, width: i === idx ? 20 : 5, borderRadius: 3,
                background: i === idx ? ticket.color : "rgba(127,224,166,.18)",
                transition: "all .5s cubic-bezier(.16,1,.3,1)",
              }}
            />
          ))}
          <div style={{ flex: 1 }} />
          <div
            style={{
              padding: "6px 16px", borderRadius: 8, fontSize: 12, fontWeight: 700,
              letterSpacing: ".01em",
              background: showSend ? "linear-gradient(100deg,#168B46,#2FE272)" : "rgba(127,224,166,.08)",
              color: showSend ? "#06140d" : "rgba(127,185,155,.28)",
              boxShadow: showSend ? "0 4px 14px -4px rgba(47,226,114,.5)" : "none",
              transition: "all .4s cubic-bezier(.16,1,.3,1)",
              cursor: "default", userSelect: "none" as const,
            }}
          >
            Envoyer
          </div>
        </div>
      </div>
    </div>
  );
}
