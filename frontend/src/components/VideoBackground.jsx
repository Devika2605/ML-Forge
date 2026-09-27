import { useRef } from "react";

export default function VideoBackground({ src, overlay = 0.35, onEnded, children, skip = false, fallbackSrc }) {
  const videoRef = useRef(null);

  return (
    <div className="video-background-wrapper">
      {skip ? (
        <div
          className="video-background-el video-background-fallback"
          style={fallbackSrc ? { backgroundImage: `url(${fallbackSrc})` } : undefined}
        />
      ) : (
        <video
          ref={videoRef}
          className="video-background-el"
          src={src}
          autoPlay
          muted
          playsInline
          onEnded={onEnded}
        />
      )}
      <div
        className="video-background-overlay"
        style={{ backgroundColor: `rgba(0, 0, 0, ${overlay})` }}
      />
      <div className="video-background-content">{children}</div>

      <style>{`
        .video-background-wrapper {
          position: fixed;
          inset: 0;
          top: 0;
          left: 0;
          width: 100vw;
          height: 100vh;
          overflow: hidden;
          background: #000;
        }

        .video-background-el {
          position: absolute;
          top: 50%;
          left: 50%;
          width: 100%;
          height: 100%;
          min-width: 100%;
          min-height: 100%;
          object-fit: cover;
          transform: translate(-50%, -50%);
          z-index: 0;
        }

        .video-background-fallback {
          background-size: cover;
          background-position: center;
        }

        .video-background-overlay {
          position: absolute;
          inset: 0;
          z-index: 1;
          pointer-events: none;
        }

        .video-background-content {
          position: relative;
          z-index: 2;
          width: 100%;
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow-y: auto;
        }
      `}</style>
    </div>
  );
}