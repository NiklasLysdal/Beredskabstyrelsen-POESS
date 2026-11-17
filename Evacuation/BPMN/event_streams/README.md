# Event streams

`send_stream.py` sends evacuation events to Siddhi in the order they appear in a JSONL or JSON file.

Each event must contain an `incident_id` and one of:

- `EvacuationOrdered`
- `FireSituationChanged`
- `CrewSafetyThreat`

`EvacuationOrdered` accepts `all_accounted_for` to select the normal completion
path (`true`) or the missing-person loop (`false`). The other events trigger the
fire/traffic update and crew-safety event subprocesses. Optional `case_id`,
`situation`, and `threat` fields are forwarded to the communication service.

From the repository root, with the BPMN stack running:

```powershell
python .\BPMN\event_streams\send_stream.py .\BPMN\event_streams\test_events.jsonl
```

Use `--delay 0` to send without pauses, or `--dry-run` to validate and print the stream without sending it:

```powershell
python .\BPMN\event_streams\send_stream.py .\BPMN\event_streams\test_events.jsonl --dry-run
```

The default endpoint is `http://localhost:7071/customer`. Override it with `--url` or the `SIDDHI_URL` environment variable.

A `.json` file may contain the same events as one JSON array instead of one JSON object per line.

The sample stream covers:

- normal evacuation completion;
- a missing-person loop that resolves after a search;
- a fire-boundary/route update; and
- crew-safety threats.

Rebuild the Siddhi and communication services after changing the event schema:

```powershell
docker compose up --build -d siddhi communication
```
