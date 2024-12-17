"""Session"""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from uuid import uuid4


@dataclass
class Session:
    """Session"""

    id: str
    opts: Namespace

    def __init__(
        self,
        id: str | None = None,  # pylint: disable=redefined-builtin
    ) -> None:
        self.id = id or str(uuid4())


session = Session(id="tools_tests")
