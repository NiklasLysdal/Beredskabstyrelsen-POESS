# Action Plan DCR Event Streams

`send_stream.py` sends an ordered stream of wildfire response events to Siddhi to drive the DCR Graph simulation.

Each event in the stream is a JSON object with:
- `incident_id`: The ID of the incident / case (e.g. `"incident-001"`).
- `action`: The event name corresponding to a DCR event in the graph.

---

## Supported Events

- `ArriveOnScene`
- `SurveyForFire`
- `IdentifySpreadingPaths`
- `DefineMMI`
- `ConductRiskAssessment`
- `EstablishLookouts`
- `EstablishAnchorPoint`
- `EstablishSecureCommunicationSystem`
- `EstablishEscapeRoutes`
- `EstablishSafeZones`
- `DrawUnitsOnMap`
- `ChooseAttackMethod`
- `InitiateDirectAttack`
- `InitiateIndirectAttack`
- `EstablishControlLine`
- `BreachesControlLine`
- `EvacuateCrewToSafeZone`
- `ChangeInWindDirection`
- `ChangeInHumidity`
- `ChangeInFlameHeight`
- `OccursBehindCrew`

---

## Running the Simulation Stream

Make sure the Action Plan DCR stack is running (`docker compose up`).

### 1. Validate the Stream (Dry Run)
Check the stream syntax and events without sending HTTP requests:

```powershell
python "Action plan\DCR\event_streams\send_stream.py" "Action plan\DCR\event_streams\test_events.jsonl" --dry-run
```

### 2. Send Events into Siddhi
Stream the events to Siddhi with the default delay (0.5s between events):

```powershell
python "Action plan\DCR\event_streams\send_stream.py" "Action plan\DCR\event_streams\test_events.jsonl"
```

### CLI Options

| Option | Default | Description |
| :--- | :--- | :--- |
| `--url <URL>` | `http://localhost:7071/incident` | Siddhi input endpoint. |
| `--delay <SEC>` | `0.5` | Delay in seconds between events (`0` to send all immediately). |
| `--timeout <SEC>` | `10.0` | HTTP request timeout. |
| `--dry-run` | `False` | Prints events without sending HTTP requests. |
| `--no-validate` | `False` | Skips event name validation (allows sending experimental events). |
