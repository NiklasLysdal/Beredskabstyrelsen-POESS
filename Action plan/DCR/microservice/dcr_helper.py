import os
import requests
import re
import base64

DCR_API_BASE = "https://repository.dcrgraphs.net/api"
DCR_GRAPH_ID = os.getenv("DCR_GRAPH_ID")
USERNAME = os.getenv("DCR_USERNAME")
PASSWORD = os.getenv("DCR_PASSWORD")

# prepare Basic Auth header
auth_string = f"{USERNAME}:{PASSWORD}"
b64_auth = base64.b64encode(auth_string.encode()).decode()

HEADERS = {
    "Authorization": f"Basic {b64_auth}",
    "Accept": "application/xml",
    "Content-Type": "application/json"
}

DATA_EVENT_TYPES = {
    "Humidity": "int",
    "FlameHeight": "float",
    "DistanceToFire": "float",
}


def create_case(incident_id=None):
    """
    Create a new DCR case (simulation instance) and mark it as a visible Scenario/Flow.
    Returns the case_id or None on failure.
    """
    create_url = f"{DCR_API_BASE}/graphs/{DCR_GRAPH_ID}/sims"
    r = requests.post(create_url, headers=HEADERS, auth=(USERNAME, PASSWORD), json={})

    if r.status_code not in (200, 201):
        print(f"[CreateCase] Error {r.status_code}: {r.text}")
        return None

    case_id = r.headers.get("simulationID")
    if not case_id:
        sims_url = f"{DCR_API_BASE}/graphs/{DCR_GRAPH_ID}/sims?filter=all"
        r2 = requests.get(sims_url, headers=HEADERS, auth=(USERNAME, PASSWORD))
        ids = re.findall(r'<trace[^>]*id="(\d+)"', r2.text)
        if not ids:
            print("[CreateCase] No case IDs found")
            return None
        case_id = ids[-1]

    title = incident_id if incident_id else f"Incident-{case_id}"
    init_log = f'<log><trace id="{case_id}" title="{title}" type="Required" isAccepting="true" isScenario="true" /></log>'
    scenario_payload = {
        "log": init_log,
        "dcrLog": init_log,
        "xmlLog": init_log,
        "dcrXmlLog": init_log,
        "logXml": init_log,
        "dcrLogXml": init_log,
    }
    try:
        requests.post(
            f"{DCR_API_BASE}/graphs/{DCR_GRAPH_ID}/sims/{case_id}",
            headers=HEADERS,
            auth=(USERNAME, PASSWORD),
            json=scenario_payload,
        )
    except Exception as e:
        print(f"[CreateCase] Warning: could not mark case {case_id} as scenario: {e}")

    print(f"[CreateCase] New case_id = {case_id} (title={title}, isScenario=true)")
    return case_id


def get_enabled_events(case_id):
    """
    Return the list of enabled event IDs for a given DCR case.
    """
    url = f"{DCR_API_BASE}/graphs/{DCR_GRAPH_ID}/sims/{case_id}/events"
    r = requests.get(url, headers=HEADERS, auth=(USERNAME, PASSWORD))

    if r.status_code not in (200, 201):
        print(f"[GetEnabledEvents] Error {r.status_code}: {r.text}")
        return []

    xml = r.text.replace('\\"', '"')
    pattern = r'<event[^>]*id="([^"]+)"[^>]*enabled="true"[^>]*>'
    events = re.findall(pattern, xml, flags=re.IGNORECASE)

    print(f"[GetEnabledEvents] case_id={case_id} events={events}")
    return events


def execute_event(case_id, event_id, data=None, value=None):
    if data is None:
        data = {}

    if event_id in DATA_EVENT_TYPES and value not in (None, ""):
        var_type = DATA_EVENT_TYPES[event_id]
        data = {
            "DataXML": f'<globalStore><variable id="{event_id}" value="{value}" isNull="false" type="{var_type}" /></globalStore>'
        }

    url = f"{DCR_API_BASE}/graphs/{DCR_GRAPH_ID}/sims/{case_id}/events/{event_id}"
    r = requests.post(url, headers=HEADERS, auth=(USERNAME, PASSWORD), json=data)

    if r.status_code not in (200, 201, 204):

        try:
            r_scen = requests.get(
                f"{DCR_API_BASE}/graphs/{DCR_GRAPH_ID}/sims?isScenario=true",
                headers=HEADERS,
                auth=(USERNAME, PASSWORD),
            )
            m = re.search(rf'(<trace id="{case_id}"[^>]*>)(.*?)(</trace>)', r_scen.text, re.DOTALL)
            if m:
                new_trace = m.group(1) + m.group(2) + f'<event id="{event_id}" />' + m.group(3)
                wrapped = f"<log>{new_trace}</log>"
                payload = {
                    "log": wrapped,
                    "dcrLog": wrapped,
                    "xmlLog": wrapped,
                    "dcrXmlLog": wrapped,
                    "logXml": wrapped,
                    "dcrLogXml": wrapped,
                }
                requests.post(
                    f"{DCR_API_BASE}/graphs/{DCR_GRAPH_ID}/sims/{case_id}",
                    headers=HEADERS,
                    auth=(USERNAME, PASSWORD),
                    json=payload,
                )
        except Exception as e:
            print(f"[ExecuteEvent] Warning: could not append rejected event {event_id} to trace {case_id}: {e}")

        return {
            "error": True,
            "message": f"DCR returned {r.status_code}: {r.text}",
            "enabledEvents": []
        }

    if not r.content or not r.text.strip():
        return {
            "error": False,
            "message": "",
            "enabledEvents": []
        }

    try:
        resp_data = r.json()
        enabled = resp_data.get("enabledEvents", [])
        return {
            "error": False,
            "message": "",
            "enabledEvents": enabled
        }
    except Exception:
        text = r.text
        if "<event" in text:
            enabled = re.findall(r'<event[^>]*id="([^"]+)"[^>]*enabled="true"', text, flags=re.IGNORECASE)
            return {
                "error": False,
                "message": "",
                "enabledEvents": enabled
            }

        return {
            "error": False,
            "message": "No JSON payload; empty or non-JSON DCR response",
            "enabledEvents": []
        }
