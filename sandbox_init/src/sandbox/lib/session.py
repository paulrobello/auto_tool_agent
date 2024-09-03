"""Session"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional


@dataclass
class Session:
    """Session"""

    id: str

    def __init__(
        self,
        id: Optional[str] = None,  # pylint: disable=redefined-builtin
    ) -> None:
        # self.id = id or str(uuid4())
        self.id = id or datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y%m%d%H%M%S"
        )


session = Session()
