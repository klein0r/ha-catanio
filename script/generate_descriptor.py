"""Generate the protobuf descriptor set used by the CatanIO client.

The upstream schemas annotate fields with nanopb options. Those options only
limit the embedded encoder and are not needed to encode or decode messages, so
they are stripped before compiling. This keeps ``nanopb.proto`` and
``google/protobuf/descriptor.proto`` out of the descriptor set.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import tempfile

from grpc_tools import protoc

ROOT = Path(__file__).resolve().parent.parent
PROTO_DIR = ROOT / "proto"
OUTPUT = ROOT / "custom_components" / "catanio" / "api" / "catanio.binpb"
SCHEMAS = ("shared.proto", "sys.proto", "ui.proto", "uoi.proto", "dor.proto")

NANOPB_IMPORT = re.compile(r'^\s*import\s+"nanopb\.proto";\s*$', re.MULTILINE)
NANOPB_OPTIONS = re.compile(r"\s*\[\s*\(nanopb\)[^\]]*\]")


def strip_nanopb(source: str) -> str:
    """Remove nanopb imports and field options from a schema."""
    return NANOPB_OPTIONS.sub("", NANOPB_IMPORT.sub("", source))


def main() -> int:
    """Compile the schemas into a descriptor set."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for schema in SCHEMAS:
            source = (PROTO_DIR / schema).read_text(encoding="utf-8")
            (tmp_dir / schema).write_text(strip_nanopb(source), encoding="utf-8")

        result = protoc.main(
            [
                "protoc",
                f"--proto_path={tmp_dir}",
                f"--descriptor_set_out={OUTPUT}",
                "--include_imports",
                *SCHEMAS,
            ]
        )
    if result != 0:
        return result
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
