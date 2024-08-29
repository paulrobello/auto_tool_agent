"""Session"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from argparse import Namespace


@dataclass
class Session:
    """Session"""

    id: str
    opts: Namespace

    def __init__(
        self,
        id: Optional[str] = None,  # pylint: disable=redefined-builtin
    ) -> None:
        self.id = id or str(uuid4())


session = Session(id="tools_tests")
