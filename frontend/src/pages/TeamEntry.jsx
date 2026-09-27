import { useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import api from "../lib/api.js";
import VideoBackground from "../components/VideoBackground.jsx";

const ENTRY_VIDEO_SEEN_KEY = "mlforge_entry_video_seen";

function hasSeenEntryVideo() {
  try {
    // localStorage (not sessionStorage): this should persist across browser
    // restarts and future logins, not just within the current tab session.
    return localStorage.getItem(ENTRY_VIDEO_SEEN_KEY) === "1";
  } catch (e) {
    return false; // storage unavailable (private mode etc.) — just play it each time
  }
}

function markEntryVideoSeen() {
  try {
    localStorage.setItem(ENTRY_VIDEO_SEEN_KEY, "1");
  } catch (e) {
    /* no-op */
  }
}

export default function TeamEntry() {
  const { roomKey: routeRoomKey } = useParams();
  const location = useLocation();
  const [roomKey, setRoomKey] = useState(routeRoomKey || "LIVE_2026");
  const [teamName, setTeamName] = useState(location.state?.rejoinTeamName || "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  // Read once, at mount, and never recompute during this page's lifetime.
  // This is what decides whether the <video> element plays at all:
  //   - false (first visit ever on this browser): video plays.
  //   - true (this browser has seen it before, on some earlier visit):
  //     skip the video entirely and go straight to the static fallback
  //     image, from the very first render.
  const [alreadySeenBefore] = useState(() => hasSeenEntryVideo());

  // Whether the form is revealed. Starts true if we're skipping the video;
  // otherwise flips true when the video finishes.
  const [videoEnded, setVideoEnded] = useState(alreadySeenBefore);
  const navigate = useNavigate();

  async function handleEnter(e) {
    e.preventDefault();
    setError("");
    if (!teamName.trim()) {
      setError("Enter your team name.");
      return;
    }
    if (!password || password.length < 4) {
      setError("Password must be at least 4 characters.");
      return;
    }
    setLoading(true);
    try {
      const result = await api.registerTeam(roomKey, teamName.trim(), password);
      navigate(`/mission/${roomKey}/${encodeURIComponent(teamName.trim())}`, {
        state: { justResumed: result.resumed, teamCode: result.team_code },
      });
    } catch (err) {
      if (err.status === 401) {
        setError("That team name is already taken and this password doesn't match it.");
      } else {
        setError(err.message || "Could not reach the room. Check the room code.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <VideoBackground
      src="/assets/teamentry-video.mp4"
      overlay={0.35}
      // Only ever true from a *previous* visit — never flips mid-session,
      // so on a first-ever play-through the <video> element stays mounted
      // after it ends and simply holds on its own last frame, instead of
      // being swapped out for the (differently framed) fallback image.
      skip={alreadySeenBefore}
      fallbackSrc="/assets/bg-teamentry.jpg"
      onEnded={() => {
        markEntryVideoSeen();
        setVideoEnded(true);
      }}
    >      {videoEnded && (
        <form onSubmit={handleEnter} className="entry-reveal">
          <div className="split-entry">
            <div className="entry-signboard sb-left">
              <div className="sb-label">Room Code</div>
              <input
                className="sb-value"
                type="text"
                value={roomKey}
                onChange={(e) => setRoomKey(e.target.value.toUpperCase().replace(/\s+/g, "_"))}
              />
              <div className="sb-status">
                <span className="sb-dot" />
                ONLINE
              </div>
            </div>

            <div className="entry-signboard sb-right">
              <div className="sb-label">Team Name</div>
              <input
                className="sb-input"
                type="text"
                value={teamName}
                onChange={(e) => setTeamName(e.target.value)}
                placeholder="Enter your team name"
                autoFocus
              />

              <div className="sb-label" style={{ marginTop: 12 }}>Team Password</div>
              <input
                className="sb-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Choose a password (first time) or enter it (returning)"
                autoComplete="off"
              />

              {location.state?.rejoinTeamName && (
                <div className="help-text" style={{ marginBottom: 10 }}>
                  Your session here expired or isn't recognized on this device. Re-enter
                  your team name and password to continue.
                </div>
              )}
              {error && <div className="error-box">{error}</div>}
              <button className="btn primary sb-button" disabled={loading}>
                {loading ? "Connecting..." : "ENTER THE FORGE →"}
              </button>
              <p className="help-text" style={{ marginTop: 12 }}>
                First time with this team name? Whatever password you type here becomes
                your team's password. Coming back later, entering the same name and
                password resumes exactly where you left off — nothing is lost. Don't
                share your password outside your team.
              </p>
            </div>
          </div>
        </form>
      )}
    </VideoBackground>
  );
}