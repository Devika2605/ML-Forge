export default function PageBackground({ src, overlay = 0.5, blur = 0, children }) {
  return (
    <>
      <div
        className="page-bg"
        style={{
          backgroundImage: `url(${src})`,
          filter: blur ? `blur(${blur}px)` : undefined,
          // overshoot slightly so the blurred edges don't reveal transparent gaps
          transform: blur ? "scale(1.08)" : undefined,
        }}
      >
        <div className="page-bg-overlay" style={{ background: `rgba(6,8,10,${overlay})` }} />
      </div>
      <div className="page-bg-content">{children}</div>
    </>
  );
}