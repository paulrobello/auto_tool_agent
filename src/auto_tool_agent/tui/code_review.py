"""Tui for code review"""

from __future__ import annotations

from typing import Literal

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Header,
    Footer,
    TextArea,
    Button,
    Checkbox,
)

from auto_tool_agent.graph.graph_state import ToolDescription
from auto_tool_agent.tui.dialogs.yes_no_dialog import YesNoDialog

UserResponse = Literal["Accept", "Reject", "AI Review"]


class MainScreen(Screen[None]):
    """Main screen"""

    DEFAULT_CSS = """
    MainScreen {
        #tool_bar {
            background: $panel;
            width: 1fr;
            height: 3;
            Button, Checkbox{
                width: auto;
                height: 3;
                margin-right: 1;
            }
        }
        Vertical{
            width: 1fr;
            height: 1fr;
            #DepsEditor{
                width: 1fr;
                height: 8;
            }
            #CodeEditor{
                width: 1fr;
                height: 1fr;
            }
        }
    }
    """

    def __init__(self, tool_def: ToolDescription) -> None:
        """Initialise the screen."""
        super().__init__()
        self.title = f"Code Review - {tool_def.name}"
        self.tool_def = tool_def
        self.updated = False

    def compose(self) -> ComposeResult:
        """Compose the screen"""
        yield Header()
        yield Footer()
        with self.prevent(TextArea.Changed, Checkbox.Changed):
            with Vertical():
                with Horizontal(id="tool_bar"):
                    yield Button("Accept", id="Accept")
                    yield Button("Reject", id="Reject")
                    yield Checkbox(
                        "Needs Review",
                        id="NeedsReview",
                        value=self.tool_def.needs_review,
                    )

                yield TextArea.code_editor(
                    "\n".join(self.tool_def.dependencies),
                    id="DepsEditor",
                    read_only=False,
                )
                yield TextArea.code_editor(
                    self.tool_def.code,
                    id="CodeEditor",
                    language="python",
                    read_only=False,
                )
        self.updated = False

    @on(Button.Pressed, "#Accept")
    async def accept(self) -> None:
        """Accept the changes"""
        if self.updated:
            await self.app.push_screen(
                YesNoDialog(
                    "Code Modified",
                    "Save changes?",
                ),
                self.confirm_save_response,  # type: ignore
            )
        self.app.exit("Accept")

    async def confirm_save_response(self, res: bool) -> None:
        """Save code"""
        if not res:
            return
        self.tool_def.existing = True
        self.tool_def.needs_review = self.query_one(Checkbox).value
        self.tool_def.code = self.query_one("#CodeEditor", TextArea).text.strip()
        self.tool_def.dependencies = (
            self.query_one("#DepsEditor", TextArea).text.strip().split("\n")
        )
        self.tool_def.save_code()
        self.tool_def.save_metadata()

    async def confirm_reject_response(self, res: bool) -> None:
        """Delete tool"""
        if not res:
            return
        self.tool_def.delete()
        self.app.exit("Reject")

    @on(Button.Pressed, "#Reject")
    async def reject(self) -> None:
        """Reject the changes"""
        await self.app.push_screen(
            YesNoDialog(
                "Reject Tool",
                "Delete tool and return to planner?",
            ),
            self.confirm_reject_response,  # type: ignore
        )

    @on(TextArea.Changed)
    def textarea_changed(self) -> None:
        """Set updated flag"""
        self.updated = True

    @on(Checkbox.Changed)
    def checkbox_changed(self) -> None:
        """Set updated flag"""
        self.updated = True


class CodeReviewApp(App[UserResponse]):
    """App to test Textual stuff"""

    def __init__(self, tool_def: ToolDescription) -> None:
        """Initialise the app."""
        super().__init__()
        self.main_screen = MainScreen(tool_def)

    async def on_mount(self) -> None:
        """Mount the screen."""
        await self.push_screen(self.main_screen)
