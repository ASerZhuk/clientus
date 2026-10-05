/** clientall mark: a "c" drawn as a booking dial; the orange dot in its opening is the client who just booked. */
export function LogoMark({ size = 28, ink = "currentColor", accent = "#efe5d3" }: { size?: number; ink?: string; accent?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden focusable="false">
      <path d="M24.43 8.93A11 11 0 1 0 24.43 23.07" fill="none" stroke={ink} strokeWidth="5" strokeLinecap="round" />
      <circle cx="26.6" cy="16" r="3.4" fill={accent} />
    </svg>
  );
}

export function Logo({ size = 28, className, accent }: { size?: number; className?: string; accent?: string }) {
  return (
    <span className={`cl-logo ${className ?? ""}`} style={{ fontSize: size * 0.82 }}>
      <LogoMark size={size} accent={accent} />
      <span>clientall</span>
    </span>
  );
}
