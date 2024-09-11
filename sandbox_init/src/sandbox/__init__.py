"""SANDBOX AI TOOLS Agent."""

from __future__ import annotations

import os
import warnings

from langchain._api import LangChainDeprecationWarning


warnings.simplefilter("ignore", category=LangChainDeprecationWarning)


__author__ = "Paul Robello"
__credits__ = ["Paul Robello"]
__maintainer__ = "Paul Robello"
__email__ = "probello@gmail.com"
__version__ = "0.0.1"
__application_title__ = "AI TOOLS Agent"
__application_binary__ = "sandbox"
__licence__ = "MIT"


os.environ["USER_AGENT"] = f"{__application_title__} {__version__}"


__all__: list[str] = [
    "__author__",
    "__credits__",
    "__maintainer__",
    "__email__",
    "__version__",
    "__application_binary__",
    "__licence__",
    "__application_title__",
]
