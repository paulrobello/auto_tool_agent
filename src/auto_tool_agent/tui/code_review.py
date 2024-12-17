"""Tui for code review"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pyperclip  # type: ignore
from rich.syntax import Syntax
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Select,
    Static,
    TextArea,
)

from auto_tool_agent.graph.graph_state import CodeReviewResponse, ToolDescription
from auto_tool_agent.tui.dialogs.yes_no_dialog import YesNoDialog

UserResponse = Literal["Accept", "Reject", "Abort", "AI Review"]


@dataclass
class SendToClipboard(Message):
    """Used to send a string to the clipboard."""

    message: str
    notify: bool = True


class MainScreen(Screen[None]):
    """Main screen"""

    BINDINGS = [
        # Binding("ctrl+v", "app.paste_from_clipboard", "", show=True),
        Binding("ctrl+c", "app.copy_to_clipboard", "", show=True),
    ]
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
            #CodeReview{
                width: 1fr;
                height: 6;
            }
            #Diff{
                width: 1fr;
                height: 10;
                #DiffSyntax{
                    width: 1fr;
                    height: auto;
                }
            }
            #DepsEditor{
                width: 1fr;
                height: 6;
            }
            #CodeEditor{
                width: 1fr;
                height: 1fr;
            }
            TextArea{
                border-title-color: $accent;
            }
            VerticalScroll{
                border: tall $background;
                border-title-color: $accent;
            }
        }
    }
    """

    def __init__(
        self,
        tool_def: ToolDescription,
        code_review: CodeReviewResponse,
        diff: Syntax | None,
    ) -> None:
        """Initialise the screen."""
        super().__init__()
        self.title = f"Code Review - {tool_def.name}"
        self.tool_def = tool_def
        self.code_review = code_review
        self.diff = diff
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
                    yield Button("Abort", id="Abort")
                    yield Checkbox(
                        "Needs Review",
                        id="NeedsReview",
                        value=self.tool_def.needs_review,
                    )
                with TextArea(
                    self.code_review.tool_issues,
                    id="CodeReview",
                ) as cr:
                    cr.border_title = "Code Review"
                if self.diff:
                    with VerticalScroll(
                        id="Diff",
                    ) as diff_vs:
                        diff_vs.border_title = "Diff"
                        yield Static(
                            self.diff,
                            id="DiffSyntax",
                        )
                with TextArea.code_editor(
                    "\n".join(self.tool_def.dependencies),
                    id="DepsEditor",
                    read_only=False,
                ) as deps_editor:
                    deps_editor.border_title = "Dependencies"
                with TextArea.code_editor(
                    self.tool_def.code.strip() + "\n",
                    id="CodeEditor",
                    language="python",
                    read_only=False,
                ) as code_editor:
                    code_editor.border_title = "Code"

    @on(Button.Pressed, "#Accept")
    async def accept(self) -> None:
        """Accept the changes"""
        self.code_review.tool_valid = True

        if self.updated:
            await self.app.push_screen(
                YesNoDialog(
                    "Code Modified",
                    "Save changes?",
                ),
                self.confirm_save_response,
            )
        else:
            self.app.exit("Accept")

    def confirm_save_response(self, res: bool | None) -> None:
        """Save code"""
        if not res:
            return

        self.tool_def.needs_review = self.query_one(Checkbox).value
        old_code = self.tool_def.code
        new_code = self.query_one("#CodeEditor", TextArea).text.strip() + "\n"
        self.tool_def.code = new_code

        old_deps = self.tool_def.dependencies
        new_deps = self.query_one("#DepsEditor", TextArea).text.strip().split("\n")
        self.tool_def.dependencies = new_deps
        self.code_review.tool_updated = old_code != new_code or set(old_deps) != set(new_deps)

        new_issues = self.query_one("#CodeReview", TextArea).text.strip()
        old_issues = self.code_review.tool_issues.strip()
        if new_issues != old_issues:
            self.code_review.tool_issues = new_issues
        else:
            self.code_review.tool_issues = ""

        self.tool_def.save()
        self.app.exit("Accept")

    def confirm_reject_response(self, res: bool | None) -> None:
        """Delete tool"""
        if not res:
            return
        self.code_review.tool_valid = False
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
            self.confirm_reject_response,
        )

    @on(Button.Pressed, "#Abort")
    def abort(self) -> None:
        """Abort the application"""
        self.app.exit("Abort")

    @on(TextArea.Changed)
    def textarea_changed(self) -> None:
        """Set updated flag"""
        self.updated = True
        self.title = f"Code Review - {self.tool_def.name} - Updated"

    @on(Checkbox.Changed)
    def checkbox_changed(self) -> None:
        """Set updated flag"""
        self.updated = True


class CodeReviewApp(App[UserResponse]):
    """App to test Textual stuff"""

    BINDINGS = [
        Binding(key="ctrl+c", action="noop", show=False),
    ]

    def __init__(
        self,
        tool_def: ToolDescription,
        code_review: CodeReviewResponse,
        diff: Syntax | None = None,
    ) -> None:
        """Initialise the app."""
        super().__init__()
        self.main_screen = MainScreen(tool_def, code_review, diff)

    async def on_mount(self) -> None:
        """Mount the screen."""
        await self.push_screen(self.main_screen)

    def action_noop(self) -> None:
        """Do nothing"""

    def action_copy_to_clipboard(self) -> None:
        """Copy focused widget value to clipboard"""
        f: Widget | None = self.screen.focused
        if not f:
            return

        if isinstance(f, (Input | Select)):
            self.app.post_message(SendToClipboard(str(f.value) if f.value and f.value != Select.BLANK else ""))

        if isinstance(f, TextArea):
            self.app.post_message(SendToClipboard(f.selected_text or f.text))

    @on(SendToClipboard)
    def send_to_clipboard(self, event: SendToClipboard) -> None:
        """Send string to clipboard"""
        # works for remote ssh sessions
        self.copy_to_clipboard(event.message)
        # works for local sessions
        pyperclip.copy(event.message)
        if event.notify:
            self.notify("Copied to clipboard")
