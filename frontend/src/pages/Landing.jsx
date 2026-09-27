import { useState } from "react";
import { useNavigate } from "react-router-dom";
import PageBackground from "../components/PageBackground.jsx";

export default function Landing() {
  const [roomKey, setRoomKey] = useState("LIVE_2026");
  const navigate = useNavigate();

  return (
    <PageBackground src="/assets/bg-landing.jpg" overlay={0.18}>
      <div style={{ textAlign: "center", paddingTop: 50 }}>
        <div className="hero-banner">
          <h1 className="hero">ML FORGE</h1>
          <div className="subtitle hero-subtitle" style={{ fontSize: 18 }}>
            DIAGNOSE.DECIDE.DEPLOY.
          </div>
        </div>

        <div className="panel" style={{ maxWidth: 520, margin: "40px auto", textAlign: "left" }}>
          <div style={{ fontFamily: "var(--font-mono)", lineHeight: 2, fontSize: 14 }}>
            50 TEAMS<br />
            30 MINUTES<br />
            1 FAILING AI SYSTEM
          </div>
          <p style={{ color: "var(--text-dim)", marginTop: 14 }}>
            Two engineers. One workstation. You are the emergency ML engineering team.
            Recover the model before deployment.
          </p>

          <div style={{ marginTop: 20 }}>
            <label>Room Code</label>
            <input
              type="text"
              value={roomKey}
              onChange={(e) => setRoomKey(e.target.value.toUpperCase().replace(/\s+/g, "_"))}
              placeholder="e.g. LIVE_2026"
            />
          </div>
          <button
            className="btn primary"
            style={{ width: "100%", marginTop: 14, padding: 14 }}
            onClick={() => navigate(`/enter/${roomKey}`)}
          >
            ENTER WAR ROOM
          </button>
        </div>
      </div>
    </PageBackground>
  );
}