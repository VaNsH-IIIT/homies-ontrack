"""Ask: plain-English question -> answer with its SQL or sources, or a refusal (owner: P2).

v0 for the runner (P2-T2): scope rules, then a placeholder. P2-T3 adds certified metrics and NL-to-SQL.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ontrack import config
from ontrack.l2_ask import scope


@dataclass
class Answer:
    answer: str
    sql_or_sources: str
    refused: bool
    route: str = ""                      # data | document | refuse | error
    understood_as: dict = field(default_factory=dict)
    table: object = None                 # pandas DataFrame of the result, for the app
    reason: str = ""
    sql: str = ""


class Engine:
    def __init__(self, con, use_cache: bool = True):
        self.con = con
        self.use_cache = use_cache

    def answer(self, question: str, as_of_date: str = config.SNAPSHOT_DATE, metric_id: str | None = None,
               question_id: str = "", tolerance: str = "") -> Answer:
        v = scope.route(question)
        if v.refused:
            return Answer(f"Refuse: {v.reason} {v.alternative}".strip(), "", True, "refuse", reason=v.category)
        return Answer("Not answered yet (placeholder)", "", False, v.route)
