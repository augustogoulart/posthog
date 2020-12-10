import json
from typing import Any, Dict, Optional

from django.http import HttpRequest

from posthog.constants import DISTINCT_ID_FILTER
from posthog.models import Entity, Filter

json_load_if = lambda data: json.loads(data) if data is not None else None


class SessionsFilter(Filter):
    distinct_id: Optional[str]
    duration_operator: Optional[str]  # lt, gt
    _duration: Optional[str]
    action_filter: Optional[Entity]

    def __init__(self, data: Dict[str, Any] = {}, request: Optional[HttpRequest] = None, **kwargs) -> None:
        super().__init__(data, request, **kwargs)
        if request:
            data = {**request.GET.dict(), "action_filter": json_load_if(request.GET.get("action_filter"))}
        elif not data:
            raise ValueError("You need to define either a data dict or a request")

        self.distinct_id = data.get(DISTINCT_ID_FILTER)
        self.duration_operator = data.get("duration_operator")
        self._duration = data.get("duration")
        self.action_filter = None
        if data.get("action_filter") is not None:
            self.action_filter = Entity(data["action_filter"])

    @property
    def duration(self) -> float:
        return float(self._duration or 0)

    @property
    def limit_by_recordings(self) -> bool:
        return self.duration_operator is not None
