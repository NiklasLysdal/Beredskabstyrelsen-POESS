from flask import Flask, request, jsonify
import json
import requests
from dcr_helper import create_case, execute_event, get_enabled_events
from enum import Enum
from datetime import datetime, timezone

class EventID(str, Enum):
    ArriveOnScene = "ArriveOnScene"
    SurveyForFire = "SurveyForFire"
    IdentifySpreadingPaths = "IdentifySpreadingPaths"
    DefineMMI = "DefineMMI"
    ConductRiskAssessment = "ConductRiskAssessment"
    ChangeInWindDirection = "ChangeInWindDirection"
    EstablishLookouts = "EstablishLookouts"
    EstablishAnchorPoint = "EstablishAnchorPoint"
    EstablishSecureCommunicationSystem = "EstablishSecureCommunicationSystem"
    EstablishEscapeRoutes = "EstablishEscapeRoutes"
    DistanceToFire = "DistanceToFire"
    DrawUnitsOnMap = "DrawUnitsOnMap"
    SetupSensors = "SetupSensors"
    A7 = "A7" #Establish LACES.
    Humidity = "Humidity"
    InitiateDirectAttack = "InitiateDirectAttack"
    ChooseAttackMethod = "ChooseAttackMethod"
    InitiateIndirectAttack = "InitiateIndirectAttack"
    BreachesControlLine = "BreachesControlLine"
    EstablishControlLine = "EstablishControlLine"
    EvacuateCrewToSafeZone = "EvacuateCrewToSafeZone"
    OccursBehindCrew = "OccursBehindCrew"
    FlameHeight = "FlameHeight"
    StopDirectAttack = "StopDirectAttack"
    StopIndirectAttack = "StopIndirectAttack"

app = Flask(__name__)

SIDDHI_CALLBACK_URL = "http://siddhi:7072/middleman"


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def send_callback_to_siddhi(incident_id, case_id, event_name, dcr_result, value=None):
    payload_dict = {
        "enabledEvents": dcr_result.get("enabledEvents", []),
        "status": "error" if dcr_result.get("error") else "success"
    }
    if value not in (None, ""):
        payload_dict["value"] = value

    payload = {
        "incident_id": incident_id,
        "case_id": case_id,
        "event": event_name,
        "timestamp": utc_now_iso(),
        "role": "microservice",
        "payload": json.dumps(payload_dict),
        "error": ""
    }

    if dcr_result.get("error"):
        payload["error"] = dcr_result["message"]

    requests.post(SIDDHI_CALLBACK_URL, json=payload)


def process_event(incident_id, case_id, event_name, data=None, value=None):
    event_str = event_name.value if hasattr(event_name, 'value') else str(event_name)
    dcr_result = execute_event(case_id, event_str, data=data, value=value)
    # always fetch the current enabled events so every callback tells siddhi what's possible next
    dcr_result["enabledEvents"] = get_enabled_events(case_id)
    send_callback_to_siddhi(incident_id, case_id, event_str, dcr_result, value=value)
    return jsonify({"status": "ok"})


@app.route("/InitIncidentOut", methods=["POST"])
def init_incident():
    print("[RAW BODY]", request.data)
    data = request.json
    item = data[0] if isinstance(data, list) else data
    incident_id = item["event"]["incident_id"]
    action = item["event"].get("action")
    if not action:
        action = EventID.ArriveOnScene.value
    payload = item["event"].get("payload", {})
    value = item["event"].get("value")

    print(f"[InitIncident] Received incident_id = {incident_id}, action = {action}")
    # instantiate a new DCR case and register it as a scenario with incident_id
    case_id = create_case(incident_id)
    return process_event(incident_id, case_id, action, data=payload, value=value)


@app.route("/ExecuteEventOut", methods=["POST"])
def execute_event_route():
    print("[RAW BODY]", request.data)
    data = request.json
    items = data if isinstance(data, list) else [data]
    last_res = jsonify({"status": "ok"})
    for item in items:
        case_id = item["event"]["case_id"]
        payload = item["event"].get("payload", {})
        incident_id = item["event"]["incident_id"]
        action = item["event"]["action"]
        value = item["event"].get("value")
        print(f"[ExecuteEvent] Received incident_id = {incident_id}, action = {action}, value = {value}")
        last_res = process_event(incident_id, case_id, action, data=payload, value=value)

    return last_res


@app.route("/enabled_events/<case_id>", methods=["GET"])
def enabled_events(case_id):
    events = get_enabled_events(case_id)
    return jsonify({"case_id": case_id, "enabled_events": events})


@app.route("/get_available_actions", methods=["POST"])
def get_available_actions():
    data = request.json
    order_id = data.get("order_id")
    case_id = data.get("case_id")
    events = get_enabled_events(case_id)
    dcr_result = {"error": False, "message": "", "enabledEvents": events}
    send_callback_to_siddhi(order_id, case_id, "GetAvailableActions", dcr_result)
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
