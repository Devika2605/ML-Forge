"""
End-to-end test: simulates a full ML Forge event with multiple teams,
including resume-on-reconnect, both rounds, the twist mechanic, precomputed
model lookups, deterministic scoring, admin flow, and the leaderboard.

Run with a live server on localhost:8000:
    python3 tests/test_full_event.py
"""
import httpx
import time
import sys

BASE = "http://localhost:8000"
ROOM = "TEST_ROOM_1"


def check(cond, msg):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {msg}")
    if not cond:
        FAILURES.append(msg)


FAILURES = []


def main():
    client = httpx.Client(base_url=BASE, timeout=10)

    # --- Room setup ---
    r = client.post("/api/rooms", json={"room_key": ROOM, "name": "Test Room"})
    check(r.status_code == 200, "Create room")

    r = client.get(f"/api/rooms/{ROOM}")
    check(r.status_code == 200 and r.json()["status"] == "PREPARATION", "Room starts in PREPARATION")

    # --- Team registration ---
    team_names = [f"Team_{i:02d}" for i in range(1, 13)]  # 12 fake teams
    for name in team_names:
        r = client.post("/api/teams/register", json={"room_key": ROOM, "team_name": name})
        check(r.status_code == 200 and r.json()["created"] is True, f"Register {name} (created)")

    # re-register one team -> should resume, not duplicate
    r = client.post("/api/teams/register", json={"room_key": ROOM, "team_name": "Team_01"})
    check(r.status_code == 200 and r.json()["resumed"] is True, "Re-registering Team_01 resumes, not duplicates")

    r = client.get(f"/api/rooms/{ROOM}")
    check(r.json()["team_count"] == 12, "Exactly 12 teams exist after resume attempt (no duplicate)")

    # --- Start Round 1 ---
    r = client.post(f"/api/admin/{ROOM}/start-round1")
    check(r.status_code == 200, "Admin starts Round 1")

    r = client.get(f"/api/rooms/{ROOM}")
    check(r.json()["round1"]["time_remaining"] > 1700, "Round 1 timer is running (~30 min remaining)")

    # --- Simulate resume/persistence: Team_01 opens a panel, "disconnects", reconnects ---
    r = client.post("/api/mission/panel-open", json={
        "room_key": ROOM, "team_name": "Team_01", "round_number": 1, "panel": "missing_values"
    })
    check(r.status_code == 200, "Team_01 opens missing_values panel")

    # simulate reconnect: re-register and check panel state survived
    r = client.post("/api/teams/register", json={"room_key": ROOM, "team_name": "Team_01"})
    resumed_state = r.json()["round1_state"]
    check("missing_values" in resumed_state["panels_opened"], "RESUME: panel state survives re-registration")

    # --- Investigate dataset (all teams look at it) ---
    r = client.get(f"/api/mission/{ROOM}/Team_02/1/investigate")
    check(r.status_code == 200 and r.json()["rows"] > 0, "Investigate endpoint returns dataset summary")
    inv = r.json()
    check("Leakage_Feature" in inv["columns"], "Dataset exposes Leakage_Feature column for investigation")
    check(inv["missing_values_pct"]["Income"] > 5, "Missing-value trap is present and visible (Income)")

    # --- Team A: does everything right (should score well) ---
    good_team = "Team_01"
    for panel in ["missing_values", "class_distribution", "feature_preview"]:
        client.post("/api/mission/panel-open", json={"room_key": ROOM, "team_name": good_team, "round_number": 1, "panel": panel})

    r = client.post("/api/mission/preprocess", json={
        "room_key": ROOM, "team_name": good_team, "round_number": 1,
        "imputation": "median", "scaling": "standardize",
        "feature_flags": {"Patient_ID": False, "Leakage_Feature": False},
    })
    check(r.status_code == 200, "Good team sets correct preprocessing (drops leakage + ID)")

    r = client.post("/api/mission/run-model", json={
        "room_key": ROOM, "team_name": good_team, "round_number": 1,
        "model": "logistic_regression", "primary_metric": "recall",
    })
    check(r.status_code == 200, "Good team runs model successfully via precomputed lookup")
    good_result = r.json()["result"]
    check("recall" in good_result, "Model run returns recall/precision/f1/accuracy")

    # --- Team B: keeps leakage + ID (should score worse) ---
    bad_team = "Team_02"
    r = client.post("/api/mission/preprocess", json={
        "room_key": ROOM, "team_name": bad_team, "round_number": 1,
        "imputation": "mode", "scaling": "none",
        "feature_flags": {"Patient_ID": True, "Leakage_Feature": True},
    })
    r = client.post("/api/mission/run-model", json={
        "room_key": ROOM, "team_name": bad_team, "round_number": 1,
        "model": "random_forest", "primary_metric": "accuracy",
    })
    check(r.status_code == 200, "Bad team runs model (keeps leakage/ID)")
    bad_result = r.json()["result"]
    check(bad_result["recall"] > good_result["recall"] or bad_result["f1"] > 0.7,
          "Leakage-retaining config shows suspiciously strong performance (trap is visible)")

    # --- Everyone else runs something minimal so they have a score ---
    for name in team_names[2:]:
        client.post("/api/mission/preprocess", json={
            "room_key": ROOM, "team_name": name, "round_number": 1,
            "imputation": "mean", "scaling": "none",
            "feature_flags": {"Patient_ID": False, "Leakage_Feature": False},
        })
        client.post("/api/mission/run-model", json={
            "room_key": ROOM, "team_name": name, "round_number": 1,
            "model": "decision_tree", "primary_metric": "f1",
        })

    # --- Experiment history ---
    r = client.get(f"/api/mission/{ROOM}/{good_team}/1/experiments")
    check(r.status_code == 200 and len(r.json()) >= 1, "Experiment history is tracked per team")

    # --- Release twist ---
    r = client.post(f"/api/admin/{ROOM}/release-twist")
    check(r.status_code == 200, "Admin releases Round 1 twist")

    r = client.get(f"/api/mission/{ROOM}/{good_team}/1/twist")
    check(r.status_code == 200 and r.json()["released"] is True, "Twist is visible to teams after release")
    check("Recall" in r.json()["headline"], "Twist headline matches spec (focus on Recall)")

    # good team adapts correctly
    r = client.post("/api/mission/twist-ack", json={
        "room_key": ROOM, "team_name": good_team, "round_number": 1,
        "switched_metric": True, "did_feature_check": True,
    })
    check(r.status_code == 200, "Good team acknowledges twist")
    client.post("/api/mission/preprocess", json={
        "room_key": ROOM, "team_name": good_team, "round_number": 1,
        "feature_flags": {"Patient_ID": False, "Leakage_Feature": False},
    })
    r = client.post("/api/mission/run-model", json={
        "room_key": ROOM, "team_name": good_team, "round_number": 1,
        "model": "logistic_regression", "primary_metric": "recall",
    })
    check(r.status_code == 200, "Good team re-runs after twist with recall as primary metric")

    # bad team ignores the twist entirely (primary_metric stays accuracy)

    # --- Submit ---
    r = client.post("/api/mission/submit", json={"room_key": ROOM, "team_name": good_team, "round_number": 1})
    check(r.status_code == 200 and r.json()["submitted"] is True, "Good team submits Round 1")

    r = client.post("/api/mission/panel-open", json={"room_key": ROOM, "team_name": good_team, "round_number": 1, "panel": "x"})
    check(r.status_code == 423, "Locked team cannot make further changes after submission (423)")

    for name in team_names[1:]:
        client.post("/api/mission/submit", json={"room_key": ROOM, "team_name": name, "round_number": 1})

    # --- Lock + score Round 1 ---
    r = client.post(f"/api/admin/{ROOM}/lock-submissions")
    check(r.status_code == 200 and r.json()["teams_locked"] == 12, "Admin locks Round 1 for all 12 teams")

    r = client.post(f"/api/admin/{ROOM}/calculate-scores")
    check(r.status_code == 200 and r.json()["scored_teams"] == 12, "Scores calculated for all 12 teams")

    r = client.get(f"/api/leaderboard/{ROOM}?round_number=1")
    lb_payload = r.json()
    lb = lb_payload["rows"]
    check(lb_payload["round_number"] == 1, "Leaderboard reports round_number=1")
    check(len(lb) == 12, "Leaderboard has 12 entries after Round 1")
    check(lb[0]["rank"] == 1 and lb[0]["score"] >= lb[-1]["score"], "Leaderboard sorted descending")

    good_score = next(x for x in lb if x["team_name"] == good_team)["score"]
    bad_score = next(x for x in lb if x["team_name"] == bad_team)["score"]
    check(good_score > bad_score, f"Good team ({good_score}) outscores bad team ({bad_score}) — scoring engine rewards correct decisions")
    print(f"    -> good_team={good_score}, bad_team={bad_score}")

    # --- Advance top 10 ---
    r = client.post(f"/api/admin/{ROOM}/advance-top10")
    check(r.status_code == 200 and len(r.json()["advanced"]) == 10, "Top 10 of 12 teams advance to Round 2")
    advanced_names = [x["team_name"] for x in r.json()["advanced"]]
    check(good_team in advanced_names, "Good team is in the advancing top 10")

    # --- Round 2 ---
    r = client.post(f"/api/admin/{ROOM}/start-round2")
    check(r.status_code == 200, "Admin starts Round 2")

    # a non-qualified team should not be able to act in round 2 meaningfully (state still creatable, but let's confirm qualification flag)
    r = client.post("/api/teams/register", json={"room_key": ROOM, "team_name": bad_team if bad_team not in advanced_names else advanced_names[-1]})

    for name in advanced_names:
        for panel in ["missing_values", "class_distribution", "feature_preview"]:
            client.post("/api/mission/panel-open", json={"room_key": ROOM, "team_name": name, "round_number": 2, "panel": panel})
        client.post("/api/mission/preprocess", json={
            "room_key": ROOM, "team_name": name, "round_number": 2,
            "imputation": "median", "scaling": "standardize",
            "feature_flags": {"Transaction_ID": False, "Leakage_Feature": False},
        })
        client.post("/api/mission/run-model", json={
            "room_key": ROOM, "team_name": name, "round_number": 2,
            "model": "logistic_regression", "primary_metric": "precision",
        })

    r = client.post(f"/api/admin/{ROOM}/release-incident")
    check(r.status_code == 200, "Admin releases Round 2 incident")

    for name in advanced_names:
        client.post("/api/mission/twist-ack", json={
            "room_key": ROOM, "team_name": name, "round_number": 2,
            "switched_metric": True, "did_feature_check": True,
        })

    # black box challenge
    r = client.get(f"/api/mission/{ROOM}/{advanced_names[0]}/2/blackbox")
    check(r.status_code == 200 and "prompt" in r.json(), "Black Box question assigned")
    q = r.json()
    r = client.post("/api/mission/blackbox-answer", json={
        "room_key": ROOM, "team_name": advanced_names[0], "round_number": 2,
        "question_id": q["id"], "selected_option": q["options"][0],
    })
    check(r.status_code == 200, "Black Box answer submitted and graded")

    for name in advanced_names:
        client.post("/api/mission/submit", json={"room_key": ROOM, "team_name": name, "round_number": 2})

    r = client.post(f"/api/admin/{ROOM}/lock-final-submissions")
    check(r.status_code == 200, "Admin locks Round 2")

    r = client.post(f"/api/admin/{ROOM}/calculate-scores-round2")
    check(r.status_code == 200 and r.json()["scored_teams"] == 10, "Round 2 scores calculated for 10 finalists")

    r = client.get(f"/api/leaderboard/{ROOM}?round_number=2")
    lb2_payload = r.json()
    check(lb2_payload["round_number"] == 2, "Round 2 leaderboard reports round_number=2")
    check(len(lb2_payload["rows"]) == 10, "Round 2 leaderboard has exactly the 10 qualified teams")

    # Round 2 is scored fully independently of Round 1 — the winner is
    # ranked on the Round 2 score alone, with no blended "overall" score.
    r = client.get(f"/api/admin/{ROOM}/winner")
    winners = r.json()
    check(len(winners) == 10, "Winner list has 10 ranked finalists")
    check(winners[0]["rank"] == 1, "Winner list is ranked")
    check(all(winners[i]["round2_score"] >= winners[i + 1]["round2_score"] for i in range(len(winners) - 1)),
          "Winner list is ranked strictly by Round 2 score")
    print(f"    -> Winner: {winners[0]['team_name']} with Round 2 score {winners[0]['round2_score']}")

    # --- Admin live view sanity ---
    r = client.get(f"/api/admin/{ROOM}/live-view")
    check(r.status_code == 200, "Admin live view endpoint works")

    # --- Room isolation check: create a second room, confirm no leakage ---
    r = client.post("/api/rooms", json={"room_key": "TEST_ROOM_2", "name": "Second Room"})
    client.post("/api/teams/register", json={"room_key": "TEST_ROOM_2", "team_name": "Team_01"})
    r = client.get("/api/rooms/TEST_ROOM_2")
    check(r.json()["team_count"] == 1, "Second room is isolated — same team name doesn't clash across rooms")

    print()
    print("=" * 60)
    if FAILURES:
        print(f"{len(FAILURES)} CHECK(S) FAILED:")
        for f in FAILURES:
            print("  -", f)
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
