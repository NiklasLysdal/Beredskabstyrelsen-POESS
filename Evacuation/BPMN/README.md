# BPMN Evacuation and Cordon

This folder contains the BPMN-based implementation of the project. It demonstrates how process logic can be modeled and orchestrated using Camunda Zeebe together with a Siddhi event-processing layer and Python-based integration services.

The setup runs the evacuation and cordon process in
`bpmn/evacuation_cordon_BRS_v3.bpmn`. The process starts when an
`EvacuationOrdered` event is received, requests a fire/traffic situation,
coordinates cordons and reception capacity, evacuates citizens by sector,
and completes after all persons are accounted for.

---

## Overview

The BPMN example combines the following components:

- a Python communication service
- a Siddhi runtime for event handling and stream processing
- Camunda Zeebe as the workflow engine
- Elasticsearch and Operate for process monitoring and inspection
- a logging service for operational output

This gives a full example of a process-centric system where workflow execution and event-driven messaging are connected.

---

## Architecture

```text
Customer / Test Event Stream
          |
          v
      Siddhi Runtime
          |
          v
  Python communication service
          |
          v
       Zeebe Broker
          |
      Elasticsearch / Operate
          |
      Logging Service
```

The communication layer forwards workflow-relevant messages to the BPMN engine, while the event stream and logging components help connect runtime activity with external inputs and outputs.

---

## Components

### Communication service
Location: `BPMN/deployer`

This component starts evacuation cases, publishes situation and safety messages,
and supplies workers for the executable evacuation tasks.

### Siddhi runtime
Location: `BPMN/siddhi`

Siddhi is used for stream-based processing and orchestration logic. It can receive incoming events, validate or route them, and connect to the workflow engine.

### Logging service
Location: `BPMN/logging_service`

This service receives operational messages and stores them in files for inspection and debugging.

### Zeebe, Elasticsearch, and Operate
These components are part of the core BPMN infrastructure and are started through Docker Compose.

---

## Prerequisites

Before starting the BPMN stack, make sure that:

- Docker is installed and running
- Docker Compose is available
- the local environment has enough resources to run the containers

---

## Running the BPMN setup

From the BPMN folder, run:

```bash
docker compose up --build
```

This starts the system containers for:

- communication service
- Siddhi runtime
- logging service
- Zeebe broker
- Elasticsearch
- Operate

To stop everything:

```bash
docker compose down
```

---

## Sending sample events

The repository includes a simple event-stream helper under `BPMN/event_streams`.

Example from the repository root:

```powershell
python .\event_streams\send_stream.py .\event_streams\test_events.jsonl
```

You can also validate the payload without sending it:

```powershell
python .\event_streams\send_stream.py .\event_streams\test_events.jsonl --dry-run
```

For more details, see [event_streams/README.md](event_streams/README.md).

The deployed communication service exposes these event endpoints:

- `POST /start_evacuation` with `{"incident_id":"incident-001"}`
- `POST /situation` with `{"incident_id":"incident-001","situation":{...}}`
- `POST /fire_situation_changed` with `{"incident_id":"incident-001","situation":{...}}`
- `POST /crew_safety_threat` with `{"incident_id":"incident-001","threat":{...}}`

The event stream helper sends evacuation orders and situation events to Siddhi,
which routes them to the corresponding communication endpoints. The included
`test_events.jsonl` covers normal completion, the missing-person loop, fire
boundary updates, and crew safety threats.

---

## Notes

This BPMN example is meant to serve as a starter project. It is intentionally simple so you can extend the process logic, event models, and integration points for your own implementation.

For the DCR implementation, see [../DCR/README.md](../DCR/README.md).
