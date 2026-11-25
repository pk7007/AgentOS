"""gen codex | host: write host plugin files from the definitions. Needs no initialized state."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEFS = REPO / "definitions"


def register(sub, common) -> None:
    p = sub.add_parser("gen", help="generate host plugin files from the definitions")
    s = p.add_subparsers(dest="gen_cmd", metavar="HOST")
    c = s.add_parser("codex", parents=[common], help="Codex plugin, agents and config snippet")
    c.add_argument("--out", type=Path, default=REPO / "plugins" / "codex")
    c.add_argument("--defs", type=Path, default=DEFS)
    c.add_argument("--force", action="store_true", help="overwrite files changed by hand")
    c.set_defaults(func=cmd_codex)
    h = s.add_parser("host", parents=[common], help="any host described by a TOML profile")
    h.add_argument("--profile", type=Path, required=True)
    h.add_argument("--out", type=Path, required=True)
    h.add_argument("--defs", type=Path, default=DEFS)
    h.add_argument("--force", action="store_true", help="overwrite files changed by hand")
    h.set_defaults(func=cmd_host)


def _report(result, out: Path) -> dict:
    def rel(ps):
        return [p.relative_to(out.resolve()).as_posix() for p in ps]

    return {"out": str(out.resolve()), "written": rel(result.written), "skipped_modified": rel(result.skipped_modified)}


def cmd_codex(args, ctx):
    from agentos.gen import codex

    return _report(codex.generate(args.defs, args.out, force=args.force), args.out)


def cmd_host(args, ctx):
    from agentos.gen import host

    return _report(host.generate(args.defs, args.profile, args.out, force=args.force), args.out)
