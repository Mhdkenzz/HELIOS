# Plugin API

Helios is designed to be extensible. Events flow through the `EventBus`, and you can hook into any stage.

## Event Types

```json
{ "type": "cmd",     "body": { "command": "...", "exit_code": 0, ... } }
{ "type": "file",    "body": { "action": "modified", "path": "src/app.tsx" } }
{ "type": "alert",   "body": { "msg": "disk > 90%" } }
{ "type": "system",  "body": { "msg": "recorder.start" } }
```

## Using the EventBus Directly

```python
from helios.recorder import EventBus

bus = EventBus()

def my_handler(event: dict):
    print(f"Got event: {event['type']}")

bus.subscribe(my_handler)

# Events are dicts with 'type' and 'body' keys
```

## Subscribing to Specific Event Types

```python
from helios.recorder import EventBus

bus = EventBus()

def on_cmd(event):
    cmd = event["body"].get("command", "")
    if "deploy" in cmd:
        print("Deployment detected!")

bus.subscribe(on_cmd, event_type="cmd")
```

## Custom Metrics

Add your own metrics to the recorder's metrics dict:

```python
from helios.recorder import Recorder

rec = Recorder(root_path, bus)

# Add a custom metric callback
rec.metrics["custom"] = lambda: {
    "queue_depth": queue.qsize(),
    "cache_hits": cache_hits,
}
```

## Webhook Integration

Receive events via HTTP POST:

```python
# In your FastAPI app:
from helios.recorder import HttpClient

client = HttpClient("https://my-webhook.example.com/events")
bus.subscribe(client.publish)
```

## Extending the Dashboard

The frontend communicates over WebSocket at `/ws`. To add a custom panel:

1. Create a React component in `web/src/`
2. Import it in `App.tsx`
3. Subscribe to WebSocket events in the component

See `web/src/App.tsx` for the full event schema usage.

## Rolling Your Own Snapshot Backend

`SnapshotManager` can be subclassed:

```python
from helios.snapshot import SnapshotManager
from pathlib import Path

class S3SnapshotManager(SnapshotManager):
    def __init__(self, root: Path, bucket: str):
        super().__init__(root)
        self.bucket = bucket

    def snapshot(self, tag=""):
        super().snapshot(tag)
        self._upload_to_s3(tag)
```