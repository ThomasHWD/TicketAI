/** Couleur HSL dérivée du nom/email pour que chaque utilisateur ait une teinte stable. */
function hueFromString(s: string): number {
  let hash = 0;
  for (let i = 0; i < s.length; i++) hash = s.charCodeAt(i) + ((hash << 5) - hash);
  return Math.abs(hash) % 360;
}

interface UserAvatarProps {
  name: string;
  /** URL d'une photo personnalisée ; si absente, on affiche le SVG généré. */
  src?: string | null;
  /** Taille en px (côté du carré, le SVG est circulaire). Défaut : 36. */
  size?: number;
  className?: string;
}

export default function UserAvatar({ name, src, size = 36, className = "" }: UserAvatarProps) {
  const initial = name.trim()[0]?.toUpperCase() ?? "?";
  const hue = hueFromString(name);

  const bg   = `hsl(${hue} 55% 88%)`;
  const fg   = `hsl(${hue} 45% 32%)`;
  const ring = `hsl(${hue} 40% 78%)`;

  if (src) {
    return (
      <img
        src={src}
        alt={name}
        width={size}
        height={size}
        className={`rounded-full object-cover ring-2 ring-white/60 dark:ring-white/10 ${className}`}
        style={{ width: size, height: size }}
      />
    );
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 36 36"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label={name}
      role="img"
      className={`shrink-0 rounded-full ${className}`}
      style={{ width: size, height: size }}
    >
      {/* Fond coloré */}
      <circle cx="18" cy="18" r="18" fill={bg} />

      {/* Silhouette subtile */}
      <circle cx="18" cy="14.5" r="5.5" fill={fg} fillOpacity="0.18" />
      <ellipse cx="18" cy="27" rx="10" ry="6.5" fill={fg} fillOpacity="0.14" />

      {/* Initiale */}
      <text
        x="18"
        y="22.5"
        textAnchor="middle"
        fontSize="14"
        fontFamily="system-ui, -apple-system, sans-serif"
        fontWeight="600"
        fill={fg}
        letterSpacing="0.01em"
      >
        {initial}
      </text>

      {/* Anneau */}
      <circle cx="18" cy="18" r="17.25" stroke={ring} strokeWidth="1.5" />
    </svg>
  );
}
