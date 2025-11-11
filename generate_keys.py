"""Module to securely generate and display random URL-safe Base64 keys."""

import base64
import os


def generate_secure_key(length: int = 32) -> str:
    """Generate a secure random key encoded in URL-safe Base64 format."""
    random_bytes = os.urandom(length)
    encoded_key = base64.urlsafe_b64encode(random_bytes).rstrip(b"=")
    return encoded_key.decode("utf-8")


def main() -> None:
    """Generate and display two secure random keys."""
    key1 = generate_secure_key()
    key2 = generate_secure_key()

    # Display generated keys
    output = f"Generated Keys:\n\nDatabase Key:\n{key1}\n\nApplication Key:\n{key2}\n"
    os.write(1, output.encode())


if __name__ == "__main__":
    main()
