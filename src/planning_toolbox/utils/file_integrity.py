"""Input-file integrity helpers used by read-only CAD workflows."""

import hashlib
from pathlib import Path


def sha256_file(path: Path | str) -> str:
    """Return a streaming SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_file_unchanged(path: Path | str, expected_sha256: str) -> None:
    """Raise if an input file changed while a read-only workflow was running."""
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            "源文件在处理期间发生变化，系统已停止返回结果。请检查文件是否被其他程序占用或修改。"
        )
