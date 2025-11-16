#!/usr/bin/env python3
import argparse
import os
from textwrap import dedent


RFCS = [
    (123, "A Proferred Official ICP"),
    (2345, "Domain Names and Company Name Retrieval"),
    (3457, "Requirements for IPsec Remote Access Scenarios"),
]


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)
    return path


def write_single_rfc(target_dir: str, rfc_num: int, title: str):
    ensure_dir(target_dir)
    content = dedent(
        f"""\
        RFC {rfc_num} - {title}

        This is a sample RFC document for testing the P2P-CI system.

        Abstract:
        This document describes {title.lower()}.

        1. Introduction
        This RFC provides specifications for {title.lower()}.

        2. Implementation
        The implementation details are provided here.

        3. Conclusion
        This concludes the RFC document.
        """
    )
    filepath = os.path.join(target_dir, f"rfc{rfc_num}.txt")
    with open(filepath, "w") as file_obj:
        file_obj.write(content)

    print(f"Created rfc{rfc_num}.txt in '{target_dir}'")


def build_default_dirs():
    return [f"peer{i + 1}_rfcs" for i in range(len(RFCS))]


def main():
    parser = argparse.ArgumentParser(
        description="Create per-peer RFC directories with one sample RFC each."
    )
    parser.add_argument(
        "directories",
        nargs="*",
        help="Directories for each sample RFC (default: peer1_rfcs ...)",
    )
    args = parser.parse_args()

    target_dirs = args.directories or build_default_dirs()

    if len(target_dirs) != len(RFCS):
        parser.error(
            f"Need exactly {len(RFCS)} directories to map one RFC per peer "
            f"(got {len(target_dirs)})."
        )

    for directory, (rfc_num, title) in zip(target_dirs, RFCS):
        write_single_rfc(directory, rfc_num, title)

    print("Done.")


if __name__ == "__main__":
    main()
