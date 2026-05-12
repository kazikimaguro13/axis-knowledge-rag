"""AUTO_GENERATED marker block handling.

Allows human-written Markdown and AI-generated sections to coexist in the
same document. Blocks are delimited by:

    <!-- AUTO_GENERATED_START: <name> -->
    ...
    <!-- AUTO_GENERATED_END: <name> -->

Regenerating a block overwrites only the content between its delimiters,
preserving everything else (= the human-written part).
"""

import re
from dataclasses import dataclass

NAME_PATTERN = r"[a-zA-Z0-9_-]+"
_START_RE = re.compile(r"<!--\s*AUTO_GENERATED_START:\s*(" + NAME_PATTERN + r")\s*-->")
_END_RE = re.compile(r"<!--\s*AUTO_GENERATED_END:\s*(" + NAME_PATTERN + r")\s*-->")
_BLOCK_RE = re.compile(
    r"<!--\s*AUTO_GENERATED_START:\s*(?P<name>" + NAME_PATTERN + r")\s*-->\n"
    r"(?P<content>.*?)"
    r"\n<!--\s*AUTO_GENERATED_END:\s*(?P=name)\s*-->",
    re.DOTALL,
)


class MarkerError(Exception):
    pass


@dataclass
class MarkerBlock:
    name: str
    content: str
    raw_full: str  # full match including delimiters


def extract_blocks(text: str) -> list[MarkerBlock]:
    """Return all AUTO_GENERATED blocks in document order."""
    blocks: list[MarkerBlock] = []
    for m in _BLOCK_RE.finditer(text):
        blocks.append(
            MarkerBlock(
                name=m.group("name"),
                content=m.group("content"),
                raw_full=m.group(0),
            )
        )
    return blocks


def validate_balance(text: str) -> list[str]:
    """Return a list of validation errors (empty list if balanced)."""
    starts = [(m.group(1), m.start()) for m in _START_RE.finditer(text)]
    ends = [(m.group(1), m.start()) for m in _END_RE.finditer(text)]
    errors: list[str] = []
    if len(starts) != len(ends):
        errors.append(
            f"Marker count mismatch: {len(starts)} starts, {len(ends)} ends"
        )
    s_names = [n for n, _ in starts]
    e_names = [n for n, _ in ends]
    if sorted(s_names) != sorted(e_names):
        errors.append(
            f"Marker name mismatch: starts={s_names} ends={e_names}"
        )
    return errors


def update_block(text: str, name: str, new_content: str) -> str:
    """Replace an existing block's content. If absent, append at the end."""
    if not re.match(rf"^{NAME_PATTERN}$", name):
        raise MarkerError(f"Invalid marker name: {name!r}")

    new_content = new_content.rstrip("\n")
    replacement = (
        f"<!-- AUTO_GENERATED_START: {name} -->\n"
        f"{new_content}\n"
        f"<!-- AUTO_GENERATED_END: {name} -->"
    )

    block_re = re.compile(
        r"<!--\s*AUTO_GENERATED_START:\s*" + re.escape(name) + r"\s*-->\n"
        r".*?"
        r"\n<!--\s*AUTO_GENERATED_END:\s*" + re.escape(name) + r"\s*-->",
        re.DOTALL,
    )
    if block_re.search(text):
        return block_re.sub(replacement, text, count=1)

    # Append at end (with leading newline if needed)
    sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    return text + sep + replacement + "\n"


def strip_blocks(text: str) -> str:
    """Remove all AUTO_GENERATED blocks (delimiters included)."""
    return _BLOCK_RE.sub("", text)


def _main(argv: list[str]) -> int:
    import argparse
    import sys
    from pathlib import Path

    p = argparse.ArgumentParser()
    p.add_argument("file", type=Path)
    p.add_argument("--list", action="store_true")
    p.add_argument("--update", action="store_true")
    p.add_argument("--strip", action="store_true")
    p.add_argument("--validate", action="store_true")
    p.add_argument("--name")
    p.add_argument("--content")
    args = p.parse_args(argv[1:])

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 1
    text = args.file.read_text(encoding="utf-8").replace("\r\n", "\n")

    if args.list:
        blocks = extract_blocks(text)
        print(f"{len(blocks)} block(s):")
        for b in blocks:
            print(f"  - {b.name}: {len(b.content)} chars")
        return 0

    if args.validate:
        errs = validate_balance(text)
        if errs:
            for e in errs:
                print(f"❌ {e}")
            return 1
        print("✅ Balanced")
        return 0

    if args.update:
        if not args.name or args.content is None:
            print("Usage: --update --name <name> --content <text>", file=sys.stderr)
            return 1
        new_text = update_block(text, args.name, args.content)
        args.file.write_text(new_text, encoding="utf-8")
        print(f"Updated block '{args.name}' in {args.file}")
        return 0

    if args.strip:
        new_text = strip_blocks(text)
        args.file.write_text(new_text, encoding="utf-8")
        print(f"Stripped all blocks from {args.file}")
        return 0

    print("Specify one of: --list / --update / --strip / --validate", file=sys.stderr)
    return 1


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv))
