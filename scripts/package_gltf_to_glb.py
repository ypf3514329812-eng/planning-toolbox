"""Pack a glTF JSON document and its local buffers/images into one GLB.

The utility intentionally supports the small, audited single-buffer assets used
by Planning Toolbox.  It has no third-party dependency and never downloads
content; all referenced files must be beside the input document.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
from typing import Any


def _pad4(data: bytes, fill: bytes = b"\x00") -> bytes:
    return data + fill * ((-len(data)) % 4)


def package_gltf_to_glb(source: Path, output: Path) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    document = json.loads(source.read_text(encoding="utf-8"))
    buffers = document.get("buffers", [])
    if len(buffers) != 1 or not buffers[0].get("uri"):
        raise ValueError("当前轻量打包器只支持一个本地外部 buffer。")

    binary_path = source.parent / str(buffers[0]["uri"])
    binary = bytearray(binary_path.read_bytes())
    buffer_views = document.setdefault("bufferViews", [])
    embedded_images = 0
    for image in document.get("images", []):
        uri = image.get("uri")
        if not uri:
            continue
        image_path = source.parent / str(uri)
        binary.extend(b"\x00" * ((-len(binary)) % 4))
        offset = len(binary)
        payload = image_path.read_bytes()
        binary.extend(payload)
        buffer_views.append(
            {
                "buffer": 0,
                "byteOffset": offset,
                "byteLength": len(payload),
            }
        )
        image.pop("uri", None)
        image["bufferView"] = len(buffer_views) - 1
        embedded_images += 1

    buffers[0].pop("uri", None)
    buffers[0]["byteLength"] = len(binary)
    json_payload = _pad4(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        b" ",
    )
    binary_payload = _pad4(bytes(binary))
    total_length = 12 + 8 + len(json_payload) + 8 + len(binary_payload)
    glb = b"".join(
        (
            struct.pack("<4sII", b"glTF", 2, total_length),
            struct.pack("<I4s", len(json_payload), b"JSON"),
            json_payload,
            struct.pack("<I4s", len(binary_payload), b"BIN\x00"),
            binary_payload,
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(glb)
    return {
        "source": str(source),
        "output": str(output),
        "size_bytes": len(glb),
        "embedded_images": embedded_images,
        "buffer_view_count": len(buffer_views),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack a local glTF asset into GLB")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = package_gltf_to_glb(args.source, args.output)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
