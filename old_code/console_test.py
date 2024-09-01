import git
from git import Repo

from pathlib import Path
from rich.console import Console
from rich.syntax import Syntax

console = Console()
working_tree_dir = Path("~/.config/auto_tool_agent/sandbox").expanduser()
if (working_tree_dir / ".git").exists():
    console.log("Found git repo")
    repo = Repo(working_tree_dir)
else:
    console.log("No git repo found")
    repo = Repo.init(working_tree_dir)

modified_files = [item.a_path for item in repo.index.diff(None)]
console.log("untracked files", repo.untracked_files)
repo.index.add(repo.untracked_files)
console.log("modified files", modified_files)
if modified_files:
    diff_index = repo.index.diff(None, modified_files[0], create_patch=True)
    console.log("number of changes", len(diff_index))
    for change in diff_index:
        if isinstance(change.diff, bytes):
            diff = change.diff.decode("utf-8", errors="replace")
        else:
            diff = str(change.diff)
        diff = diff.replace("\n", "\n")
        s = Syntax(diff, "diff")
        console.log(s)
        # console.log(str(change.diff))
        # console.log(change.split("---", 2)[1])
