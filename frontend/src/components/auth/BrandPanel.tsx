import TicketAIMark from "../../assets/ticketai_mark_v2.svg";
import { TicketAnimation } from "./TicketAnimation";

export function BrandPanel() {
  return (
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

      {/* Animation + tagline */}
      <div style={{ position: "relative", display: "flex", flexDirection: "column", alignItems: "center", gap: 32, padding: "20px 0" }}>
        <TicketAnimation />
        <div style={{ textAlign: "center", maxWidth: 300 }}>
          <div style={{ fontSize: 22, fontWeight: 600, lineHeight: 1.3, color: "#eafff2", letterSpacing: "-.01em" }}>
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
  );
}
