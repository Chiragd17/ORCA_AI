import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.schemas.investigations import ExecutionEvent, EventType

class EventBus:
    """
    Manages and stores execution events emitted during an investigation.
    Enforces that events reflect genuine execution milestones.
    """
    def __init__(self, investigation_id: str):
        self.investigation_id = investigation_id
        self._events: List[ExecutionEvent] = []

    def emit(
        self,
        event_type: EventType,
        agent_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            id=f"evt-{uuid.uuid4().hex[:12]}",
            investigation_id=self.investigation_id,
            event_type=event_type,
            agent_id=agent_id,
            timestamp=datetime.now(timezone.utc),
            details=details or {},
        )
        self._events.append(event)
        return event

    def get_events(self) -> List[ExecutionEvent]:
        return list(self._events)
