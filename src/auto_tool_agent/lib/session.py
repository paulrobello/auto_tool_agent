"""Session"""

from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass
class Session:
    """Session"""

    id: str

    def __init__(
        self,
        id: str | None = None,  # pylint: disable=redefined-builtin
    ) -> None:
        # self.id = id or str(uuid4())
        self.id = id or datetime.datetime.now(datetime.UTC).strftime("%Y%m%d%H%M%S")


session = Session()
