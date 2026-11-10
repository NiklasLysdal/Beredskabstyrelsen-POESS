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
BPMN_FILE = os.getenv("BPMN_FILE", "/bpmn/wildfire_detection.bpmn")
SIDDHI_CALLBACK_URL = os.getenv("SIDDHI_CALLBACK_URL", "http://siddhi:7072/middleman")
CUSTOMER_PROCESS_ID = "Process_06p6nly"

app = Flask(__name__)
client = None
worker = None
event_loop = None
process_keys = {}


def now_iso():
    return datetime.now(timezone.utc).isoformat()

def callback(order_id, case_id, event, payload=None, error=""):
    body = {
        "order_id": order_id,
        "case_id": str(case_id),
        "event": event,
        "timestamp": now_iso(),
        "role": "camunda",
        "payload": json.dumps(payload or {}),
        "error": error,
    }
    response = requests.post(SIDDHI_CALLBACK_URL, json=body, timeout=30)
    response.raise_for_status()

async def register_incident_task(incidentId):
    print(f"Registering incident: {incidentId}", flush=True)
    return {}


async def record_false_alarm_task(incidentId):
    print(f"Recording false alarm: {incidentId}", flush=True)
    return {}


async def notify_cep_task(incidentId):
    print(f"Notifying CEP of false alarm: {incidentId}", flush=True)
    return {}


async def request_increased_monitoring_task(incidentId, severity):
    print(
        f"Requesting increased monitoring: {incidentId}, severity={severity}",
        flush=True,
    )
    return {}


async def print_process_ended_task(incidentId):
    print(f"Process ended: {incidentId}", flush=True)
    return {}

def run_async(coroutine):
    if event_loop is None:
        raise RuntimeError("Communication adapter is not ready")
    future = asyncio.run_coroutine_threadsafe(coroutine, event_loop)
    return future.result(timeout=30)


async def publish_message(name, order_id, variables):
    await client.publish_message(name, str(order_id), variables)


@app.post("/place_order")
def place_order():
    data = request.get_json(force=True)
    order_id = get_order_id(data)
    if not order_id:
        return jsonify({"error": "order_id is required"}), 400

    process_key = run_async(client.run_process(
        CUSTOMER_PROCESS_ID,
        variables={"orderId": order_id},
    ))
    process_keys[order_id] = process_key
    callback(order_id, process_key, "PlaceOrder", {"processInstanceKey": process_key})
    return jsonify({"status": "accepted", "case_id": str(process_key)})

def cancel_order():
    data = request.get_json(force=True)
    order_id = get_order_id(data)
    if not order_id:
        return jsonify({"error": "order_id is required"}), 400
    case_id = get_case_id(order_id, data.get("case_id"))
    run_async(publish_message("OrderCancelled", order_id, {"orderId": order_id, "caseId": case_id}))
    return jsonify({"status": "accepted"})

def receive_order():
    data = request.get_json(force=True)
    order_id = get_order_id(data)
    if not order_id:
        return jsonify({"error": "order_id is required"}), 400
    case_id = get_case_id(order_id, data.get("case_id"))
    run_async(publish_message("FoodReceived", order_id, {"orderId": order_id, "caseId": case_id}))
    return jsonify({"status": "accepted"})

def pay_order():
    data = request.get_json(force=True)
    order_id = get_order_id(data)
    if not order_id:
        return jsonify({"error": "order_id is required"}), 400
    return jsonify({"status": "accepted"})

async def deploy_and_work():
    global client, worker
    channel = grpc.aio.insecure_channel(ZEEBE_ADDRESS)
    client = ZeebeClient(grpc_channel=channel)
    worker = ZeebeWorker(grpc_channel=channel)
    worker.task(task_type="register_incident", variables_to_fetch=["incidentId"])(register_incident_task)
    worker.task(task_type="record_false_alarm", variables_to_fetch=["incidentId"])(record_false_alarm_task)
    worker.task(task_type="notify_cep", variables_to_fetch=["incidentId"])(notify_cep_task)
    worker.task(task_type="request_increased_monitoring", variables_to_fetch=["incidentId", "severity"])(request_increased_monitoring_task)
    worker.task(task_type="print_process_ended", variables_to_fetch=["incidentId"])(print_process_ended_task)
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
