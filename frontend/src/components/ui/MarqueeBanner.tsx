import { useRef, useEffect, useState } from "react";
import { Megaphone } from "lucide-react";

interface MarqueeBannerProps {
  message: string;
  url?: string;
}

interface MarqueeMetrics {
  duration: number;
  from: string;
  to: string;
}

export default function MarqueeBanner({ message, url }: MarqueeBannerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLElement>(null);
  const [metrics, setMetrics] = useState<MarqueeMetrics>({ duration: 20, from: "100%", to: "-100%" });

  useEffect(() => {
    if (!containerRef.current || !textRef.current) return;
    const containerWidth = containerRef.current.offsetWidth;
    const textWidth = textRef.current.scrollWidth;
    setMetrics({
      duration: Math.max(8, (containerWidth + textWidth) / 80),
      from: `${containerWidth}px`,
      to: `${-textWidth}px`,
    });
  }, [message]);

  const sharedStyle: React.CSSProperties = {
    animationDuration: `${metrics.duration}s`,
    "--marquee-from": metrics.from,
    "--marquee-to": metrics.to,
  } as React.CSSProperties;

  const sharedClass =
    "inline-block whitespace-nowrap text-sm font-medium text-amber-700 dark:text-amber-300 animate-marquee";

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-hidden flex items-center gap-2 px-4 min-w-0"
    >
      <Megaphone
        size={15}
        className="shrink-0 text-amber-500 dark:text-amber-400"
        aria-hidden="true"
      />
      <div className="overflow-hidden flex-1 relative">
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            ref={textRef as React.RefObject<HTMLAnchorElement>}
            className={`${sharedClass} underline-offset-2 hover:underline`}
            style={sharedStyle}
          >
            {message}
          </a>
        ) : (
          <span
            ref={textRef as React.RefObject<HTMLSpanElement>}
            className={sharedClass}
            style={sharedStyle}
          >
            {message}
          </span>
        )}
      </div>
    </div>
  );
}
