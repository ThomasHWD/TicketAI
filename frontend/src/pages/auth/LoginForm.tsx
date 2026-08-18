import { useState } from "react";
import { Loader2 } from "lucide-react";

interface LoginFormTheme {
  sub: string;
  inputCls: string;
}

interface LoginFormProps {
  onLogin: (username: string, password: string) => Promise<void>;
  theme: LoginFormTheme;
}

export default function LoginForm({ onLogin, theme }: LoginFormProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await onLogin(username.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de la connexion.");
    } finally {
      setLoading(false);
    }
  }

  return (
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
  );
}
