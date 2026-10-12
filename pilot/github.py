"""A local stand-in for GitHub over HTTPS, so remotes keep their real addresses.

`git remote -v` shows a URL after `insteadOf` rewriting, so a remote rewritten to a local folder shows that folder,
and a tutor checking whether `origin` is the course's own repository cannot tell. Instead, git is given its own exec
path (GIT_EXEC_PATH) in which `git-remote-https` is a small remote helper: it maps `https://github.com/<owner>/<repo>`
to a bare repository `<root>/<owner>/<repo>.git` and connects git's upload-pack or receive-pack to it. Remotes keep
their GitHub URLs; a repository that does not exist answers as GitHub does ("Repository not found"), and one marked
read-only refuses pushes with GitHub's 403 message. Every other git command is the real one (the exec path holds
links to the real git-core)."""
from __future__ import annotations

import os, re, subprocess  # noqa: E401
from pathlib import Path

URL = re.compile(r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")
DENIED = ("remote: Permission to {owner}/{name}.git denied to {user}.\n"
          "fatal: unable to access 'https://github.com/{owner}/{name}/': The requested URL returned error: 403\n")
HELPER = '''#!{python}
"""git-remote-https: fetch from and push to this laptop's GitHub repositories."""
import os, re, sys

ROOT = {root!r}
url = sys.argv[2] if len(sys.argv) > 2 else sys.argv[1]
m = re.match({pattern!r}, url)
local = os.path.join(ROOT, m.group(1), m.group(2) + ".git") if m else None
for line in sys.stdin:
    line = line.strip()
    if line == "capabilities":
        sys.stdout.write("connect\\n\\n")
        sys.stdout.flush()
    elif line.startswith("connect "):
        service = line.split(" ", 1)[1]
        if not local or not os.path.isdir(local):
            sys.stderr.write("remote: Repository not found.\\nfatal: repository '%s/' not found\\n" % url.rstrip("/"))
            sys.exit(128)
        denied = os.path.join(local, "push-denied")
        if service == "git-receive-pack" and os.path.exists(denied):
            sys.stderr.write(open(denied, encoding="utf-8").read())
            sys.exit(128)
        sys.stdout.write("\\n")
        sys.stdout.flush()
        os.execvp("git", ["git", service[len("git-"):], local])  # upload-pack or receive-pack, built into git
    else:
        sys.exit(0)
'''


def url(owner: str, name: str) -> str:
    return f"https://github.com/{owner}/{name}"


def install(exec_dir: Path, root: Path, *, python: str, git: str = "git") -> dict:
    """Fill `exec_dir` with links to the real git-core plus the helper, and return the environment that makes git
    use it ({"GIT_EXEC_PATH": ...}). `git` is the git the actors will run (its --exec-path is linked)."""
    real = Path(subprocess.run([git, "--exec-path"], capture_output=True, text=True, check=True).stdout.strip())
    exec_dir, root = Path(exec_dir), Path(root)
    exec_dir.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    for entry in real.iterdir():
        if entry.name not in ("git-remote-https", "git-remote-http") and not (exec_dir / entry.name).exists():
            (exec_dir / entry.name).symlink_to(entry)
    helper = exec_dir / "git-remote-https"
    helper.write_text(HELPER.format(python=python, root=str(root), pattern=URL.pattern), encoding="utf-8")
    helper.chmod(0o755)
    if not (exec_dir / "git-remote-http").exists():
        (exec_dir / "git-remote-http").symlink_to("git-remote-https")
    return {"GIT_EXEC_PATH": str(exec_dir)}


def add_repo(root: Path, owner: str, name: str, source: Path | None = None, *, push_denied_to: str = "") -> Path:
    """A bare repository at <root>/<owner>/<name>.git, cloned from `source` when given (else empty). With
    `push_denied_to`, pushes are refused with GitHub's 403 message naming that user."""
    path = Path(root) / owner / f"{name}.git"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        args = (["clone", "-q", "--bare", "--no-local", str(source), str(path)] if source else
                ["init", "-q", "--bare", str(path)])
        p = subprocess.run(["git", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if p.returncode:
            raise RuntimeError(f"git {' '.join(args[:2])} for {owner}/{name} failed: {p.stderr.strip()}")
    if push_denied_to:
        (path / "push-denied").write_text(DENIED.format(owner=owner, name=name, user=push_denied_to), encoding="utf-8")
    return path


def local_path(root: Path, address: str) -> Path | None:
    """The bare repository a GitHub URL maps to, or None when it is not a GitHub repository URL."""
    m = URL.match(address.strip())
    return Path(root) / m.group(1) / f"{m.group(2)}.git" if m else None


def _run(*args: str, cwd: Path | None = None, env: dict | None = None) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                       env={**os.environ, **(env or {})})
    if p.returncode:
        raise RuntimeError(f"git {' '.join(args[:3])}: {p.stderr.strip()}")
    return p.stdout


def replay_template(bare: Path, template: Path, since: str | None, ref: str = "HEAD",
                    branch: str = "main") -> list[dict]:
    """Make a template update reach a run: add the template's commits after `since` (up to `ref`) to `bare`'s
    `branch`, one commit each, with the template commit's message, author and date and its whole tree, on top of
    what `branch` holds now. A student's `git fetch upstream` then lists them by subject and `git merge
    upstream/main` brings them in, as when the instructor pushes to the class repository. When `since` is unknown
    to the template's history (or not given), one commit carries `ref`'s tree. Returns
    [{"sha", "template", "subject"}] for the commits added (none when the template has not moved)."""
    bare, template = Path(bare), Path(template)
    head = _run("rev-parse", f"{ref}^{{commit}}", cwd=template).strip()
    known = bool(since) and subprocess.run(["git", "merge-base", "--is-ancestor", since, head], cwd=template,
                                           capture_output=True).returncode == 0
    commits = [c for c in _run("rev-list", "--reverse", f"{since}..{head}", cwd=template).split()] if known else [head]
    if not commits or (known and since == head):
        return []
    _run("--git-dir", str(bare), "fetch", "-q", "--no-tags", str(template), f"+{head}:refs/pilot/template")
    parent = _run("--git-dir", str(bare), "rev-parse", f"refs/heads/{branch}").strip()
    added = []
    try:
        for c in commits:
            name, email, date, message = _run("log", "-1", "--format=%an%x00%ae%x00%aI%x00%B", c,
                                              cwd=template).split("\0", 3)
            who = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": date,
                   "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": date}
            tree = _run("--git-dir", str(bare), "rev-parse", f"{c}^{{tree}}").strip()
            parent = _run("--git-dir", str(bare), "commit-tree", tree, "-p", parent, "-m", message.rstrip("\n"),
                          env=who).strip()
            added.append({"sha": parent, "template": c, "subject": message.splitlines()[0] if message else ""})
        _run("--git-dir", str(bare), "update-ref", f"refs/heads/{branch}", parent)
    finally:
        subprocess.run(["git", "--git-dir", str(bare), "update-ref", "-d", "refs/pilot/template"],
                       capture_output=True)
    return added
