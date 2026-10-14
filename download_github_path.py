#!/usr/bin/env python3
"""
download_github_path.py

Download a file or folder from a GitHub repository given a repository URL and an optional path.

Usage:
  python download_github_path.py <repository_url_or_owner/repo> [path] [--output OUTPUT_DIR] [--token GITHUB_TOKEN]

Examples:
  python download_github_path.py https://github.com/owner/repo path/to/folder
  python download_github_path.py owner/repo path/to/file.txt --output ./downloaded
  python download_github_path.py https://github.com/owner/repo/tree/branch/path --token YOURTOKEN

Notes:
- If the path is a directory the script will recursively download all files preserving directory structure.
- For public repositories no token is required. For private repos provide a token via --token or GITHUB_TOKEN env var.
"""

from __future__ import annotations
import argparse
import os
import sys
import requests
from urllib.parse import urlparse, unquote


def parse_github_url(url: str):
    """Return (owner, repo, branch, path) where branch and path may be None.
    Accepts forms:
      - https://github.com/owner/repo
      - https://github.com/owner/repo/tree/branch/path/to/dir
      - https://github.com/owner/repo/blob/branch/path/to/file
      - owner/repo
    """
    url = url.strip()
    # owner/repo quick form
    if "/" in url and not url.startswith("http") and url.count("/") == 1:
        owner, repo = url.split("/")
        return owner, repo, None, None

    parsed = urlparse(url)
    if parsed.netloc.lower() not in ("github.com", "www.github.com"):
        raise ValueError("URL doesn't look like a GitHub URL")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("URL must include owner and repo")
    owner, repo = parts[0], parts[1]
    branch = None
    path = None
    if len(parts) >= 3 and parts[2] in ("tree", "blob"):
        # /tree/<branch>/<path...>
        if len(parts) >= 4:
            branch = parts[3]
        if len(parts) >= 5:
            path = "/".join(parts[4:])
    elif len(parts) >= 3:
        # Could be owner/repo/.. ignore for now
        # Common case: trailing slash or other URLs
        pass
    if path:
        path = unquote(path)
    return owner, repo, branch, path


class GitHubDownloader:
    API_URL = "https://api.github.com"

    def __init__(self, owner: str, repo: str, token: str | None = None):
        self.owner = owner
        self.repo = repo
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Authorization": f"token {token}"})
        # set a user agent
        self.session.headers.update({"User-Agent": "download-github-path-script"})

    def _contents_endpoint(self, path: str | None, ref: str | None) -> str:
        if path:
            path = path.lstrip("/")
            return f"{self.API_URL}/repos/{self.owner}/{self.repo}/contents/{path}" + (f"?ref={ref}" if ref else "")
        else:
            return f"{self.API_URL}/repos/{self.owner}/{self.repo}/contents" + (f"?ref={ref}" if ref else "")

    def fetch_metadata(self, path: str | None = None, ref: str | None = None):
        url = self._contents_endpoint(path, ref)
        r = self.session.get(url)
        if r.status_code == 404:
            raise FileNotFoundError(f"Path not found in repo: {path} (ref={ref})")
        r.raise_for_status()
        return r.json()

    def download_file(self, download_url: str, local_path: str):
        r = self.session.get(download_url, stream=True)
        r.raise_for_status()
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    def download_path(self, path: str | None, outdir: str, ref: str | None = None):
        meta = self.fetch_metadata(path, ref)
        # meta may be a dict (file) or list (directory)
        if isinstance(meta, dict):
            # single file
            if meta.get("type") != "file":
                raise RuntimeError(f"Unsupported content type: {meta.get('type')}")
            rel = meta.get("path")
            local_path = os.path.join(outdir, rel)
            print(f"Downloading file {rel} -> {local_path}")
            self.download_file(meta.get("download_url"), local_path)
        elif isinstance(meta, list):
            # directory
            for item in meta:
                itype = item.get("type")
                ipath = item.get("path")
                if itype == "file":
                    local_path = os.path.join(outdir, ipath)
                    print(f"Downloading file {ipath}")
                    self.download_file(item.get("download_url"), local_path)
                elif itype == "dir":
                    # recurse
                    print(f"Descending into directory {ipath}")
                    self.download_path(ipath, outdir, ref)
                else:
                    print(f"Skipping unsupported item type: {itype} at {ipath}")
        else:
            raise RuntimeError("Unexpected metadata structure from GitHub API")


def main(argv):
    p = argparse.ArgumentParser(description="Download a file or folder from a GitHub repository")
    p.add_argument("repo_url", help="Repository URL (https://github.com/owner/repo) or owner/repo or full tree/blob URL")
    p.add_argument("path", nargs="?", help="Path inside repository (file or directory). Optional if URL contains it.")
    p.add_argument("--output", "-o", default="downloads", help="Output directory (default: ./downloads)")
    p.add_argument("--token", "-t", default=None, help="GitHub token (or set GITHUB_TOKEN env var)")
    p.add_argument("--ref", "-r", default=None, help="Branch/ref to use (overrides branch parsed from URL)")
    args = p.parse_args(argv)

    token = args.token or os.environ.get("GITHUB_TOKEN")

    try:
        owner, repo, branch_from_url, path_from_url = parse_github_url(args.repo_url)
    except Exception as e:
        print("Error parsing repo URL:", e)
        sys.exit(2)

    # priority: explicit ref flag > branch in URL > None
    ref = args.ref or branch_from_url
    # priority: explicit path arg > path in URL
    path = args.path or path_from_url

    downloader = GitHubDownloader(owner, repo, token)
    outdir = args.output
    print(f"Repository: {owner}/{repo}  ref={ref}  path={path}  output={outdir}")

    try:
        downloader.download_path(path, outdir, ref)
    except FileNotFoundError as e:
        print("Not found:", e)
        sys.exit(3)
    except requests.HTTPError as e:
        print("HTTP error:", e)
        sys.exit(4)
    except Exception as e:
        print("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
