import asyncio
import json
import os
import threading
from datetime import datetime, timezone

import grpc
import requests
from flask import Flask, jsonify, request
from pyzeebe import Job, ZeebeClient, ZeebeWorker

ZEEBE_ADDRESS = os.getenv("ZEEBE_ADDRESS", "zeebe:26500")
BPMN_FILE = os.getenv("BPMN_FILE", "/bpmn/evacuation_cordon_BRS_v3.bpmn")
SIDDHI_CALLBACK_URL = os.getenv("SIDDHI_CALLBACK_URL", "http://siddhi:7072/middleman")
PROCESS_ID = "Process_Evacuation"

app = Flask(__name__)
client = None
worker = None
event_loop = None
process_keys = {}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_incident_id(data):
    return data.get("incident_id") or data.get("event", {}).get("incident_id")


def callback(incident_id, case_id, event, payload=None, error=""):
    body = {
        "incident_id": incident_id,
        "case_id": str(case_id),
        "event": event,
        "timestamp": now_iso(),
        "role": "camunda",
        "payload": json.dumps(payload or {}),
        "error": error,
    }
    response = requests.post(SIDDHI_CALLBACK_URL, json=body, timeout=30)
    response.raise_for_status()


def get_case_id(incident_id, supplied_case_id=None):
    return supplied_case_id or process_keys.get(incident_id, "UNKNOWN_CASE")


def run_async(coroutine):
    if event_loop is None:
        raise RuntimeError("Communication adapter is not ready")
    future = asyncio.run_coroutine_threadsafe(coroutine, event_loop)
    return future.result(timeout=30)


async def publish_message(name, incident_id, variables):
    await client.publish_message(name, str(incident_id), variables)


@app.post("/start_evacuation")
def start_evacuation():
    data = request.get_json(force=True)
    incident_id = get_incident_id(data)
    if not incident_id:
        return jsonify({"error": "incident_id is required"}), 400

    variables = {
        "incidentId": incident_id,
        "allAccountedFor": data.get("all_accounted_for", True),
    }
    run_async(publish_message("EvacuationOrdered", incident_id, variables))
    callback(incident_id, "PENDING", "EvacuationOrdered", variables)
    return jsonify({"status": "accepted", "incident_id": incident_id})


@app.post("/situation")
def situation():
    data = request.get_json(force=True)
    incident_id = get_incident_id(data)
    if not incident_id:
        return jsonify({"error": "incident_id is required"}), 400
    case_id = get_case_id(incident_id, data.get("case_id"))
    run_async(publish_message("FireTrafficSituation", incident_id, {
        "incidentId": incident_id,
        "caseId": case_id,
        "situation": data.get("situation", {}),
    }))
    return jsonify({"status": "accepted"})


@app.post("/fire_situation_changed")
def fire_situation_changed():
    data = request.get_json(force=True)
    incident_id = get_incident_id(data)
    if not incident_id:
        return jsonify({"error": "incident_id is required"}), 400
    run_async(publish_message("FireSituationChanged", incident_id, {
        "incidentId": incident_id,
        "caseId": get_case_id(incident_id, data.get("case_id")),
        "situation": data.get("situation", {}),
    }))
    return jsonify({"status": "accepted"})


@app.post("/crew_safety_threat")
def crew_safety_threat():
    data = request.get_json(force=True)
    incident_id = get_incident_id(data)
    if not incident_id:
        return jsonify({"error": "incident_id is required"}), 400
    run_async(publish_message("CrewSafetyThreat", incident_id, {
        "incidentId": incident_id,
        "caseId": get_case_id(incident_id, data.get("case_id")),
        "threat": data.get("threat", {}),
    }))
    return jsonify({"status": "accepted"})


async def request_cep_situation(incidentId, job: Job):
    variables = {"incidentId": incidentId, "caseId": job.process_instance_key}
    process_keys[incidentId] = job.process_instance_key
    await publish_message("FireTrafficSituation", incidentId, variables)
    callback(incidentId, job.process_instance_key, "RequestFireTrafficSituation", variables)
    return variables


async def evacuation_task(incidentId, caseId=None, job: Job = None, **variables):
    case_id = caseId or (job.process_instance_key if job else "UNKNOWN_CASE")
    payload = {"incidentId": incidentId, "caseId": case_id, **variables}
    callback(incidentId, case_id, variables.pop("event", "EvacuationActivity"), payload)
    return payload


def create_evacuation_handler(event, resolves_missing_persons=False):
    async def handler(incidentId, caseId=None, allAccountedFor=None, job=None):
        if resolves_missing_persons:
            allAccountedFor = True
        return await evacuation_task(
            incidentId,
            caseId,
            job,
            event=event,
            allAccountedFor=allAccountedFor,
        )

    return handler


async def deploy_and_work():
    global client, worker
    channel = grpc.aio.insecure_channel(ZEEBE_ADDRESS)
    client = ZeebeClient(grpc_channel=channel)
    worker = ZeebeWorker(grpc_channel=channel)
    worker.task(
        task_type="request_cep_situation",
        variables_to_fetch=["incidentId"],
    )(request_cep_situation)

    task_types = {
        "define_zones": "DefineZones",
        "assess_crew_safety": "AssessCrewSafety",
        "create_missing_register": "CreateMissingRegister",
        "select_reception_center": "SelectReceptionCenter",
        "request_police_cordon": "RequestPoliceCordon",
        "reserve_reception_capacity": "ReserveReceptionCapacity",
        "establish_inner_cordon": "EstablishInnerCordon",
        "evacuate_citizens": "EvacuateCitizens",
        "register_evacuated": "RegisterEvacuated",
        "search_remaining_persons": "SearchRemainingPersons",
        "confirm_zone_cleared": "ConfirmZoneCleared",
        "handover_to_police": "HandoverToPolice",
        "update_zones_and_routes": "UpdateZonesAndRoutes",
        "notify_field_teams": "NotifyFieldTeams",
        "withdraw_crews_to_safety_zones": "WithdrawCrewsToSafetyZones",
    }
    for task_type, event in task_types.items():
        worker.task(
            task_type=task_type,
            variables_to_fetch=["incidentId", "caseId", "allAccountedFor"],
        )(create_evacuation_handler(
            event,
            resolves_missing_persons=task_type == "search_remaining_persons",
        ))

    for attempt in range(1, 31):
        try:
            deployment = await client.deploy_process(BPMN_FILE)
            print(f"[Camunda] BPMN deployed: {deployment}", flush=True)
            break
        except Exception as error:
            cause = getattr(error, "__cause__", None)
            print(
                f"[Camunda] deployment attempt {attempt} failed: "
                f"{error!r}; cause={cause!r}",
                flush=True,
            )
            if attempt == 30:
                raise
            await asyncio.sleep(2)
    await worker.work()


def serve_http():
    app.run(host="0.0.0.0", port=5001, threaded=True)


async def main():
    global event_loop
    event_loop = asyncio.get_running_loop()
    threading.Thread(target=serve_http, daemon=True).start()
    await deploy_and_work()


if __name__ == "__main__":
    asyncio.run(main())
