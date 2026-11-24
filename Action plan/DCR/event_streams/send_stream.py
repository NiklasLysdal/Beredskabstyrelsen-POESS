"""Send an ordered event & telemetry stream to Siddhi input endpoints to simulate the Action Plan To-Be DCR process."""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SUPPORTED_ACTIONS = {
    "ArriveOnScene",
    "SurveyForFire",
    "IdentifySpreadingPaths",
    "DefineMMI",
    "ConductRiskAssessment",
    "ChangeInWindDirection",
    "EstablishLookouts",
    "EstablishAnchorPoint",
    "EstablishSecureCommunicationSystem",
    "EstablishEscapeRoutes",
    "DistanceToFire",
    "DrawUnitsOnMap",
    "SetupSensors",
    "Humidity",
    "InitiateDirectAttack",
    "ChooseAttackMethod",
    "InitiateIndirectAttack",
    "BreachesControlLine",
    "EstablishControlLine",
    "EvacuateCrewToSafeZone",
    "OccursBehindCrew",
    "FlameHeight",
    "StopDirectAttack",
    "StopIndirectAttack",
}


def resolve_stream_target(base_url, event):
    """Determine which Siddhi HTTP endpoint and payload shape to use for an event."""
    root = base_url.rsplit("/", 1)[0] if "/" in base_url else base_url
    if "humidity" in event:
        return f"{root}/humidity", f"humidity={event['humidity']}%", {
            "incident_id": event["incident_id"],
            "humidity": int(event["humidity"]),
        }
    if "wind_direction" in event:
        return f"{root}/wind", f"wind_direction={event['wind_direction']}", {
            "incident_id": event["incident_id"],
            "wind_direction": str(event["wind_direction"]),
        }

    action = event["action"]
    val = str(event.get("value", ""))
    label = f"{action} (value={val})" if val else action
    return f"{root}/actor", label, {
        "incident_id": event["incident_id"],
        "action": action,
        "value": val,
    }


def load_events(path, validate_actions=True):
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError("A .json stream file must contain an array of events")
        events = parsed
    else:
        events = [json.loads(line) for line in text.splitlines() if line.strip()]

    if not events:
        raise ValueError("The stream file does not contain any events")

    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise ValueError(f"Event {index} must be a JSON object")

        incident_id = event.get("incident_id")
        if not incident_id or not isinstance(incident_id, str):
            raise ValueError(f"Event {index} must have a non-empty string 'incident_id'")

        is_sensor = any(k in event for k in ("humidity", "wind_direction"))
        if is_sensor:
            continue

        action = event.get("action")
        if not action or not isinstance(action, str):
            raise ValueError(
                f"Event {index} must have either 'action' or one of ('humidity', 'wind_direction')"
            )

        if validate_actions and action not in SUPPORTED_ACTIONS:
            actions = ", ".join(sorted(SUPPORTED_ACTIONS))
            raise ValueError(
                f"Event {index} has unsupported action '{action}'. Use --no-validate to bypass, or one of:\n{actions}"
            )

    return events


def send_event(url, payload, timeout):
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        response_body = response.read().decode("utf-8")
        return response.status, response_body


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send an ordered JSON/JSONL event & sensor stream to Siddhi for the Action Plan DCR simulation."
    )
    parser.add_argument("file", type=Path, help="JSON array or JSONL event stream file")
    parser.add_argument(
        "--url",
        default=os.getenv("SIDDHI_URL", "http://localhost:7071/actor"),
        help="Base Siddhi input endpoint (default: %(default)s)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.6,
        help="Seconds to wait between events (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip action name validation against known Action Plan events",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print events without sending them",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.delay < 0 or args.timeout <= 0:
        raise ValueError("--delay must be non-negative and --timeout must be positive")
    if not args.file.is_file():
        raise FileNotFoundError(f"Stream file not found: {args.file}")

    events = load_events(args.file, validate_actions=not args.no_validate)
    total = len(events)
    print(f"Loaded {total} event(s) from {args.file}")

    for index, event in enumerate(events, start=1):
        incident_id = event["incident_id"]
        target_url, label, payload = resolve_stream_target(args.url, event)

        if args.dry_run:
            print(f"[{index}/{total}] {label} ({incident_id}) -> {target_url}")
        else:
            try:
                status, response = send_event(target_url, payload, args.timeout)
            except (HTTPError, URLError, TimeoutError) as error:
                print(f"[{index}/{total}] failed: {error}", file=sys.stderr)
                return 1
            print(
                f"[{index}/{total}] {label} ({incident_id}) -> {target_url} [HTTP {status}] {response}"
            )

        if index < total and args.delay:
            # ArriveOnScene creates the case in DCR and calls back to Siddhi; give it time to complete
            sleep_time = max(args.delay, 2.5) if event.get("action") == "ArriveOnScene" else args.delay
            time.sleep(sleep_time)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
