import argparse
import json
import pathlib
import sys

from .gate import promote, rollback


def main() -> int:
    p = argparse.ArgumentParser(prog="mlplat")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("promote", "rollback"):
        s = sub.add_parser(name)
        s.add_argument("--registry", default="registry/registry.json")
        if name == "promote":
            s.add_argument("version")
            s.add_argument("--holdout", default="tests/holdout.json")
    a = p.parse_args()
    if a.cmd == "rollback":
        print("active:", rollback(pathlib.Path(a.registry)))
        return 0
    problems = promote(pathlib.Path(a.registry), a.version, json.loads(pathlib.Path(a.holdout).read_text()))
    for x in problems:
        print("refused:", x, file=sys.stderr)
    if not problems:
        print("active:", a.version)
    return 1 if problems else 0


sys.exit(main())
