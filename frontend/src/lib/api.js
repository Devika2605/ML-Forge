// In production this is served by the same FastAPI process as the frontend
// (see backend/app/main.py's static mount), so requests are same-origin and
// need no base URL at all. VITE_API_BASE only needs to be set for local dev
// against a separately-running backend (see frontend/.env.development),
// which is why the fallback here is "" and not localhost.
const API_BASE = import.meta.env.VITE_API_BASE || "";

async function request(method, path, body, extraHeaders = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...extraHeaders },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch (e) {
    /* no body */
  }
  if (!res.ok) {
    const message = (data && data.detail) || `Request failed (${res.status})`;
    const err = new Error(message);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

// ---------------------------------------------------------------------------
// Team session tokens.
//
// A team name alone used to be enough to act as that team (register/resume
// only checked room_key + team_name). Now registering or resuming requires a
// password, and the backend hands back a per-team session token that proves
// "this browser is the one that logged in as this team". Every later call
// that reads or changes that team's state must carry the same token, or the
// backend rejects it with 401.
//
// Stored per (room, team) so a shared computer can hold sessions for more
// than one team/room without them clobbering each other.
// ---------------------------------------------------------------------------
function tokenStorageKey(roomKey, teamName) {
  return `mlforge_token:${roomKey}:${teamName}`;
}

function storeTeamSession(roomKey, teamName, token) {
  try {
    localStorage.setItem(tokenStorageKey(roomKey, teamName), token);
  } catch (e) {
    /* localStorage unavailable (private mode etc.) — session just won't persist across reloads */
  }
}

function getTeamToken(roomKey, teamName) {
  try {
    return localStorage.getItem(tokenStorageKey(roomKey, teamName)) || "";
  } catch (e) {
    return "";
  }
}

function clearTeamSession(roomKey, teamName) {
  try {
    localStorage.removeItem(tokenStorageKey(roomKey, teamName));
  } catch (e) {
    /* no-op */
  }
}

// ---------------------------------------------------------------------------
// "Last active team" — lets pages like the Leaderboard offer a "Back to
// Chambers" button that goes straight to /mission/:roomKey/:teamName
// without sending the person back through the room-code + password entry
// screen. Updated every time a team successfully registers/resumes.
// ---------------------------------------------------------------------------
const LAST_TEAM_KEY = "mlforge_last_team";

function storeLastTeam(roomKey, teamName) {
  try {
    localStorage.setItem(LAST_TEAM_KEY, JSON.stringify({ roomKey, teamName }));
  } catch (e) {
    /* no-op */
  }
}

function getLastTeam() {
  try {
    const raw = localStorage.getItem(LAST_TEAM_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    // Only worth offering if we still hold a live session token for it —
    // otherwise "Back to Chambers" would just bounce them to a 401 redirect.
    if (parsed && parsed.roomKey && parsed.teamName && getTeamToken(parsed.roomKey, parsed.teamName)) {
      return parsed;
    }
    return null;
  } catch (e) {
    return null;
  }
}

// Attaches the stored token to a payload that already has room_key/team_name.
function withToken(payload) {
  return { ...payload, team_token: getTeamToken(payload.room_key, payload.team_name) };
}

// Appends team_token as a query param to a GET URL that already has a team
// identity in its path.
function withTokenQuery(url, roomKey, teamName) {
  const token = getTeamToken(roomKey, teamName);
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}team_token=${encodeURIComponent(token)}`;
}

export const api = {
  // rooms
  createRoom: (room_key, name) => request("POST", "/api/rooms", { room_key, name }),
  getRoom: (roomKey) => request("GET", `/api/rooms/${roomKey}`),
  listRooms: () => request("GET", "/api/rooms"),

  // teams
  // password is required now: on a brand-new team name it sets the
  // password; on an existing name it must match, or the call fails.
  registerTeam: async (room_key, team_name, password) => {
    const result = await request("POST", "/api/teams/register", { room_key, team_name, password });
    storeTeamSession(room_key, team_name, result.team_token);
    storeLastTeam(room_key, team_name);
    return result;
  },
  getTeamState: (roomKey, teamName, roundNumber) =>
    request("GET", withTokenQuery(`/api/teams/${roomKey}/${teamName}/state?round_number=${roundNumber}`, roomKey, teamName)),
  clearTeamSession,
  hasTeamSession: (roomKey, teamName) => !!getTeamToken(roomKey, teamName),
  getLastTeam,

  // mission
  investigate: (roomKey, teamName, roundNumber) =>
    request("GET", withTokenQuery(`/api/mission/${roomKey}/${teamName}/${roundNumber}/investigate`, roomKey, teamName)),
  panelOpen: (payload) => request("POST", "/api/mission/panel-open", withToken(payload)),
  preprocess: (payload) => request("POST", "/api/mission/preprocess", withToken(payload)),
  runModel: (payload) => request("POST", "/api/mission/run-model", withToken(payload)),
  adjustThreshold: (payload) => request("POST", "/api/mission/threshold", withToken(payload)),
  experiments: (roomKey, teamName, roundNumber) =>
    request("GET", withTokenQuery(`/api/mission/${roomKey}/${teamName}/${roundNumber}/experiments`, roomKey, teamName)),
  getTwist: (roomKey, teamName, roundNumber) =>
    request("GET", `/api/mission/${roomKey}/${teamName}/${roundNumber}/twist`),
  twistAck: (payload) => request("POST", "/api/mission/twist-ack", withToken(payload)),
  getBlackbox: (roomKey, teamName, roundNumber) =>
    request("GET", withTokenQuery(`/api/mission/${roomKey}/${teamName}/${roundNumber}/blackbox`, roomKey, teamName)),
  blackboxAnswer: (payload) => request("POST", "/api/mission/blackbox-answer", withToken(payload)),
  submit: (payload) => request("POST", "/api/mission/submit", withToken(payload)),
  logTabSwitch: (payload) => request("POST", "/api/mission/tab-switch", payload),

  // reference
  getReference: () => request("GET", "/api/reference"),

  // leaderboard — Round 1 and Round 2 are independent; roundNumber defaults to 1
  getLeaderboard: (roomKey, roundNumber = 1) =>
    request("GET", `/api/leaderboard/${roomKey}?round_number=${roundNumber}`),

  // admin
  adminStartRound1: (roomKey) => request("POST", `/api/admin/${roomKey}/start-round1`),
  adminReleaseTwist: (roomKey) => request("POST", `/api/admin/${roomKey}/release-twist`),
  adminLockRound1: (roomKey) => request("POST", `/api/admin/${roomKey}/lock-submissions`),
  adminCalcScores1: (roomKey) => request("POST", `/api/admin/${roomKey}/calculate-scores`),
  adminAdvanceTop10: (roomKey) => request("POST", `/api/admin/${roomKey}/advance-top10`),
  adminStartRound2: (roomKey) => request("POST", `/api/admin/${roomKey}/start-round2`),
  adminReleaseIncident: (roomKey) => request("POST", `/api/admin/${roomKey}/release-incident`),
  adminLockRound2: (roomKey) => request("POST", `/api/admin/${roomKey}/lock-final-submissions`),
  adminCalcScores2: (roomKey) => request("POST", `/api/admin/${roomKey}/calculate-scores-round2`),
  adminWinner: (roomKey) => request("GET", `/api/admin/${roomKey}/winner`),
  adminLiveView: (roomKey) => request("GET", `/api/admin/${roomKey}/live-view`),
  adminTabSwitches: (roomKey) => request("GET", `/api/admin/${roomKey}/tab-switches`),
  // team password tools — require the organizer's admin key
  adminListTeams: (roomKey, adminKey) =>
    request("GET", `/api/admin/${roomKey}/teams`, undefined, { "X-Admin-Key": adminKey }),
  adminResetPassword: (roomKey, teamId, adminKey) =>
    request("POST", `/api/admin/${roomKey}/teams/${teamId}/reset-password`, undefined, { "X-Admin-Key": adminKey }),
  adminReportUrl: (roomKey, roundNumber) => `${API_BASE}/api/admin/${roomKey}/report/${roundNumber}`,
};

export default api;