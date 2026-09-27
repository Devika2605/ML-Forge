import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "../lib/api.js";
import PageBackground from "../components/PageBackground.jsx";
import "./Leaderboard.css";

const MEDALS = { 1: "🥇", 2: "🥈", 3: "🥉" };

export default function Leaderboard() {
  const [roomKey, setRoomKey] = useState("LIVE_2026");
  const [round, setRound] = useState(1);
  const [query, setQuery] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [copied, setCopied] = useState(false);
  const [lastTeam] = useState(() => api.getLastTeam());

  async function load(showSpinner) {
    if (showSpinner) setLoading(true);
    setError("");
    try {
      const d = await api.getLeaderboard(roomKey, round);
      setData(d);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err.message);
    } finally {
      if (showSpinner) setLoading(false);
    }
  }

  useEffect(() => {
    load(true);
    const id = setInterval(() => load(false), 5000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomKey, round]);

  const rows = data?.rows ?? [];
  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => r.team_name.toLowerCase().includes(q));
  }, [rows, query]);

  function copyRoomKey() {
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(roomKey).catch(() => {});
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <PageBackground src="/assets/leaderboard-bg.png" overlay={0.55}>
      <div className="mc-board">
        <div className="mc-frame">
        <div className="mc-moss" aria-hidden="true" />
        <div className="mc-lanterns" aria-hidden="true">
          <span className="mc-lantern">🏮</span>
          <span className="mc-lantern">🏮</span>
        </div>

        <div className="mc-sign-wrap">
          <span className="mc-crown" aria-hidden="true">👑</span>
          <div className="mc-sign mc-pixel-corners">
            <h1>Leaderboard</h1>
          </div>
        </div>

        {lastTeam && (
          <div style={{ textAlign: "center", marginBottom: 18 }}>
            <Link
              to={`/mission/${lastTeam.roomKey}/${encodeURIComponent(lastTeam.teamName)}`}
              className="btn mc-pixel-corners-sm"
              style={{ display: "inline-block", textDecoration: "none" }}
            >
              ← Back to Chambers
            </Link>
          </div>
        )}

        <div className="mc-controls">
          <div className="mc-field">
            <label htmlFor="mc-room-code">📖 Room Code</label>
            <div className="mc-input-row">
              <input
                id="mc-room-code"
                value={roomKey}
                onChange={(e) => setRoomKey(e.target.value.toUpperCase().replace(/\s+/g, "_"))}
              />
              <button
                type="button"
                className="mc-icon-btn mc-pixel-corners-sm"
                onClick={copyRoomKey}
                aria-label="Copy room code"
                title="Copy room code"
              >
                📋
              </button>
            </div>
            {copied && <div className="mc-copied">COPIED!</div>}
          </div>

          <div className="mc-field">
            <label htmlFor="mc-search-team">🔍 Search Team</label>
            <div className="mc-input-row">
              <input
                id="mc-search-team"
                placeholder="Type a team name…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <button
                type="button"
                className="mc-icon-btn mc-pixel-corners-sm"
                onClick={() => document.getElementById("mc-search-team")?.focus()}
                aria-label="Search team"
                title="Search"
              >
                🔎
              </button>
            </div>
          </div>
        </div>

        <div className="mc-tabs">
          <button
            type="button"
            className={`mc-tab mc-pixel-corners-sm ${round === 1 ? "active" : ""}`}
            onClick={() => setRound(1)}
          >
            <span className="mc-tab-icon">🟩</span> ROUND 1
          </button>
          <button
            type="button"
            className={`mc-tab mc-pixel-corners-sm ${round === 2 ? "active" : ""}`}
            onClick={() => setRound(2)}
          >
            <span className="mc-tab-icon">🔒</span> ROUND 2 <span className="mc-tab-hint">(Top 10)</span>
          </button>
        </div>

        <p className="mc-help-text">
          Round 1 and Round 2 are scored independently — this is each round's own ranking, not a blended score.
        </p>

        {error && <div className="mc-error">{error}</div>}

        {data && (
          <div className="mc-stats">
            <div className="mc-stats-item">
              👥 <span className="mc-stats-val">{data.scored_count}</span> / {data.team_count} scored
            </div>
            {data.top_score != null && (
              <div className="mc-stats-item">
                Top score: <span className="mc-stats-val">{data.top_score}</span>
              </div>
            )}
            <div className="mc-updated">
              🕐 {loading ? "Refreshing…" : lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : ""}
            </div>
          </div>
        )}

        <div className="mc-table">
          <div className="mc-row mc-row-head">
            <div>#</div>
            <div>TEAM</div>
            <div>STATUS</div>
            <div>SCORE</div>
          </div>

          {filteredRows.map((r) => (
            <div
              key={r.team_name}
              className={`mc-row mc-row-body ${r.rank && r.rank <= 3 ? "top3" : ""}`}
            >
              <div className="mc-rank">{r.rank ? (MEDALS[r.rank] || r.rank) : "—"}</div>
              <div className="mc-team">
                {r.team_name}
                {round === 1 && r.qualified_round2 && (
                  <span className="mc-badge green">R2</span>
                )}
              </div>
              <div>
                {r.scored ? (
                  <span className="mc-badge green">SCORED</span>
                ) : r.submitted ? (
                  <span className="mc-badge warning">SUBMITTED</span>
                ) : (
                  <span className="mc-badge neutral">WORKING</span>
                )}
              </div>
              <div className="mc-score">{r.score ?? "—"}</div>
            </div>
          ))}

          {!loading && filteredRows.length === 0 && rows.length > 0 && (
            <div className="mc-empty">
              <div className="mc-empty-sub">No team matches "{query}".</div>
            </div>
          )}

          {!loading && rows.length === 0 && (
            <div className="mc-empty">
              <span className="mc-chest" aria-hidden="true">📦</span>
              <div className="mc-empty-title">NO TEAMS YET FOR THIS ROUND.</div>
              <p className="mc-empty-sub">Scores will appear here once teams submit.</p>
            </div>
          )}
        </div>
      </div>
      </div>
    </PageBackground>
  );
}