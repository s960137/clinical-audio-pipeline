"""Conservative staged-file guard. This is not a guarantee of anonymization."""

from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SUFFIXES = {".py", ".md", ".toml", ".json", ".svg", ".html", ".yml", ".yaml", ".txt"}
ALLOWED_DOTFILES = {".gitignore", ".gitattributes"}
PATTERNS = [
    rb"(?<![A-Za-z0-9])[A-Z][12][0-9]{8}(?![0-9])",
    rb"gh[pousr]_[A-Za-z0-9]{20,}",
    rb"github_pat_[A-Za-z0-9_]{20,}",
    rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
    rb"[A-Za-z]:[\\/]Users[\\/]",
]


def main():
    git_root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=ROOT).decode().strip()
    if Path(git_root).resolve() != ROOT:
        print("BLOCK: initialize this standalone repository before scanning; parent indexes are not allowed")
        return True
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    findings = []
    count = 0
    for name in filter(None, names):
        count += 1
        path = Path(name)
        if path.suffix.lower() not in ALLOWED_SUFFIXES and name not in ALLOWED_DOTFILES:
            findings.append((name, "file_type_not_allowlisted"))
        if any(word in name.lower() for word in ["cookie", "credential", ".env", "profile"]):
            findings.append((name, "sensitive_filename"))
        content = subprocess.check_output(["git", "show", ":" + name], cwd=ROOT)
        if len(content) > 250_000:
            findings.append((name, "unexpected_large_file"))
        if any(re.search(pattern, content) for pattern in PATTERNS):
            findings.append((name, "potential_sensitive_content"))
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            findings.append((name, "binary_content"))
    if not count:
        findings.append(("index", "no_staged_or_tracked_files"))
    for name, reason in findings:
        print(f"BLOCK: {name}: {reason}")
    print(f"Public tree scan: {count} indexed files, {len(findings)} findings")
    return bool(findings)


if __name__ == "__main__":
    sys.exit(main())
