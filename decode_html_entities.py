# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

import html
import re
import sys
from pathlib import Path


ENTITY_PATTERN = re.compile(r"&#(?:[xX][0-9A-Fa-f]+|[0-9]+);")


def decode_entity(match: re.Match[str]) -> str:
    return html.unescape(match.group())


def main() -> None:
    source_path, target_path = map(Path, sys.argv[1:])
    source_text = source_path.read_text(encoding="utf-8")
    decoded_text = ENTITY_PATTERN.sub(decode_entity, source_text)

    with target_path.open("x", encoding="utf-8") as target_file:
        target_file.write(decoded_text)


if __name__ == "__main__":
    main()
