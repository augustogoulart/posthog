from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ee.clickhouse.client import sync_execute
from ee.clickhouse.models.action import format_action_filter
from ee.clickhouse.models.property import parse_prop_clauses
from ee.clickhouse.queries.breakdown_props import (
    format_breakdown_cohort_join_query,
    get_breakdown_event_prop_values,
    get_breakdown_person_prop_values,
)
from ee.clickhouse.queries.funnels.funnel_event_query import FunnelEventQuery
from ee.clickhouse.sql.funnels.funnel import FUNNEL_INNER_EVENT_STEPS_QUERY
from posthog.constants import FUNNEL_WINDOW_DAYS, LIMIT, TREND_FILTER_TYPE_ACTIONS
from posthog.models import Entity, Filter, Team
from posthog.queries.funnel import Funnel
from posthog.utils import relative_date_parse


class ClickhouseFunnelBase(ABC, Funnel):
    _filter: Filter
    _team: Team

    def __init__(self, filter: Filter, team: Team) -> None:
        self._filter = filter
        self._team = team
        self.params = {
            "team_id": self._team.pk,
            "events": [],  # purely a speed optimization, don't need this for filtering
        }

        # handle default if window isn't provided
        if not self._filter.funnel_window_days:
            self._filter = self._filter.with_data({FUNNEL_WINDOW_DAYS: 14})

        if not self._filter.limit:
            new_limit = {LIMIT: 100}
            self._filter = self._filter.with_data(new_limit)
            self.params.update(new_limit)

    def run(self, *args, **kwargs):
        if len(self._filter.entities) == 0:
            return []

        results = self._exec_query()
        return self._format_results(results)

    def _format_single_funnel(self, results, with_breakdown=False):
        # Format of this is [step order, person count (that reached that step), array of person uuids]
        steps = []
        total_people = 0

        for step in reversed(self._filter.entities):

            if results and len(results) > 0:
                total_people += results[step.order]

            serialized_result = self._serialize_step(step, total_people, [])
            if step.order > 0:
                serialized_result.update(
                    {
                        "average_conversion_time": results[step.order + len(self._filter.entities) - 1],
                        "median_conversion_time": results[step.order + len(self._filter.entities) * 2 - 2],
                    }
                )
            else:
                serialized_result.update({"average_conversion_time": None, "median_conversion_time": None})

            if with_breakdown:
                serialized_result.update({"breakdown": results[-1]})
                # important to not try and modify this value any how - as these are keys for fetching persons

            steps.append(serialized_result)

        return steps[::-1]  #  reverse

    def _format_results(self, results):
        if not results or len(results) == 0:
            return []

        if self._filter.breakdown:
            return [self._format_single_funnel(res, with_breakdown=True) for res in results]
        else:
            return self._format_single_funnel(results[0])

    def _exec_query(self) -> List[Tuple]:

        # format default dates
        data: Dict[str, Any] = {}
        if not self._filter._date_from:
            data.update({"date_from": relative_date_parse("-7d")})
        if not self._filter._date_to:
            data.update({"date_to": timezone.now()})

        if self._filter.breakdown and not self._filter.breakdown_type:
            data.update({"breakdown_type": "event"})

        for exclusion in self._filter.exclusions:
            if exclusion.funnel_from_step is None or exclusion.funnel_to_step is None:
                raise ValidationError("Exclusion event needs to define funnel steps")

            if exclusion.funnel_from_step >= exclusion.funnel_to_step:
                raise ValidationError("Exclusion event range is invalid. End of range should be greater than start.")

            if exclusion.funnel_from_step >= len(self._filter.entities) - 1:
                raise ValidationError(
                    "Exclusion event range is invalid. Start of range is greater than number of steps."
                )

            if exclusion.funnel_to_step > len(self._filter.entities) - 1:
                raise ValidationError("Exclusion event range is invalid. End of range is greater than number of steps.")

        self._filter = self._filter.with_data(data)

        query = self.get_query()
        return sync_execute(query, self.params)

    def _get_step_times(self, max_steps: int):
        conditions: List[str] = []
        for i in range(1, max_steps):
            conditions.append(
                f"if(isNotNull(latest_{i}), dateDiff('second', toDateTime(latest_{i - 1}), toDateTime(latest_{i})), NULL) step_{i}_conversion_time"
            )

        formatted = ", ".join(conditions)
        return f", {formatted}" if formatted else ""

    def _get_partition_cols(self, level_index: int, max_steps: int):
        cols: List[str] = []
        for i in range(0, max_steps):
            cols.append(f"step_{i}")
            if i < level_index:
                cols.append(f"latest_{i}")
                for exclusion in self._filter.exclusions:
                    if exclusion.funnel_from_step + 1 == i:
                        cols.append(f"exclusion_latest_{exclusion.funnel_from_step}")
            else:
                duplicate_event = 0
                if i > 0 and self._filter.entities[i].equals(self._filter.entities[i - 1]):
                    duplicate_event = 1
                cols.append(
                    f"min(latest_{i}) over (PARTITION by person_id {self._get_breakdown_prop()} ORDER BY timestamp DESC ROWS BETWEEN UNBOUNDED PRECEDING AND {duplicate_event} PRECEDING) latest_{i}"
                )
                for exclusion in self._filter.exclusions:
                    # exclusion starting at step i follows semantics of step i+1 in the query (since we're looking for exclusions after step i)
                    if exclusion.funnel_from_step + 1 == i:
                        cols.append(
                            f"min(exclusion_latest_{exclusion.funnel_from_step}) over (PARTITION by person_id {self._get_breakdown_prop()} ORDER BY timestamp DESC ROWS BETWEEN UNBOUNDED PRECEDING AND 0 PRECEDING) exclusion_latest_{exclusion.funnel_from_step}"
                        )
        return ", ".join(cols)

    def _get_exclusion_condition(self):
        if not self._filter.exclusions:
            return ""

        conditions = []
        for exclusion in self._filter.exclusions:
            from_time = f"latest_{exclusion.funnel_from_step}"
            to_time = f"latest_{exclusion.funnel_to_step}"
            exclusion_time = f"exclusion_latest_{exclusion.funnel_from_step}"
            condition = (
                f"if( {exclusion_time} > {from_time} AND {exclusion_time} < "
                f"if(isNull({to_time}), {from_time} + INTERVAL {self._filter.funnel_window_days} DAY, {to_time}), 1, 0)"
            )
            conditions.append(condition)

        if conditions:
            return f", arraySum([{','.join(conditions)}]) as exclusion"
        else:
            return ""

    def _get_sorting_condition(self, curr_index: int, max_steps: int):

        if curr_index == 1:
            return "1"

        conditions: List[str] = []
        for i in range(1, curr_index):
            conditions.append(f"latest_{i - 1} < latest_{i }")
            conditions.append(f"latest_{i} <= latest_0 + INTERVAL {self._filter.funnel_window_days} DAY")

        return f"if({' AND '.join(conditions)}, {curr_index}, {self._get_sorting_condition(curr_index - 1, max_steps)})"

    def _get_inner_event_query(
        self, entities=None, entity_name="events", skip_entity_filter=False, skip_step_filter=False
    ) -> str:
        entities_to_use = entities or self._filter.entities

        event_query, params = FunnelEventQuery(filter=self._filter, team_id=self._team.pk).get_query(
            entities_to_use, entity_name, skip_entity_filter=skip_entity_filter
        )

        self.params.update(params)

        if skip_step_filter:
            steps_conditions = "1=1"
        else:
            steps_conditions = self._get_steps_conditions(length=len(entities_to_use))

        all_step_cols: List[str] = []
        for index, entity in enumerate(entities_to_use):
            step_cols = self._get_step_col(entity, index, entity_name)
            all_step_cols.extend(step_cols)

        for entity in self._filter.exclusions:
            step_cols = self._get_step_col(entity, entity.funnel_from_step, entity_name, "exclusion_")
            # every exclusion entity has the form: exclusion_step_i & timestamp exclusion_latest_i
            # where i is the starting step for exclusion on that entity
            all_step_cols.extend(step_cols)

        steps = ", ".join(all_step_cols)

        select_prop = self._get_breakdown_select_prop()
        breakdown_conditions = ""
        extra_conditions = ""
        extra_join = ""

        if self._filter.breakdown:
            if self._filter.breakdown_type == "cohort":
                extra_join = self._get_cohort_breakdown_join()
            else:
                breakdown_conditions = self._get_breakdown_conditions()
                extra_conditions = "AND prop != ''" if select_prop else ""
                extra_conditions += f"AND {breakdown_conditions}" if breakdown_conditions and select_prop else ""

        return FUNNEL_INNER_EVENT_STEPS_QUERY.format(
            steps=steps,
            event_query=event_query,
            extra_join=extra_join,
            steps_condition=steps_conditions,
            select_prop=select_prop,
            extra_conditions=extra_conditions,
        )

    def _get_steps_conditions(self, length: int) -> str:
        step_conditions: List[str] = []

        for index in range(length):
            step_conditions.append(f"step_{index} = 1")

        for entity in self._filter.exclusions:
            step_conditions.append(f"exclusion_step_{entity.funnel_from_step} = 1")

        return " OR ".join(step_conditions)

    def _get_step_col(self, entity: Entity, index: int, entity_name: str, step_prefix: str = "") -> List[str]:
        # step prefix is used to distinguish actual steps, and exclusion steps
        # without the prefix, we get the same parameter binding for both, which borks things up
        step_cols: List[str] = []
        condition = self._build_step_query(entity, index, entity_name, step_prefix)
        step_cols.append(f"if({condition}, 1, 0) as {step_prefix}step_{index}")
        step_cols.append(f"if({step_prefix}step_{index} = 1, timestamp, null) as {step_prefix}latest_{index}")

        return step_cols

    def _build_step_query(self, entity: Entity, index: int, entity_name: str, step_prefix: str) -> str:
        filters = self._build_filters(entity, index)
        if entity.type == TREND_FILTER_TYPE_ACTIONS:
            action = entity.get_action()
            for action_step in action.steps.all():
                self.params[entity_name].append(action_step.event)
            action_query, action_params = format_action_filter(action, f"{entity_name}_{step_prefix}step_{index}")
            if action_query == "":
                return ""

            self.params.update(action_params)
            content_sql = "{actions_query} {filters}".format(actions_query=action_query, filters=filters,)
        else:
            self.params[entity_name].append(entity.id)
            event_param_key = f"{entity_name}_{step_prefix}event_{index}"
            self.params[event_param_key] = entity.id
            content_sql = f"event = %({event_param_key})s {filters}"
        return content_sql

    def _build_filters(self, entity: Entity, index: int) -> str:
        prop_filters, prop_filter_params = parse_prop_clauses(
            entity.properties, self._team.pk, prepend=str(index), allow_denormalized_props=True
        )
        self.params.update(prop_filter_params)
        if entity.properties:
            return prop_filters
        return ""

    def _get_funnel_person_step_condition(self):
        step_num = self._filter.funnel_step
        max_steps = len(self._filter.entities)

        if step_num is None:
            raise ValueError("funnel_step should not be none")

        conditions = []
        if step_num >= 0:
            self.params.update({"step_num": [i for i in range(step_num, max_steps + 1)]})
            conditions.append("steps IN %(step_num)s")
        else:
            self.params.update({"step_num": abs(step_num) - 1})
            conditions.append("steps = %(step_num)s")

        if self._filter.funnel_step_breakdown:
            prop_vals = (
                [val.strip() for val in self._filter.funnel_step_breakdown.split(",")]
                if isinstance(self._filter.funnel_step_breakdown, str)
                else [self._filter.funnel_step_breakdown]
            )
            self.params.update({"breakdown_prop_value": prop_vals})
            conditions.append("prop IN %(breakdown_prop_value)s")

        return " AND ".join(conditions)

    def _get_count_columns(self, max_steps: int):
        cols: List[str] = []

        for i in range(max_steps):
            cols.append(f"countIf(steps = {i + 1}) step_{i + 1}")

        return ", ".join(cols)

    def _get_step_time_avgs(self, max_steps: int, inner_query: bool = False):
        conditions: List[str] = []
        for i in range(1, max_steps):
            conditions.append(
                f"avg(step_{i}_conversion_time) step_{i}_average_conversion_time_inner"
                if inner_query
                else f"avg(step_{i}_average_conversion_time_inner) step_{i}_average_conversion_time"
            )

        formatted = ", ".join(conditions)
        return f", {formatted}" if formatted else ""

    def _get_step_time_median(self, max_steps: int, inner_query: bool = False):
        conditions: List[str] = []
        for i in range(1, max_steps):
            conditions.append(
                f"median(step_{i}_conversion_time) step_{i}_median_conversion_time_inner"
                if inner_query
                else f"median(step_{i}_median_conversion_time_inner) step_{i}_median_conversion_time"
            )

        formatted = ", ".join(conditions)
        return f", {formatted}" if formatted else ""

    @abstractmethod
    def get_query(self):
        pass

    def get_step_counts_query(self):
        pass

    def get_step_counts_without_aggregation_query(self):
        pass

    def _get_breakdown_select_prop(self) -> str:
        if self._filter.breakdown:
            self.params.update({"breakdown": self._filter.breakdown})
            if self._filter.breakdown_type == "person":
                return f", trim(BOTH '\"' FROM JSONExtractRaw(person_props, %(breakdown)s)) as prop"
            elif self._filter.breakdown_type == "event":
                return f", trim(BOTH '\"' FROM JSONExtractRaw(properties, %(breakdown)s)) as prop"
            elif self._filter.breakdown_type == "cohort":
                return ", value as prop"

        return ""

    def _get_cohort_breakdown_join(self) -> str:
        cohort_queries, _, cohort_params = format_breakdown_cohort_join_query(self._team.pk, self._filter)
        self.params.update(cohort_params)
        return f"""
            INNER JOIN (
                {cohort_queries}
            ) cohort_join
            ON events.distinct_id = cohort_join.distinct_id
        """

    def _get_breakdown_conditions(self) -> str:
        if self._filter.breakdown:
            limit = 5
            first_entity = next(x for x in self._filter.entities if x.order == 0)
            if not first_entity:
                ValidationError("An entity with order 0 was not provided")
            values = []
            if self._filter.breakdown_type == "person":
                values = get_breakdown_person_prop_values(self._filter, first_entity, "count(*)", self._team.pk, limit)
            elif self._filter.breakdown_type == "event":
                values = get_breakdown_event_prop_values(self._filter, first_entity, "count(*)", self._team.pk, limit)
            self.params.update({"breakdown_values": values})

            return "prop IN %(breakdown_values)s"
        else:
            return ""

    def _get_breakdown_prop(self) -> str:
        if self._filter.breakdown:
            return ", prop"
        else:
            return ""
