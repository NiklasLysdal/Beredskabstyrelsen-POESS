# Action Plan – DCR & Siddhi

`send_stream.py` sends events and sensor readings from `test_events.jsonl` into Siddhi (`/actor`, `/humidity`, `/wind`), which processes them and forwards valid process events to DCR (`DCR_GRAPH_ID=2017006`).

## Run like this

From the project root in PowerShell:

**1. Start Docker:**
```powershell
docker compose -f "Action plan/DCR/docker-compose.yml" up -d --build
```

**2. Send the event stream:**
```powershell
& .venv\Scripts\python.exe "Action plan\DCR\event_streams\send_stream.py" "Action plan\DCR\event_streams\test_events.jsonl" --delay 0.6
```

**3. Reset Siddhi memory (only needed if re-running the same incident IDs):**
```powershell
docker restart siddhi-runtime
```

**4. Stop Docker:**
```powershell
docker compose -f "Action plan/DCR/docker-compose.yml" down
```
