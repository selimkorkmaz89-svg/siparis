"""Shared list-screen filtering: date range, search and column ordering."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Sequence

from django.db.models import Q, QuerySet


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@dataclass
class ListFilter:
    """Applies the UI conventions every list screen shares."""

    request: object
    search_fields: Sequence[str] = field(default_factory=tuple)
    date_field: str = "created_at"
    ordering_map: dict[str, str] = field(default_factory=dict)
    default_ordering: str = "-created_at"

    def __post_init__(self):
        params = self.request.GET
        self.search = (params.get("q") or "").strip()
        self.date_from = parse_date(params.get("date_from"))
        self.date_to = parse_date(params.get("date_to"))
        self.sort = params.get("sort") or ""

    @property
    def is_active(self) -> bool:
        return bool(self.search or self.date_from or self.date_to or self.sort)

    def apply(self, queryset: QuerySet) -> QuerySet:
        if self.search and self.search_fields:
            condition = Q()
            for name in self.search_fields:
                condition |= Q(**{f"{name}__icontains": self.search})
            queryset = queryset.filter(condition)
        if self.date_from:
            queryset = queryset.filter(**{f"{self.date_field}__date__gte": self.date_from})
        if self.date_to:
            queryset = queryset.filter(**{f"{self.date_field}__date__lte": self.date_to})
        return queryset.order_by(*self.order_by())

    def order_by(self) -> list[str]:
        key = self.sort.lstrip("-")
        target = self.ordering_map.get(key)
        if not target:
            return [self.default_ordering]
        return [f"-{target}" if self.sort.startswith("-") else target]

    def as_context(self) -> dict:
        return {
            "q": self.search,
            "date_from": self.date_from.isoformat() if self.date_from else "",
            "date_to": self.date_to.isoformat() if self.date_to else "",
            "sort": self.sort,
            "filters_active": self.is_active,
        }
