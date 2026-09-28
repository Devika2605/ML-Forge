import { useEffect, useState } from "react";
import api from "../lib/api.js";

function fmtTime(sec) {
  if (sec == null) return "--:--";
  const m = Math.floor(sec / 60).toString().padStart(2, "0");
  const s = Math.floor(sec % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export default function Admin() {
  const [roomKey, setRoomKey] = useState("LIVE_2026");
  const [roomName, setRoomName] = useState("ML Forge Live");
  const [room, setRoom] = useState(null);
  const [liveView, setLiveView] = useState(null);
  const [tabSwitches, setTabSwitches] = useState(null);
  const [winner, setWinner] = useState(null);
  const [adminKey, setAdminKey] = useState("");
  const [teams, setTeams] = useState(null);
  const [resetResult, setResetResult] = useState(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function refresh() {
    try {
      const r = await api.getRoom(roomKey);
      setRoom(r);
      setErr("");
    } catch (e) {
      if (!room) return; // room truly doesn't exist yet — not an error
      setErr(`getRoom failed: ${e.message}`);
      return;
    }
    try {
      const lv = await api.adminLiveView(roomKey);
      setLiveView(lv);
    } catch (e) { setErr(`live-view failed: ${e.message}`); }
    try {
      const ts = await api.adminTabSwitches(roomKey);
      setTabSwitches(ts);
    } catch (e) { setErr(`tab-switches failed: ${e.message}`); }
  }

  useEffect(() => {
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [roomKey]);

  async function run(fn, successMsg) {
    setErr(""); setMsg("");
    try {
      await fn();
      setMsg(successMsg);
      await refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function loadTeams(clearResult = true) {
    setErr("");
    if (clearResult) setResetResult(null);
    try {
      setTeams(await api.adminListTeams(roomKey, adminKey));
    } catch (e) { setErr(e.message); }
  }

  async function resetPassword(team) {
    if (!window.confirm(`Reset the password for "${team.team_name}"? Their current password stops working and they'll be signed out.`)) return;
    setErr(""); setResetResult(null);
    try {
      setResetResult(await api.adminResetPassword(roomKey, team.team_id, adminKey));
      await loadTeams(false); // keep the temporary password visible after refreshing the list
    } catch (e) { setErr(e.message); }
  }

  return (
    <div>
      <div className="panel">
        <div className="panel-title">Room Setup</div>
        <div className="grid cols-2">
          <div><label>Room Key</label><input value={roomKey} onChange={(e) => setRoomKey(e.target.value.toUpperCase().replace(/\s+/g, "_"))} /></div>
          <div><label>Room Name</label><input value={roomName} onChange={(e) => setRoomName(e.target.value)} /></div>
        </div>
        <div style={{ marginTop: 12, display: "flex", gap: 10 }}>
          <button className="btn primary" onClick={() => run(() => api.createRoom(roomKey, roomName), "Room created.")}>Create Room</button>
          <button className="btn" onClick={refresh}>Load / Refresh Status</button>
        </div>
      </div>

      {err && <div className="error-box">{err}</div>}
      {msg && <div className="success-box">{msg}</div>}

      {room && (
        <>
          <div className="panel">
            <div className="panel-title">Round Control</div>
            <div className="grid cols-4">
              <button className="btn" onClick={() => run(() => api.adminStartRound1(roomKey), "Round 1 started.")}>START ROUND 1</button>
              <button className="btn" onClick={() => run(() => api.adminReleaseTwist(roomKey), "Twist released.")}>RELEASE TWIST</button>
              <button className="btn" onClick={() => run(() => api.adminLockRound1(roomKey), "Round 1 locked.")}>LOCK SUBMISSIONS</button>
              <button className="btn" onClick={() => run(() => api.adminCalcScores1(roomKey), "Scores calculated.")}>CALCULATE SCORES</button>
              <button className="btn" onClick={() => run(() => api.adminAdvanceTop10(roomKey), "Top 10 advanced.")}>ADVANCE TOP 10</button>
              <button className="btn" onClick={() => run(() => api.adminStartRound2(roomKey), "Round 2 started.")}>START ROUND 2</button>
              <button className="btn" onClick={() => run(() => api.adminReleaseIncident(roomKey), "Incident released.")}>RELEASE INCIDENT</button>
              <button className="btn" onClick={() => run(() => api.adminLockRound2(roomKey), "Round 2 locked.")}>LOCK FINAL SUBMISSIONS</button>
              <button className="btn" onClick={() => run(() => api.adminCalcScores2(roomKey), "Round 2 scores calculated.")}>CALC SCORES R2</button>
              <button
                className="btn primary"
                onClick={async () => {
                  setErr(""); setMsg("");
                  try {
                    const w = await api.adminWinner(roomKey);
                    setWinner(w);
                  } catch (e) { setErr(e.message); }
                }}
              >
                SHOW WINNER
              </button>
            </div>
          </div>

          <div className="panel">
            <div className="panel-title">Live View</div>
            <div className="grid cols-3">
              <div className="result-box"><div className="val">{room.status}</div><div className="lbl">room status</div></div>
              <div className="result-box"><div className="val">{liveView?.teams_registered ?? "—"}</div><div className="lbl">teams registered</div></div>
              <div className="result-box"><div className="val">{fmtTime(room.round1.time_remaining)}</div><div className="lbl">round 1 remaining</div></div>
              <div className="result-box"><div className="val">{liveView?.round1_submitted ?? "—"}</div><div className="lbl">submitted (R1)</div></div>
              <div className="result-box"><div className="val">{liveView?.round1_working ?? "—"}</div><div className="lbl">working (R1)</div></div>
              <div className="result-box"><div className="val">{liveView?.top_score ?? "—"}</div><div className="lbl">top score</div></div>
              <div className="result-box"><div className="val">{liveView?.lowest_score ?? "—"}</div><div className="lbl">lowest score</div></div>
              <div className="result-box"><div className="val">{fmtTime(room.round2.time_remaining)}</div><div className="lbl">round 2 remaining</div></div>
              <div className="result-box"><div className="val">{room.round1.twist_released ? "YES" : "NO"}</div><div className="lbl">twist released (R1)</div></div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-title">Tab Switch Violations{tabSwitches ? ` (${tabSwitches.total})` : ""}</div>
            {tabSwitches && tabSwitches.by_team.length > 0 ? (
              tabSwitches.by_team.map((row) => (
                <div key={row.team_name} className="leaderboard-row" style={{ gridTemplateColumns: "1fr 100px" }}>
                  <div>{row.team_name}</div>
                  <div><strong>{row.count}</strong></div>
                </div>
              ))
            ) : (
              <p className="help-text">No tab switches logged yet.</p>
            )}
          </div>

          <div className="panel">
            <div className="panel-title">Team Access (forgotten passwords)</div>
            <p className="help-text" style={{ marginTop: -6, marginBottom: 12 }}>
              Passwords are stored hashed, so an old one can't be looked up — if a team
              forgets theirs, reset it here and give them the temporary one shown below.
            </p>
            <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
              <input type="password" placeholder="Admin key" value={adminKey} onChange={(e) => setAdminKey(e.target.value)} />
              <button className="btn" onClick={() => loadTeams()}>Load Teams</button>
            </div>
            {resetResult && (
              <div className="success-box">
                New temporary password for <strong>{resetResult.team_name}</strong>:{" "}
                <strong style={{ letterSpacing: 2 }}>{resetResult.temporary_password}</strong>
                {" "}— shown only once. Tell the team to log in with it.
              </div>
            )}
            {teams && teams.map((t) => (
              <div key={t.team_id} className="leaderboard-row" style={{ gridTemplateColumns: "1fr 130px 90px 140px" }}>
                <div>{t.team_name}{t.qualified_round2 && <span className="badge green" style={{ marginLeft: 6 }}>R2</span>}</div>
                <div>{t.team_code || "—"}</div>
                <div>{t.has_password ? "Set" : "Not set"}</div>
                <div><button className="btn" onClick={() => resetPassword(t)}>Reset password</button></div>
              </div>
            ))}
          </div>

          <div className="panel">
            <div className="panel-title">Validation Reports</div>
            <div style={{ display: "flex", gap: 10 }}>
              <a className="btn" href={api.adminReportUrl(roomKey, 1)}>Download Round 1 Report (CSV)</a>
              <a className="btn" href={api.adminReportUrl(roomKey, 2)}>Download Round 2 Report (CSV)</a>
            </div>
          </div>

          {winner && (
            <div className="panel">
              <div className="panel-title">Winner — ranked by Round 2 score</div>
              <p className="help-text" style={{ marginTop: -6, marginBottom: 14 }}>
                Round 1 and Round 2 are scored independently. Round 1 decided who advanced;
                the final ranking below is Round 2 alone, with Round 1 shown for context only.
              </p>
              {winner.map((w) => (
                <div key={w.team_name} className="leaderboard-row" style={{ gridTemplateColumns: "40px 1fr 120px 120px" }}>
                  <div className="rank-num">{w.rank}</div>
                  <div>{w.team_name}</div>
                  <div>R1 (context): {w.round1_score ?? "—"}</div>
                  <div><strong>R2: {w.round2_score}</strong></div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}