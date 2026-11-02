# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

import secrets
import uuid

while True:
    value = secrets.randbits(128)
    value = (value & ~(0xF << 76)) | (6 << 76)  # UUIDv6
    value = (value & ~(0x3 << 62)) | (2 << 62)  # RFC 4122 variant

    if value >> 124 >= 0xA:
        print(uuid.UUID(int=value))
        break
