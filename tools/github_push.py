#!/usr/bin/env python3
"""Cria um repositório GitHub e faz upload de todos os arquivos do projeto via API."""

import base64
import fnmatch
import os
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).parent.parent


def load_gitignore_patterns() -> list[str]:
    gitignore = PROJECT_ROOT / ".gitignore"
    patterns = []
    if gitignore.exists():
        for line in gitignore.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def is_ignored(path: Path, patterns: list[str]) -> bool:
    rel = str(path.relative_to(PROJECT_ROOT))
    for pattern in patterns:
        clean = pattern.rstrip("/")
        if fnmatch.fnmatch(rel, clean):
            return True
        if fnmatch.fnmatch(rel, f"{clean}/*"):
            return True
        if fnmatch.fnmatch(Path(rel).name, clean):
            return True
    return False


def collect_files(patterns: list[str]) -> list[Path]:
    files = []
    for path in sorted(PROJECT_ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(PROJECT_ROOT)
        parts = rel.parts
        if any(p.startswith(".") and p not in (".gitignore", ".gitkeep") for p in parts[:-1]):
            continue
        if is_ignored(path, patterns):
            continue
        files.append(path)
    return files


def create_repo(token: str, name: str, private: bool) -> dict:
    resp = requests.post(
        "https://api.github.com/user/repos",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
        json={"name": name, "private": private, "auto_init": False},
    )
    if resp.status_code == 422:
        print(f"  Repositório '{name}' já existe — continuando upload...")
        resp2 = requests.get(
            f"https://api.github.com/repos/{get_username(token)}/{name}",
            headers={"Authorization": f"token {token}"},
        )
        return resp2.json()
    resp.raise_for_status()
    return resp.json()


def get_username(token: str) -> str:
    resp = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"token {token}"},
    )
    resp.raise_for_status()
    return resp.json()["login"]


def upload_file(token: str, owner: str, repo: str, path: Path) -> None:
    rel = str(path.relative_to(PROJECT_ROOT))
    content = base64.b64encode(path.read_bytes()).decode()

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{rel}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

    existing = requests.get(url, headers=headers).json()
    sha = existing.get("sha")

    payload = {"message": f"add {rel}", "content": content}
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=headers, json=payload)
    resp.raise_for_status()


def main() -> None:
    print("\n=== GitHub Push via API ===\n")
    token = input("Personal Access Token (repo scope): ").strip()
    if not token:
        sys.exit("Token não informado.")

    owner = get_username(token)
    print(f"  Usuário: {owner}")

    repo_name = input("Nome do repositório [Mining-Dark]: ").strip() or "Mining-Dark"
    private_input = input("Privado? [S/n]: ").strip().lower()
    private = private_input != "n"

    print(f"\n  Criando repositório '{repo_name}'...")
    create_repo(token, repo_name, private)

    patterns = load_gitignore_patterns()
    files = collect_files(patterns)
    print(f"  {len(files)} arquivos encontrados\n")

    for i, f in enumerate(files, 1):
        rel = f.relative_to(PROJECT_ROOT)
        print(f"  [{i}/{len(files)}] {rel}", end="\r")
        try:
            upload_file(token, owner, repo_name, f)
        except Exception as e:
            print(f"\n  ERRO em {rel}: {e}")

    print(f"\n\n  Concluído! https://github.com/{owner}/{repo_name}")


if __name__ == "__main__":
    main()
