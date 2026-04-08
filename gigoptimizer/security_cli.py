from __future__ import annotations

import argparse
import getpass
import secrets
import sys

from .config import GigOptimizerConfig
from .services.auth_service import AuthService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GigOptimizer Pro security helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    hash_password = subparsers.add_parser("hash-password", help="Generate a PBKDF2 password hash.")
    hash_password.add_argument("--password", default="", help="Plaintext password. Prompts when omitted.")

    subparsers.add_parser("generate-secret", help="Generate a session secret.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "hash-password":
        password = args.password or getpass.getpass("Admin password: ")
        if not password:
            print("Password cannot be empty.", file=sys.stderr)
            return 1
        service = AuthService(GigOptimizerConfig())
        print(service.hash_password(password))
        return 0

    if args.command == "generate-secret":
        print(secrets.token_urlsafe(48))
        return 0

    parser.print_help()
    return 1
