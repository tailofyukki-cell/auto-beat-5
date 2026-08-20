"""音声デコード失敗を調査するため、WAVヘッダーと利用可能なデコーダーの結果を出力する。"""
from __future__ import annotations

import struct
import sys
import traceback
from pathlib import Path


def print_result(label: str, callback: object) -> None:
    try:
        value = callback()  # type: ignore[operator]
        print(f"{label}: OK\n{value}")
    except Exception as error:
        print(f"{label}: FAILED\n{type(error).__name__}: {error}")
        traceback.print_exc(limit=2)


def wav_header(path: Path) -> str:
    raw = path.read_bytes()[:128]
    if len(raw) < 12 or raw[:4] not in {b"RIFF", b"RF64"} or raw[8:12] != b"WAVE":
        return f"not a RIFF/RF64 WAVE header: {raw[:12]!r}"
    offset = 12
    rows: list[str] = [f"container={raw[:4].decode('ascii', 'replace')}"]
    while offset + 8 <= len(raw):
        chunk_id = raw[offset : offset + 4].decode("ascii", "replace")
        chunk_size = struct.unpack_from("<I", raw, offset + 4)[0]
        payload = raw[offset + 8 : offset + 8 + min(chunk_size, 64)]
        rows.append(f"chunk={chunk_id} size={chunk_size}")
        if chunk_id == "fmt " and len(payload) >= 16:
            tag, channels, rate, byte_rate, block_align, bits = struct.unpack_from("<HHIIHH", payload)
            rows.append(
                f"format_tag=0x{tag:04X} channels={channels} sample_rate={rate} "
                f"byte_rate={byte_rate} block_align={block_align} bits_per_sample={bits}"
            )
            if len(payload) >= 18:
                rows.append(f"fmt_extension_size={struct.unpack_from('<H', payload, 16)[0]}")
        offset += 8 + chunk_size + (chunk_size % 2)
    return "\n".join(rows)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/diagnose_audio_format.py <audio-file>")
    path = Path(sys.argv[1]).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")
    print(f"path={path}\nsize_bytes={path.stat().st_size}")
    print_result("wav_header", lambda: wav_header(path))

    import soundfile as sf

    print_result("soundfile.info", lambda: sf.info(str(path)))
    print_result("soundfile.read", lambda: tuple(item for item in sf.read(str(path), frames=22050)))

    import librosa

    print_result("librosa.load", lambda: tuple(item.shape if hasattr(item, "shape") else item for item in librosa.load(str(path), sr=22050, mono=True)))


if __name__ == "__main__":
    main()
