"""Strictly verify an exact Neophytic Rooms public result and provenance."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Any


OBSERVATION_KEYS = {
    "done",
    "reward",
    "metadata",
    "current_room",
    "committed",
    "failure_last",
    "room_visited",
    "room_inspected",
    "room_known_connects",
    "room_locked",
    "room_haskey",
    "room_exit",
    "current_keys",
    "actions_remaining",
    "obs_inspect_weight",
}


def fail(message: str) -> None:
    raise SystemExit(f"Gate failed: {message}")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def parse_json(text: str, name: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda value: fail(f"non-finite number {value!r}"),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"cannot parse strict JSON for {name}: {exc}")


def load_json(path: Path) -> Any:
    try:
        return parse_json(path.read_text(encoding="utf-8"), str(path))
    except OSError as exc:
        fail(f"cannot read {path}: {exc}")


def require_int(value: Any, expected: int, name: str) -> None:
    if type(value) is not int or value != expected:
        fail(f"{name}={value!r}, expected integer {expected}")


def require_float(value: Any, expected: float, name: str) -> None:
    if type(value) is not float or not math.isfinite(value) or value != expected:
        fail(f"{name}={value!r}, expected float {expected!r}")


def require_vector(
    value: Any,
    expected: list[int],
    name: str,
) -> None:
    if not isinstance(value, list) or any(type(item) is not int for item in value):
        fail(f"{name} is not an integer list")
    if value != expected:
        fail(f"{name}={value!r}, expected {expected!r}")


def decode_encoding(encoding: Any) -> dict[str, Any]:
    if not isinstance(encoding, str) or not re.fullmatch(r"[0-9a-f]{25}", encoding):
        fail(f"invalid encoding syntax: {encoding!r}")
    bits = bin(int(encoding, 16))[2:].zfill(100)
    start_room = int(bits[:4], 2)

    included: list[int] = []
    locked: list[int] = []
    has_key: list[int] = []
    exits: list[int] = []
    index = 4
    for _ in range(8):
        included.append(int(bits[index]))
        locked.append(int(bits[index + 1]))
        has_key.append(int(bits[index + 2]))
        exits.append(int(bits[index + 3]))
        index += 4

    connections: list[list[int]] = []
    for _ in range(8):
        row = [int(value) for value in bits[index : index + 8]]
        connections.append(row)
        index += 8

    room_count = sum(included)
    if room_count not in (2, 3):
        fail(f"encoding has {room_count} included rooms")
    expected_included = [1] * room_count + [0] * (8 - room_count)
    if included != expected_included:
        fail(f"encoding has non-contiguous included rooms: {included!r}")
    if start_room >= room_count:
        fail(f"start room {start_room} is excluded")
    if any(locked) or any(has_key):
        fail("tutorial encoding unexpectedly contains a lock or key")
    if sum(exits) != 1:
        fail(f"encoding exit count={sum(exits)}")
    exit_room = exits.index(1)
    if exit_room >= room_count or exit_room == start_room:
        fail(f"invalid tutorial start/exit pair: {start_room}/{exit_room}")

    edge_count = 0
    for left in range(8):
        for right in range(8):
            value = connections[left][right]
            if value not in (0, 1):
                fail("connection matrix is not binary")
            if value != connections[right][left]:
                fail("connection matrix is not symmetric")
            if left == right and value:
                fail("connection matrix has a self-loop")
            if (left >= room_count or right >= room_count) and value:
                fail("connection references an excluded room")
            if left < right:
                edge_count += value
    if edge_count != room_count - 1:
        fail(f"tutorial graph is not a tree: edges={edge_count}")

    reached = {start_room}
    frontier = [start_room]
    while frontier:
        room = frontier.pop()
        for neighbor, connected in enumerate(connections[room]):
            if connected and neighbor not in reached:
                reached.add(neighbor)
                frontier.append(neighbor)
    if reached != set(range(room_count)):
        fail(f"tutorial graph is disconnected: reached={sorted(reached)!r}")

    return {
        "start": start_room,
        "exit": exit_room,
        "room_count": room_count,
        "connections": connections,
    }


def verify_observation_shape(observation: Any, name: str) -> None:
    if not isinstance(observation, dict) or set(observation) != OBSERVATION_KEYS:
        fail(f"{name} keys mismatch")
    if type(observation["done"]) is not bool:
        fail(f"{name}.done is not a boolean")
    if observation["metadata"] != {}:
        fail(f"{name}.metadata={observation['metadata']!r}")
    for key in (
        "current_room",
        "committed",
        "failure_last",
        "current_keys",
        "actions_remaining",
    ):
        if type(observation[key]) is not int:
            fail(f"{name}.{key} is not an integer")
    for key in ("reward", "obs_inspect_weight"):
        value = observation[key]
        if type(value) is not float or not math.isfinite(value):
            fail(f"{name}.{key} is not a finite float")
    for key in ("room_visited", "room_inspected", "room_locked", "room_haskey", "room_exit"):
        value = observation[key]
        if (
            not isinstance(value, list)
            or len(value) != 8
            or any(type(item) is not int for item in value)
        ):
            fail(f"{name}.{key} is not an eight-integer vector")
    matrix = observation["room_known_connects"]
    if (
        not isinstance(matrix, list)
        or len(matrix) != 8
        or any(
            not isinstance(row, list)
            or len(row) != 8
            or any(type(item) is not int for item in row)
            for row in matrix
        )
    ):
        fail(f"{name}.room_known_connects is not an 8x8 integer matrix")


def verify_state(
    observation: dict[str, Any],
    *,
    name: str,
    current_room: int,
    committed: int,
    failure_last: int,
    visited: set[int],
    actions_remaining: int,
    reward: float,
    done: bool,
) -> None:
    verify_observation_shape(observation, name)
    require_int(observation["current_room"], current_room, f"{name}.current_room")
    require_int(observation["committed"], committed, f"{name}.committed")
    require_int(observation["failure_last"], failure_last, f"{name}.failure_last")
    require_int(
        observation["actions_remaining"],
        actions_remaining,
        f"{name}.actions_remaining",
    )
    require_int(observation["current_keys"], 0, f"{name}.current_keys")
    require_float(observation["reward"], reward, f"{name}.reward")
    require_float(observation["obs_inspect_weight"], 3.0, f"{name}.obs_inspect_weight")
    if observation["done"] is not done:
        fail(f"{name}.done={observation['done']!r}, expected {done!r}")

    expected_visited = [int(room in visited) for room in range(8)]
    require_vector(observation["room_visited"], expected_visited, f"{name}.room_visited")
    require_vector(observation["room_inspected"], [0] * 8, f"{name}.room_inspected")
    for key in ("room_locked", "room_haskey", "room_exit"):
        require_vector(observation[key], [-1] * 8, f"{name}.{key}")
    if observation["room_known_connects"] != [[-1] * 8 for _ in range(8)]:
        fail(f"{name}.room_known_connects unexpectedly reveals graph data")


def verify_response_and_action(
    response_entry: Any,
    action_entry: Any,
    *,
    expected_step: int,
    expected_command: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(response_entry, dict) or set(response_entry) != {
        "step",
        "solver_response",
    }:
        fail(f"step {expected_step} solver-response entry mismatch")
    require_int(response_entry["step"], expected_step, "solver_response.step")
    response_text = response_entry["solver_response"]
    if not isinstance(response_text, str):
        fail(f"step {expected_step} solver_response is not text")
    response = parse_json(response_text, f"step {expected_step} solver_response")

    if not isinstance(action_entry, dict) or set(action_entry) != {"step", "action"}:
        fail(f"step {expected_step} action entry mismatch")
    require_int(action_entry["step"], expected_step, "action.step")
    action = action_entry["action"]
    if not isinstance(action, dict) or set(action) != {
        "metadata",
        "command",
        "target_room",
    }:
        fail(f"step {expected_step} action payload mismatch: {action!r}")
    if action["metadata"] != {} or action["command"] != expected_command:
        fail(f"step {expected_step} action={action!r}")

    expected_response: dict[str, Any] = {"command": expected_command.upper()}
    if expected_command == "move":
        expected_response["target_room"] = action["target_room"]
    if response != expected_response:
        fail(
            f"step {expected_step} response={response!r}, "
            f"expected {expected_response!r}"
        )
    return response, action


def verify_results(document: Any, participant_id: str) -> list[dict[str, Any]]:
    if not isinstance(document, dict) or set(document) != {"participants", "results"}:
        fail(f"unexpected top-level result: {document!r}")
    if document["participants"] != {"solver": participant_id}:
        fail(f"participants={document['participants']!r}")
    if not isinstance(document["results"], list) or len(document["results"]) != 1:
        fail("expected exactly one benchmark result")

    aggregate = document["results"][0]
    aggregate_keys = {
        "total_runs",
        "successful_runs",
        "errored_runs",
        "success_rate",
        "avg_loss",
        "avg_steps",
        "max_steps",
        "per_run_results",
    }
    if not isinstance(aggregate, dict) or set(aggregate) != aggregate_keys:
        fail(f"unexpected aggregate result: {aggregate!r}")
    for key, expected in (
        ("total_runs", 5),
        ("successful_runs", 5),
        ("errored_runs", 0),
        ("max_steps", 30),
    ):
        require_int(aggregate[key], expected, key)
    require_float(aggregate["success_rate"], 1.0, "success_rate")

    runs = aggregate["per_run_results"]
    if not isinstance(runs, list) or len(runs) != 5:
        fail("per_run_results must contain exactly five runs")

    total_steps = 0
    total_loss = 0.0
    logged_actions: list[dict[str, Any]] = []
    run_keys = {
        "run_index",
        "success",
        "total_loss",
        "steps_taken",
        "max_steps",
        "encoding",
        "final_observation",
        "conversation_history",
    }

    for expected_index, run in enumerate(runs):
        if not isinstance(run, dict) or set(run) != run_keys:
            fail(f"run {expected_index} keys mismatch")
        require_int(run["run_index"], expected_index, f"run {expected_index}.run_index")
        if run["success"] is not True:
            fail(f"run {expected_index} did not succeed")
        steps = run["steps_taken"]
        if type(steps) is not int or not 1 <= steps <= 9:
            fail(f"run {expected_index}.steps_taken={steps!r}")
        require_int(run["max_steps"], 30, f"run {expected_index}.max_steps")
        require_float(run["total_loss"], float(-steps), f"run {expected_index}.total_loss")

        room_system = decode_encoding(run["encoding"])
        start_room = room_system["start"]
        exit_room = room_system["exit"]
        connections = room_system["connections"]

        history = run["conversation_history"]
        expected_history_length = 1 + 3 * (steps + 1)
        if not isinstance(history, list) or len(history) != expected_history_length:
            fail(
                f"run {expected_index} history length="
                f"{len(history) if isinstance(history, list) else None}, "
                f"expected {expected_history_length}"
            )

        initial = history[0]
        if not isinstance(initial, dict) or set(initial) != {"step", "observation", "prompt"}:
            fail(f"run {expected_index} initial history entry mismatch")
        require_int(initial["step"], 0, f"run {expected_index} initial step")
        prompt = initial["prompt"]
        if not isinstance(prompt, str) or not prompt.startswith(
            "You are solving a Rooms navigation puzzle. Current state (Move 0):"
        ):
            fail(f"run {expected_index} initial prompt mismatch")
        verify_state(
            initial["observation"],
            name=f"run {expected_index} initial observation",
            current_room=start_room,
            committed=0,
            failure_last=0,
            visited={start_room},
            actions_remaining=30,
            reward=-0.0,
            done=False,
        )

        current_room = start_room
        visited = {start_room}
        for action_index in range(steps + 1):
            offset = 1 + 3 * action_index
            expected_command = "commit" if action_index == 0 else "move"
            _, action = verify_response_and_action(
                history[offset],
                history[offset + 1],
                expected_step=action_index,
                expected_command=expected_command,
            )

            observation_entry = history[offset + 2]
            if not isinstance(observation_entry, dict) or set(observation_entry) != {
                "step",
                "observation",
                "loss",
            }:
                fail(f"run {expected_index} step {action_index} observation entry mismatch")
            require_int(
                observation_entry["step"],
                action_index + 1,
                f"run {expected_index} observation step",
            )

            if action_index == 0:
                if action["target_room"] is not None:
                    fail(f"run {expected_index} commit has a target")
                expected_failure = 0
                expected_remaining = 30
                expected_reward = -0.0
                expected_done = False
                logged_action = {"command": "COMMIT"}
            else:
                target = action["target_room"]
                if type(target) is not int or target not in range(8):
                    fail(f"run {expected_index} step {action_index} target={target!r}")
                if connections[current_room][target] == 1:
                    current_room = target
                    visited.add(target)
                    expected_failure = 0
                else:
                    expected_failure = 1
                expected_remaining = 30 - action_index
                expected_reward = float(-action_index)
                expected_done = current_room == exit_room
                logged_action = {"command": "MOVE", "target_room": target}

            if expected_done != (action_index == steps):
                fail(
                    f"run {expected_index} terminal position occurs at action "
                    f"{action_index}, expected {steps}"
                )
            verify_state(
                observation_entry["observation"],
                name=f"run {expected_index} action {action_index} observation",
                current_room=current_room,
                committed=1,
                failure_last=expected_failure,
                visited=visited,
                actions_remaining=expected_remaining,
                reward=expected_reward,
                done=expected_done,
            )
            require_float(
                observation_entry["loss"],
                expected_reward,
                f"run {expected_index} action {action_index}.loss",
            )
            logged_actions.append(logged_action)

        if current_room != exit_room:
            fail(f"run {expected_index} ended in room {current_room}, not exit {exit_room}")
        verify_observation_shape(
            run["final_observation"],
            f"run {expected_index} final_observation",
        )
        if run["final_observation"] != history[-1]["observation"]:
            fail(f"run {expected_index} final_observation does not match history")

        total_steps += steps
        total_loss += run["total_loss"]

    require_float(aggregate["avg_steps"], total_steps / 5, "avg_steps")
    require_float(aggregate["avg_loss"], total_loss / 5, "avg_loss")
    return logged_actions


def verify_provenance(provenance: Any) -> None:
    if not isinstance(provenance, dict) or set(provenance) != {
        "image_digests",
        "timestamp",
        "github_actions",
    }:
        fail(f"unexpected provenance document: {provenance!r}")

    expected_digests = {
        "green-agent": os.environ["GREEN_IMAGE"],
        "solver": os.environ["PARTICIPANT_IMAGE"],
        "agentbeats-client": os.environ["CLIENT_IMAGE"],
    }
    if provenance["image_digests"] != expected_digests:
        fail(f"image digests={provenance['image_digests']!r}")
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
        provenance.get("timestamp", ""),
    ):
        fail(f"timestamp={provenance.get('timestamp')!r}")

    expected_actions = {
        "run_url": (
            f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
            f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        ),
        "run_logs_url": (
            f"{os.environ['GITHUB_API_URL']}/repos/{os.environ['GITHUB_REPOSITORY']}"
            f"/actions/runs/{os.environ['GITHUB_RUN_ID']}/logs"
        ),
        "ref": os.environ["GITHUB_REF"],
        "sha": os.environ["GITHUB_SHA"],
        "repository_url": (
            f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
        ),
        "workflow_ref": os.environ["GITHUB_WORKFLOW_REF"],
        "workflow_sha": os.environ["GITHUB_WORKFLOW_SHA"],
    }
    if provenance["github_actions"] != expected_actions:
        fail(f"GitHub Actions provenance={provenance['github_actions']!r}")


def verify_logs(
    green_log: str,
    participant_log: str,
    client_log: str,
    expected_actions: list[dict[str, Any]],
) -> None:
    combined = "\n".join((green_log, participant_log, client_log))
    for marker in (
        "Traceback (most recent call last)",
        "rooms_solver_error=",
        "ERROR:",
    ):
        if marker in combined:
            fail(f"runtime logs contain {marker!r}")

    action_lines = []
    for line in participant_log.splitlines():
        match = re.fullmatch(r"rooms_solver_action=(\{.*\})", line)
        if match:
            action_lines.append(parse_json(match.group(1), "participant action log"))
    if action_lines != expected_actions:
        fail(f"participant action log={action_lines!r}, expected={expected_actions!r}")

    participant_posts = sum(
        '"POST / HTTP/1.1" 200 OK' in line
        for line in participant_log.splitlines()
    )
    if participant_posts != len(expected_actions):
        fail(
            f"participant successful POST count={participant_posts}, "
            f"expected {len(expected_actions)}"
        )
    green_posts = sum(
        '"POST / HTTP/1.1" 200 OK' in line
        for line in green_log.splitlines()
    )
    if green_posts != 1:
        fail(f"green successful POST count={green_posts}, expected 1")
    if "Deterministic Rooms solver running on 0.0.0.0:9009" not in participant_log:
        fail("participant did not report the expected leaderboard endpoint")
    if "Successful:      5" not in client_log or "Success Rate:    100.0%" not in client_log:
        fail("client log does not contain the exact success summary")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--green-log", type=Path, required=True)
    parser.add_argument("--participant-log", type=Path, required=True)
    parser.add_argument("--client-log", type=Path, required=True)
    args = parser.parse_args()

    expected_actions = verify_results(
        load_json(args.results),
        os.environ["NEOPHYTIC_ROOMS_AGENT_ID"],
    )
    verify_provenance(load_json(args.provenance))
    verify_logs(
        args.green_log.read_text(encoding="utf-8"),
        args.participant_log.read_text(encoding="utf-8"),
        args.client_log.read_text(encoding="utf-8"),
        expected_actions,
    )
    print(
        "Exact Neophytic Rooms result verified: "
        f"5/5 generated systems, {len(expected_actions) - 5} execution actions"
    )


if __name__ == "__main__":
    main()
