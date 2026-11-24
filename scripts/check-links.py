#!/usr/bin/env python3
"""Check every link in the Markdown files of the repository.

Relative links must point at a file (and, for a #fragment into a Markdown file, at a heading).
https links are fetched. Hosts that refuse automated clients (AES, ISO, ITU, and some publishers)
are listed as MANUAL: open them in a browser or search for the title, and note the result in the
release test log. Exit status 1 when a relative link or a fetchable link is broken.

    python3 scripts/check-links.py [--offline]
"""

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANUAL_HOSTS = ("aes.org", "aes2.org", "iso.org", "doi.org")
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|<img[^>]+src=\"([^\"]+)\"|<(https?://[^>\s]+)>")
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}


def slug(heading):
    h = re.sub(r"[`*_]", "", heading.strip().lower())
    h = re.sub(r"[^\w\- ]", "", h)
    return h.replace(" ", "-")


def anchors(path):
    return {slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.*?)\s*$", path.read_text(), re.M)}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; link-check)"})
    last = None
    for method in ("HEAD", "GET"):
        req.method = method
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, ""
        except urllib.error.HTTPError as e:
            last = (e.code, str(e))
            if e.code in (404, 410):
                return last
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = (0, str(e))
    return last


def main():
    offline = "--offline" in sys.argv
    files = [p for p in ROOT.rglob("*.md") if not SKIP_DIRS & set(p.relative_to(ROOT).parts)]
    bad, manual, seen, n = [], [], {}, 0
    for f in sorted(files):
        for m in LINK.finditer(f.read_text()):
            target = next(g for g in m.groups() if g)
            n += 1
            if target.startswith(("mailto:", "#")) and not target.startswith("#"):
                continue
            if target.startswith("#"):
                if target[1:] not in anchors(f):
                    bad.append((f, target, "no such heading"))
                continue
            own = re.match(r"https://(?:github\.com/(?:aclater|dsd-toolbox)/dsd-measure/blob|raw\.githubusercontent\.com/(?:aclater|dsd-toolbox)/dsd-measure)/main/(.+)", target)
            if own:  # a link to this repository's main branch: before the release is merged, check the local file
                if not (ROOT / own.group(1).split("#")[0]).exists():
                    bad.append((f, target, "no such file in this tree"))
                continue
            if target.startswith(("http://", "https://")):
                host = target.split("/")[2]
                if any(host == h or host.endswith("." + h) for h in MANUAL_HOSTS):
                    manual.append((f, target))
                elif not offline:
                    if target not in seen:
                        seen[target] = fetch(target)
                    code, msg = seen[target]
                    if code != 200:
                        bad.append((f, target, f"HTTP {code} {msg}"[:100]))
                continue
            path, _, frag = target.partition("#")
            dest = (f.parent / path).resolve() if path else f
            if not dest.exists():
                bad.append((f, target, "no such file"))
            elif frag and dest.suffix == ".md" and frag not in anchors(dest):
                bad.append((f, target, "no such heading"))
    print(f"{n} links in {len(files)} files")
    for f, t, why in bad:
        print(f"BROKEN {f.relative_to(ROOT)}: {t} ({why})")
    for f, t in sorted(set(manual)):
        print(f"MANUAL {f.relative_to(ROOT)}: {t}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
