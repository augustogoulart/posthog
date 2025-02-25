from typing import Any, Dict, Tuple

from django.conf import settings

from ee.clickhouse.queries.event_query import ClickhouseEventQuery
from ee.clickhouse.queries.trends.util import get_active_user_params, populate_entity_params
from ee.clickhouse.queries.util import date_from_clause, get_time_diff, get_trunc_func_ch, parse_timestamps
from posthog.constants import MONTHLY_ACTIVE, WEEKLY_ACTIVE
from posthog.models import Entity


class TrendsEventQuery(ClickhouseEventQuery):
    _entity: Entity

    def __init__(self, entity: Entity, *args, **kwargs):
        self._entity = entity
        super().__init__(*args, **kwargs)

    def get_query(self) -> Tuple[str, Dict[str, Any]]:
        _fields = (
            f"{self.EVENT_TABLE_ALIAS}.timestamp as timestamp, {self.EVENT_TABLE_ALIAS}.properties as properties"
            + (f", {self.DISTINCT_ID_TABLE_ALIAS}.person_id as person_id" if self._should_join_distinct_ids else "")
            + (f", {self.PERSON_TABLE_ALIAS}.person_props as person_props" if self._should_join_persons else "")
            + (
                " ".join(
                    [
                        f", {self.EVENT_TABLE_ALIAS}.properties_{prop} as properties_{prop}"
                        for prop in settings.CLICKHOUSE_DENORMALIZED_PROPERTIES
                    ]
                )
            )
        )

        date_query, date_params = self._get_date_filter()
        self.params.update(date_params)

        prop_filters = [*self._filter.properties, *self._entity.properties]
        prop_query, prop_params = self._get_props(prop_filters, allow_denormalized_props=True)
        self.params.update(prop_params)

        entity_query, entity_params = self._get_entity_query()
        self.params.update(entity_params)

        query = f"""
            SELECT {_fields} FROM events {self.EVENT_TABLE_ALIAS}
            {self._get_disintct_id_query()}
            {self._get_person_query()}
            WHERE team_id = %(team_id)s
            {entity_query}
            {date_query}
            {prop_query}
        """

        return query, self.params

    def _determine_should_join_persons(self) -> None:
        super()._determine_should_join_persons()
        for prop in self._entity.properties:
            if prop.type == "person":
                self._should_join_distinct_ids = True
                self._should_join_persons = True
                return

    def _determine_should_join_distinct_ids(self) -> None:
        if self._entity.math == "dau":
            self._should_join_distinct_ids = True

    def _get_date_filter(self) -> Tuple[str, Dict]:
        date_filter = ""
        date_params: Dict[str, Any] = {}
        interval_annotation = get_trunc_func_ch(self._filter.interval)
        _, _, round_interval = get_time_diff(
            self._filter.interval or "day", self._filter.date_from, self._filter.date_to, team_id=self._team_id
        )
        _, parsed_date_to, date_params = parse_timestamps(filter=self._filter, team_id=self._team_id)
        parsed_date_from = date_from_clause(interval_annotation, round_interval)

        self.parsed_date_from = parsed_date_from
        self.parsed_date_to = parsed_date_to

        if self._entity.math in [WEEKLY_ACTIVE, MONTHLY_ACTIVE]:
            date_filter = "{parsed_date_from_prev_range} {parsed_date_to}"
            format_params = get_active_user_params(self._filter, self._entity, self._team_id)
            self.active_user_params = format_params

            date_filter = date_filter.format(**format_params, parsed_date_to=parsed_date_to)
        else:
            date_filter = "{parsed_date_from} {parsed_date_to}".format(
                parsed_date_from=parsed_date_from, parsed_date_to=parsed_date_to
            )

        return date_filter, date_params

    def _get_entity_query(self) -> Tuple[str, Dict]:
        entity_params, entity_format_params = populate_entity_params(self._entity)

        return entity_format_params["entity_query"], entity_params
