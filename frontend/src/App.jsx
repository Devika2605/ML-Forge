import { HashRouter, Routes, Route, Link } from "react-router-dom";
import Landing from "./pages/Landing.jsx";
import TeamEntry from "./pages/TeamEntry.jsx";
import Mission from "./pages/Mission.jsx";
import Admin from "./pages/Admin.jsx";
import Leaderboard from "./pages/Leaderboard.jsx";

function TopBar() {
  return (
    <div className="topbar">
      <Link to="/" className="brand">
        ML FORGE <small>Diagnose. Decide. Deploy.</small>
      </Link>
      <div style={{ display: "flex", gap: 14, fontSize: 13 }}>
        <Link to="/leaderboard">Leaderboard</Link>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <HashRouter>
      <div className="app-shell">
        <TopBar />
        <div className="container">
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/enter/:roomKey" element={<TeamEntry />} />
            <Route path="/enter" element={<TeamEntry />} />
            <Route path="/mission/:roomKey/:teamName" element={<Mission />} />
            {/* Not linked in the nav on purpose — only reachable by typing
                the URL directly, so participants don't see it. */}
            <Route path="/1235/admin" element={<Admin />} />
            <Route path="/leaderboard" element={<Leaderboard />} />
          </Routes>
        </div>
        <div className="footer-note">ML FORGE — Two engineers. One workstation. One failing AI system.</div>
      </div>
    </HashRouter>
  );
}
