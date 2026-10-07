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
        args = ["clone", "-q", "--bare", "--no-local", str(source), str(path)] if source else ["init", "-q", "--bare", str(path)]
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
