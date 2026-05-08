/* global React */
// ═══════════════════════════════════════════════════════════════
// Shared UI primitives for Jarvis dashboard
// ═══════════════════════════════════════════════════════════════

const { useState, useEffect, useRef, useMemo } = React;

// ─── Status dot ───
function Dot({ kind = 'idle', pulse = false, style }) {
  return <span className={`dot ${kind} ${pulse ? 'pulse' : ''}`} style={style} />;
}

// ─── Tag ───
function Tag({ kind = '', children, solid = false }) {
  return <span className={`tag ${kind} ${solid ? 'solid' : ''}`}>{children}</span>;
}

// ─── Animated bars (sparkline-ish) ───
function Bars({ values, color = 'var(--fg-faint)', height = 18 }) {
  const max = Math.max(...values, 1);
  return (
    <div className="bars" style={{ height }}>
      {values.map((v, i) => (
        <span key={i} style={{
          height: `${(v / max) * 100}%`,
          background: color,
        }} />
      ))}
    </div>
  );
}

// ─── Live ticking number ───
function TickNum({ base, jitter = 1, fmt = (n) => n.toLocaleString() }) {
  const [v, setV] = useState(base);
  useEffect(() => {
    const id = setInterval(() => {
      setV((cur) => cur + Math.floor(Math.random() * jitter));
    }, 1500 + Math.random() * 1500);
    return () => clearInterval(id);
  }, [jitter]);
  return <span className="mono-num">{fmt(v)}</span>;
}

// ─── Live clock ───
function Clock() {
  const [t, setT] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setT(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const pad = (n) => String(n).padStart(2, '0');
  return (
    <span className="mono-num">
      {pad(t.getHours())}:{pad(t.getMinutes())}:{pad(t.getSeconds())} UTC
    </span>
  );
}

// ─── Brace corners (mission-control-style frame) ───
function Brace({ children, style, label, accent = 'var(--line-strong)' }) {
  return (
    <div style={{ position: 'relative', ...style }}>
      <CornerTicks accent={accent} />
      {label && <div style={{
        position: 'absolute',
        top: -7, left: 12,
        fontSize: 9,
        letterSpacing: '0.18em',
        textTransform: 'uppercase',
        color: 'var(--fg-dim)',
        background: 'var(--bg-void)',
        padding: '0 6px',
      }}>{label}</div>}
      {children}
    </div>
  );
}

function CornerTicks({ accent = 'var(--line-bright)', size = 8 }) {
  const tick = {
    position: 'absolute',
    width: size,
    height: size,
    borderColor: accent,
    borderStyle: 'solid',
    pointerEvents: 'none',
  };
  return (
    <>
      <span style={{ ...tick, top: 0, left: 0, borderWidth: '1px 0 0 1px' }} />
      <span style={{ ...tick, top: 0, right: 0, borderWidth: '1px 1px 0 0' }} />
      <span style={{ ...tick, bottom: 0, left: 0, borderWidth: '0 0 1px 1px' }} />
      <span style={{ ...tick, bottom: 0, right: 0, borderWidth: '0 1px 1px 0' }} />
    </>
  );
}

// ─── Progress bar ───
function Progress({ value = 0, color = 'var(--amber)', height = 3, animated = true }) {
  return (
    <div style={{
      height,
      background: 'var(--line)',
      borderRadius: 1,
      overflow: 'hidden',
      position: 'relative',
    }}>
      <div style={{
        position: 'absolute',
        inset: 0,
        width: `${value * 100}%`,
        background: color,
        boxShadow: `0 0 8px ${color}`,
        transition: animated ? 'width 600ms ease-out' : 'none',
      }} />
    </div>
  );
}

// ─── KV row ───
function KV({ label, children, accent }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'baseline',
      padding: '5px 0',
      borderBottom: '1px dashed var(--line)',
      fontSize: 11,
    }}>
      <span style={{
        fontSize: 10,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color: 'var(--fg-dim)',
      }}>{label}</span>
      <span className="mono-num" style={{ color: accent || 'var(--fg)' }}>{children}</span>
    </div>
  );
}

// ─── Agent glyph badge (the small bordered square) ───
function AgentGlyph({ agent, size = 18 }) {
  if (!agent) return null;
  return (
    <span style={{
      width: size,
      height: size,
      border: `1px solid ${agent.colorHex}`,
      color: agent.colorHex,
      display: 'inline-grid',
      placeItems: 'center',
      fontSize: size < 20 ? 8 : 10,
      fontWeight: 700,
      letterSpacing: '-0.04em',
      flexShrink: 0,
      fontFamily: 'var(--mono)',
    }}>{agent.glyph}</span>
  );
}

// ─── Section heading ───
function SectionHeading({ children, right }) {
  return (
    <div className="sub-h" style={{ marginBottom: 10 }}>
      <span>{children}</span>
      {right && <span style={{ marginLeft: 'auto', flex: 'none' }}>{right}</span>}
    </div>
  );
}

// ─── Hatched placeholder ───
function Placeholder({ label, height = 80, style }) {
  return (
    <div className="hatch" style={{
      height,
      display: 'grid',
      placeItems: 'center',
      fontSize: 10,
      letterSpacing: '0.18em',
      textTransform: 'uppercase',
      color: 'var(--fg-faint)',
      borderRadius: 2,
      ...style,
    }}>
      {label || '— placeholder —'}
    </div>
  );
}

Object.assign(window, {
  Dot, Tag, Bars, TickNum, Clock, Brace, CornerTicks,
  Progress, KV, AgentGlyph, SectionHeading, Placeholder,
});
