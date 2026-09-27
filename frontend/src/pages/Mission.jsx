import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "../lib/api.js";
import PageBackground from "../components/PageBackground.jsx";

const CHAMBER_BG = {
  lab: "/assets/bg-lab.jpg",
  prep: "/assets/bg-prep.jpg",
  forge: "/assets/bg-forge.jpg",
  deploy: "/assets/bg-deploy.jpg",
};

const IMPUTATIONS = ["mean", "median", "mode", "remove_rows"];
const SCALINGS = ["none", "standardize", "normalize"];
const MODELS = ["logistic_regression", "decision_tree", "random_forest", "knn", "naive_bayes", "svm"];
const METRICS = ["accuracy", "precision", "recall", "f1"];

const CHAMBERS = [
  {
    key: "lab",
    num: 1,
    name: "Data Lab",
    verb: "INVESTIGATE",
    desc: "Investigate the dataset. Uncover missing values, class imbalance, and suspicious features.",
  },
  {
    key: "prep",
    num: 2,
    name: "Preprocessing Unit",
    verb: "PREPARE",
    desc: "Choose imputation and scaling. Decide which optional features actually belong.",
  },
  {
    key: "forge",
    num: 3,
    name: "Model Forge",
    verb: "BUILD",
    desc: "Pick a model and a metric, run it, and iterate until performance holds up.",
  },
  {
    key: "deploy",
    num: 4,
    name: "Deployment Chamber",
    verb: "DEPLOY",
    desc: "Review requirements and submit your final model. This locks your workspace.",
  },
];

function fmtTime(sec) {
  if (sec == null) return "--:--";
  const m = Math.floor(sec / 60).toString().padStart(2, "0");
  const s = Math.floor(sec % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function HelpTip({ text }) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: "relative" }}>
      <span className="help-btn" onClick={() => setOpen(!open)}>?</span>
      {open && <div className="help-text" style={{ position: "absolute", top: 20, left: 0, background: "var(--panel-2)", border: "1px solid var(--border)", padding: 8, borderRadius: 4, width: 220, zIndex: 10 }}>{text}</div>}
    </span>
  );
}

export default function Mission() {
  const { roomKey, teamName } = useParams();
  const navigate = useNavigate();
  const [room, setRoom] = useState(null);
  const [state, setState] = useState(null);
  const [dataset, setDataset] = useState(null);
  const [round, setRound] = useState(1);
  const [investigateData, setInvestigateData] = useState(null);
  const [openPanels, setOpenPanels] = useState(new Set());
  const [experiments, setExperiments] = useState([]);
  const [reference, setReference] = useState(null);
  const [twist, setTwist] = useState({ released: false });
  const [twistAcked, setTwistAcked] = useState(false);
  const [blackbox, setBlackbox] = useState(null);
  const [bbFeedback, setBbFeedback] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tabSwitchWarning, setTabSwitchWarning] = useState("");
  const tabSwitchCount = useRef(0);
  const [runningModel, setRunningModel] = useState(false);

  const [imputation, setImputation] = useState("");
  const [scaling, setScaling] = useState("");
  const [featureFlags, setFeatureFlags] = useState({});
  const [model, setModel] = useState("");
  const [metric, setMetric] = useState("");

  // ---- hub / chamber navigation state ----
  const [activeChamber, setActiveChamber] = useState(null); // null = hub
  const [showBrief, setShowBrief] = useState(false);
  const briefShownForRound = useRef(new Set());
  // Tracks which rounds' editable fields (imputation/scaling/feature flags/
  // model/metric) have already been hydrated from the server. These fields
  // are only ever pushed TO the server on an explicit save (savePreprocess,
  // runModel) — never on the 5s poll — so we must only pull them FROM the
  // server once per round. Otherwise a poll landing between "click a chip"
  // and "the next explicit save" overwrites the user's in-progress click
  // back to whatever (possibly empty) value the server currently has,
  // which is exactly what made Model Forge selections feel like they
  // needed 2-3 clicks to "stick".
  const hydratedFieldsForRound = useRef(new Set());

  const pollRef = useRef(null);

  const loadAll = useCallback(async () => {
    try {
      const roomData = await api.getRoom(roomKey);
      setRoom(roomData);
      const activeRound = roomData.status === "ROUND2" ? 2 : 1;
      setRound(activeRound);

      const stateData = await api.getTeamState(roomKey, teamName, activeRound);
      setState(stateData.state);
      setDataset(stateData.dataset);
      setOpenPanels(new Set(stateData.state.panels_opened || []));
      if (!hydratedFieldsForRound.current.has(activeRound)) {
        hydratedFieldsForRound.current.add(activeRound);
        setImputation(stateData.state.imputation || "");
        setScaling(stateData.state.scaling || "");
        setFeatureFlags(stateData.state.feature_flags || {});
        setModel(stateData.state.model || "");
        setMetric(stateData.state.primary_metric || "");
      }

      if (stateData.twist_released) {
        const t = await api.getTwist(roomKey, teamName, activeRound);
        setTwist(t);
        setTwistAcked(!!stateData.state.twist_metric_switched);
      }

      const exps = await api.experiments(roomKey, teamName, activeRound);
      setExperiments(exps);

      if (activeRound === 2) {
        try {
          const bb = await api.getBlackbox(roomKey, teamName, 2);
          setBlackbox(bb);
        } catch (e) { /* not available yet */ }
      }

      if (!reference) {
        const ref = await api.getReference();
        setReference(ref);
      }

      if (!briefShownForRound.current.has(activeRound)) {
        briefShownForRound.current.add(activeRound);
        setShowBrief(true);
        setActiveChamber(null);
      }
    } catch (err) {
      if (err.status === 401) {
        // No valid session for this team on this browser (new device, cleared
        // storage, or a stale/expired token) — send them back to log in
        // rather than getting stuck on a dead screen.
        api.clearTeamSession(roomKey, teamName);
        navigate(`/enter/${roomKey}`, { state: { rejoinTeamName: teamName } });
        return;
      }
      setError(err.message);
    }
  }, [roomKey, teamName, reference, navigate]);

  useEffect(() => {
    loadAll();
    pollRef.current = setInterval(loadAll, 5000);
    return () => clearInterval(pollRef.current);
  }, [loadAll]);

  // ---- tab-switch detection ----
  // Fires whenever this tab is hidden (switched away, minimized, or the
  // window loses focus on most browsers). We warn the team in-app and log
  // it server-side (best-effort) so organizers can see it on Admin > Live View.
  useEffect(() => {
    function handleVisibilityChange() {
      if (document.hidden) {
        tabSwitchCount.current += 1;
        setTabSwitchWarning(
          `Tab switch detected (${tabSwitchCount.current}). This has been logged for the organizers.`
        );
        api
          .logTabSwitch({ room_key: roomKey, team_name: teamName, round_number: round })
          .catch(() => { /* best-effort — never block the team on a logging failure */ });
      }
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [roomKey, teamName, round]);

  async function openPanel(panel) {
    try {
      await api.panelOpen({ room_key: roomKey, team_name: teamName, round_number: round, panel });
      setOpenPanels((prev) => new Set([...prev, panel]));
      if (!investigateData) {
        const data = await api.investigate(roomKey, teamName, round);
        setInvestigateData(data);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  async function savePreprocess(partial) {
    try {
      await api.preprocess({ room_key: roomKey, team_name: teamName, round_number: round, ...partial });
      setNotice("Saved.");
      setTimeout(() => setNotice(""), 1500);
    } catch (err) {
      setError(err.message);
    }
  }

  function toggleFeature(feat) {
    const next = { ...featureFlags, [feat]: !featureFlags[feat] };
    setFeatureFlags(next);
    savePreprocess({ feature_flags: next });
  }

  async function runModel() {
    if (!model || !metric || !imputation || !scaling) {
      setError("Choose imputation, scaling, a model, and a metric before running.");
      return;
    }
    setRunningModel(true);
    setError("");
    try {
      const res = await api.runModel({
        room_key: roomKey, team_name: teamName, round_number: round, model, primary_metric: metric,
      });
      setState((s) => ({ ...s, last_run_result: res.result }));
      const exps = await api.experiments(roomKey, teamName, round);
      setExperiments(exps);
    } catch (err) {
      setError(err.message);
    } finally {
      setRunningModel(false);
    }
  }

  async function ackTwist(switchedMetric, didFeatureCheck) {
    try {
      await api.twistAck({
        room_key: roomKey, team_name: teamName, round_number: round,
        switched_metric: switchedMetric, did_feature_check: didFeatureCheck,
      });
      setTwistAcked(true);
    } catch (err) {
      setError(err.message);
    }
  }

  async function answerBlackbox(option) {
    try {
      const res = await api.blackboxAnswer({
        room_key: roomKey, team_name: teamName, round_number: round,
        question_id: blackbox.id, selected_option: option,
      });
      setBbFeedback(res);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleSubmit() {
    if (!window.confirm("Submitting locks your workspace permanently for this round. Continue?")) return;
    try {
      await api.submit({ room_key: roomKey, team_name: teamName, round_number: round });
      setNotice("Submitted and locked.");
      loadAll();
    } catch (err) {
      setError(err.message);
    }
  }

  if (!state || !dataset || !room) {
    return <div className="panel">Loading mission...</div>;
  }

  const remaining = round === 1 ? room.round1.time_remaining : room.round2.time_remaining;
  const missionDuration = round === 1 ? room.round1.duration_seconds : room.round2.duration_seconds;
  const timerClass = remaining == null ? "" : remaining < 120 ? "danger" : remaining < 300 ? "warning" : "";
  const locked = state.locked || state.submitted;
  const twistBlocking = twist.released && !twistAcked && !showBrief;

  const chamberStatus = {
    lab: openPanels.size > 0,
    prep: !!(imputation && scaling),
    forge: !!state.last_run_result,
    deploy: !!state.submitted,
  };

  function ChamberNav({ current }) {
    return (
      <div className="chamber-nav">
        <button className="nav-pill hub-pill" onClick={() => setActiveChamber(null)}>&larr; HUB</button>
        {CHAMBERS.map((c) => (
          <button
            key={c.key}
            className={`nav-pill ${c.key} ${current === c.key ? "active " + c.key : ""}`}
            onClick={() => setActiveChamber(c.key)}
          >
            {c.num}. {c.name}
          </button>
        ))}
      </div>
    );
  }

  function renderHub() {
  return (
    <div>
      <div className="panel" style={{ textAlign: "center" }}>
        <div className="panel-title" style={{ display: "inline-block" }}>Mission Brief</div>
        <p style={{ margin: 0 }}>{dataset.brief}</p>
      </div>
      {CHAMBERS.map((c) => (
        <div
          key={c.key}
          className={`hub-hotspot ${c.key}`}
          onClick={() => setActiveChamber(c.key)}
          title={`${c.num}. ${c.name}`}
        />
      ))}
    </div>
  );
}
 
  function renderLab() {
    return (
      <div className={`chamber-view lab`}>
        <div className="chamber-view-header">
          <span className="chamber-title">01. Data Lab</span>
          <span className="chamber-subtitle">Investigate</span>
        </div>
        <ChamberNav current="lab" />
        <div className="panel lab">
          <div className="panel-title">Investigate the Dataset</div>
          <div>
            {["missing_values", "class_distribution", "feature_preview"].map((p) => (
              <button key={p} className={`chip ${openPanels.has(p) ? "selected" : ""}`} onClick={() => openPanel(p)} disabled={locked}>
                {p.replace(/_/g, " ")}
              </button>
            ))}
          </div>
          {investigateData && (
            <div style={{ marginTop: 14 }}>
              <div className="grid cols-3">
                <div className="result-box"><div className="val">{investigateData.rows}</div><div className="lbl">rows</div></div>
                <div className="result-box"><div className="val">{investigateData.columns.length}</div><div className="lbl">columns</div></div>
                <div className="result-box"><div className="val">{investigateData.target}</div><div className="lbl">target</div></div>
              </div>
              {openPanels.has("missing_values") && (
                <div style={{ marginTop: 12 }}>
                  <strong style={{ fontSize: 13 }}>Missing values (%)</strong>
                  <table style={{ marginTop: 6 }}><tbody>
                    {Object.entries(investigateData.missing_values_pct).filter(([, v]) => v > 0).map(([k, v]) => (
                      <tr key={k}><td>{k}</td><td>{v}%</td></tr>
                    ))}
                  </tbody></table>
                </div>
              )}
              {openPanels.has("class_distribution") && (
                <div style={{ marginTop: 12 }}>
                  <strong style={{ fontSize: 13 }}>Class distribution</strong>
                  <table style={{ marginTop: 6 }}><tbody>
                    {Object.entries(investigateData.class_distribution).map(([k, v]) => (
                      <tr key={k}><td>{k}</td><td>{(v * 100).toFixed(1)}%</td></tr>
                    ))}
                  </tbody></table>
                </div>
              )}
              {openPanels.has("feature_preview") && (
                <div style={{ marginTop: 12, overflowX: "auto" }}>
                  <strong style={{ fontSize: 13 }}>Sample records</strong>
                  <table style={{ marginTop: 6, fontSize: 11 }}>
                    <thead><tr>{investigateData.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                    <tbody>
                      {investigateData.sample_records.map((row, i) => (
                        <tr key={i}>{investigateData.columns.map((c) => <td key={c}>{row[c] === null ? "\u2014" : String(row[c])}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  function renderPrep() {
    return (
      <div className={`chamber-view prep`}>
        <div className="chamber-view-header">
          <span className="chamber-title">02. Preprocessing Unit</span>
          <span className="chamber-subtitle">Prepare</span>
        </div>
        <ChamberNav current="prep" />
        <div className="panel prep">
          <div className="panel-title">Prepare the Data</div>
          <div className="grid cols-2">
            <div>
              <label>Missing Value Handling</label>
              <select value={imputation} disabled={locked} onChange={(e) => { setImputation(e.target.value); savePreprocess({ imputation: e.target.value }); }}>
                <option value="">Choose...</option>
                {IMPUTATIONS.map((v) => <option key={v} value={v}>{v.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div>
              <label>Scaling</label>
              <select value={scaling} disabled={locked} onChange={(e) => { setScaling(e.target.value); savePreprocess({ scaling: e.target.value }); }}>
                <option value="">Choose...</option>
                {SCALINGS.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
          </div>
          <div style={{ marginTop: 14 }}>
            <label>Optional Features (toggle on to include)</label>
            {dataset.toggle_features.map((f) => (
              <button key={f} className={`chip ${featureFlags[f] ? "toggle-on" : ""}`} disabled={locked} onClick={() => toggleFeature(f)}>
                {f} {featureFlags[f] ? "\u2713 included" : "excluded"}
              </button>
            ))}
            <div className="help-text">Core features are always included. These optional ones may or may not belong.</div>
          </div>
        </div>
      </div>
    );
  }

  function renderForge() {
    return (
      <div className={`chamber-view forge`}>
        <div className="chamber-view-header">
          <span className="chamber-title">03. Model Forge</span>
          <span className="chamber-subtitle">Build</span>
        </div>
        <ChamberNav current="forge" />
        <div className="panel forge">
          <div className="panel-title">Build Model</div>
          <label>Model</label>
          <div style={{ marginBottom: 10 }}>
            {MODELS.map((m) => (
              <button key={m} className={`chip ${model === m ? "selected" : ""}`} disabled={locked} onClick={() => setModel(m)}>
                {m.replace(/_/g, " ")}
              </button>
            ))}
          </div>
          {model && reference && <div className="help-text" style={{ marginBottom: 10 }}>{reference.models[model]}</div>}

          <label>Primary Metric</label>
          <div style={{ marginBottom: 14 }}>
            {METRICS.map((m) => (
              <button key={m} className={`chip ${metric === m ? "selected" : ""}`} disabled={locked} onClick={() => setMetric(m)}>
                {m} <HelpTip text={reference ? reference.metrics[m] : ""} />
              </button>
            ))}
          </div>

          <button className="btn primary" onClick={runModel} disabled={locked || runningModel}>
            {runningModel ? "Running..." : "RUN MODEL"}
          </button>

          {state.last_run_result && (
            <div className="result-grid">
              <div className="result-box"><div className="val">{(state.last_run_result.accuracy * 100).toFixed(1)}%</div><div className="lbl">Accuracy</div></div>
              <div className="result-box"><div className="val">{(state.last_run_result.precision * 100).toFixed(1)}%</div><div className="lbl">Precision</div></div>
              <div className="result-box"><div className="val">{(state.last_run_result.recall * 100).toFixed(1)}%</div><div className="lbl">Recall</div></div>
              <div className="result-box"><div className="val">{(state.last_run_result.f1 * 100).toFixed(1)}%</div><div className="lbl">F1</div></div>
            </div>
          )}
        </div>

        {experiments.length > 0 && (
          <div className="panel forge">
            <div className="panel-title">Experiment History</div>
            <table>
              <thead><tr><th>#</th><th>Model</th><th>Imputation</th><th>Scaling</th><th>Metric</th><th>Accuracy</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead>
                <tbody>
                  {experiments.map((e, i) => (
                    <tr key={e.id}>
                      <td>{i + 1}</td>
                      <td>{e.config.model}</td>
                      <td>{e.config.imputation}</td>
                      <td>{e.config.scaling}</td>
                      <td>{e.config.primary_metric}</td>
                      <td>{(e.result.accuracy * 100).toFixed(1)}%</td>
                      <td>{(e.result.precision * 100).toFixed(1)}%</td>
                      <td>{(e.result.recall * 100).toFixed(1)}%</td>
                      <td>{(e.result.f1 * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
            </table>
          </div>
        )}

        {round === 2 && blackbox && (
          <div className="panel forge">
            <div className="panel-title">Black Box Challenge</div>
            <p>{blackbox.prompt}</p>
            {!bbFeedback ? (
              <div>{blackbox.options.map((o) => (
                <button key={o} className="chip" disabled={locked || blackbox.answered} onClick={() => answerBlackbox(o)}>{o}</button>
              ))}</div>
            ) : (
              <div className={bbFeedback.correct ? "success-box" : "error-box"}>
                {bbFeedback.correct ? "Correct." : "Not quite."} {bbFeedback.concept}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  function renderDeploy() {
    const checklist = [
      { label: "Core Requirements (imputation + scaling)", done: !!(imputation && scaling) },
      { label: "Model Performance (at least one run)", done: !!state.last_run_result },
      { label: "Twist Requirements", done: !twist.released || twistAcked },
    ];
    const allDone = checklist.every((c) => c.done);

    return (
      <div className={`chamber-view deploy`}>
        <div className="chamber-view-header">
          <span className="chamber-title">04. Deployment Chamber</span>
          <span className="chamber-subtitle">Deploy {"\u00b7"} Validate {"\u00b7"} Submit</span>
        </div>
        <ChamberNav current="deploy" />

        <div className="panel deploy">
          <div className="panel-title">Requirements Checklist</div>
          <div className="checklist">
            {checklist.map((c) => (
              <div key={c.label} className={`checklist-item ${c.done ? "done" : ""}`}>
                <span className="mark">{c.done ? "\u2713" : ""}</span>
                {c.label}
              </div>
            ))}
          </div>

          {state.last_run_result && (
            <div className="result-grid">
              <div className="result-box"><div className="val">{(state.last_run_result.accuracy * 100).toFixed(1)}%</div><div className="lbl">Accuracy</div></div>
              <div className="result-box"><div className="val">{(state.last_run_result.precision * 100).toFixed(1)}%</div><div className="lbl">Precision</div></div>
              <div className="result-box"><div className="val">{(state.last_run_result.recall * 100).toFixed(1)}%</div><div className="lbl">Recall</div></div>
              <div className="result-box"><div className="val">{(state.last_run_result.f1 * 100).toFixed(1)}%</div><div className="lbl">F1</div></div>
            </div>
          )}

          <p style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 16 }}>
            Submitting locks your workspace permanently. Only your last saved configuration is evaluated.
          </p>
          <button className="btn primary" onClick={handleSubmit} disabled={locked || !allDone}>
            {state.submitted ? "SUBMITTED" : "DEPLOY MODEL"}
          </button>
          {!allDone && !state.submitted && (
            <div className="help-text" style={{ marginTop: 8 }}>Complete the checklist above before deploying.</div>
          )}

          {state.submitted && (
            <div className="trophy-box">
              <div className="icon">{"\ud83c\udfc6"}</div>
              <div className="label">Mission Complete</div>
            </div>
          )}
        </div>
      </div>
    );
  }

  const currentBg = showBrief
    ? "/assets/bg-brief.jpg"
    : activeChamber === null
      ? "/assets/bg-hub.jpg"
      : CHAMBER_BG[activeChamber];

  return (
    <PageBackground src={currentBg} overlay={activeChamber === null && !showBrief ? 0.2 : 0.3}>
      <div className="mission-topbar" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
        <div>
          <h2 style={{ margin: 0 }}>{teamName}</h2>
          <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 2 }}>
            Round {round} {"\u00b7"} Room {roomKey}
            {locked && !state.submitted && <span className="badge danger" style={{ marginLeft: 8 }}>LOCKED</span>}
          </div>
        </div>
        <div className={`timer ${timerClass}`}>TIME: {fmtTime(remaining)}</div>
      </div>

      {error && <div className="error-box">{error}</div>}
      {notice && <div className="success-box">{notice}</div>}
      {tabSwitchWarning && <div className="error-box">{tabSwitchWarning}</div>}

      {twist.released && (
        <div className="twist-sidebar">
          <div>
            <div className="label">{"\u26a0"} Mission Update</div>
            <strong>{twist.headline}</strong>
          </div>
          {twistAcked ? <span className="badge green">Acknowledged</span> : <span className="badge warning">Pending</span>}
        </div>
      )}

      {activeChamber === null ? renderHub() : null}
      {activeChamber === "lab" ? renderLab() : null}
      {activeChamber === "prep" ? renderPrep() : null}
      {activeChamber === "forge" ? renderForge() : null}
      {activeChamber === "deploy" ? renderDeploy() : null}

      {showBrief && (
        <div className="modal-overlay">
          <div className="modal-box">
            <div className="modal-title">Mission Brief {"\u2014"} Round {round}</div>
            <p>{dataset.brief}</p>
            <div className="modal-stats">
              <div><div className="stat-val">{fmtTime(missionDuration)}</div><div className="stat-lbl">Time Limit</div></div>
              <div><div className="stat-val">UNRELIABLE</div><div className="stat-lbl">System Status</div></div>
              <div><div className="stat-val">RESTORE</div><div className="stat-lbl">Objective</div></div>
            </div>
            <button className="btn primary" style={{ width: "100%", padding: 14 }} onClick={() => setShowBrief(false)}>
              BEGIN MISSION &rarr;
            </button>
          </div>
        </div>
      )}

      {twistBlocking && (
        <div className="modal-overlay">
          <div className="modal-box twist">
            <div className="modal-title">{"\u26a0"} Mission Update</div>
            <strong style={{ display: "block", marginBottom: 8, fontSize: 15 }}>{twist.headline}</strong>
            <p>{twist.detail}</p>
            <button className="btn primary" style={{ width: "100%", padding: 14, marginTop: 10 }} onClick={() => ackTwist(true, true)} disabled={locked}>
              I UNDERSTAND
            </button>
          </div>
        </div>
      )}
    </PageBackground>
  );
}