"""Send an ordered event stream to the Siddhi input endpoint to simulate the Action Plan DCR process."""

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
    "A7",
    "Humidity",
    "InitiateDirectAttack",
    "ChooseAttackMethod",
    "InitiateIndirectAttack",
    "BreachesControlLine",
    "EstablishControlLine",
    "EvacuateCrewToSafeZone",
    "OccursBehindCrew",
    "FlameHeight",
}

ENVIRONMENT_ACTIONS = {
    "ChangeInWindDirection",
    "Humidity",
    "FlameHeight",
    "OccursBehindCrew",
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

        action = event.get("action")
        if not action or not isinstance(action, str):
            raise ValueError(f"Event {index} must have a non-empty string 'action'")

        if validate_actions and action not in SUPPORTED_ACTIONS:
            actions = ", ".join(sorted(SUPPORTED_ACTIONS))
            raise ValueError(
                f"Event {index} has unsupported action '{action}'. Use --no-validate to bypass, or one of:\n{actions}"
            )

    return events


def send_event(url, event, timeout):
    body = json.dumps(event).encode("utf-8")
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
        description="Send an ordered JSON/JSONL event stream to Siddhi for the Action Plan DCR simulation."
    )
    parser.add_argument("file", type=Path, help="JSON array or JSONL event stream file")
    parser.add_argument(
        "--url",
        default=os.getenv("SIDDHI_URL", "http://localhost:7071/actor"),
        help="Siddhi actor input endpoint (default: %(default)s)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
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
        action = event["action"]
        incident_id = event["incident_id"]
        target_url = args.url
        if action in ENVIRONMENT_ACTIONS and target_url.endswith("/actor"):
            target_url = target_url[:-6] + "/environment"

        if args.dry_run:
            print(f"[{index}/{total}] {action} ({incident_id}) -> {target_url}")
        else:
            try:
                status, response = send_event(target_url, event, args.timeout)
            except (HTTPError, URLError, TimeoutError) as error:
                print(f"[{index}/{total}] failed: {error}", file=sys.stderr)
                return 1
            print(
                f"[{index}/{total}] {action} ({incident_id}) -> HTTP {status} {response}"
            )

        if index < total and args.delay:
            time.sleep(args.delay)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
