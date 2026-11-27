"""gen codex | host | schemas | docs: write host plugin files, JSON schemas and the command reference from the definitions. Needs no initialized state."""

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
    sc = s.add_parser("schemas", parents=[common], help="JSON Schema files for AgentOS records")
    sc.add_argument("--out", type=Path, default=REPO / "schemas")
    sc.set_defaults(func=cmd_schemas)
    d = s.add_parser("docs", parents=[common],
                     help="docs/CLI.md, the command reference, and docs/REASONS.md, every refusal reason")
    d.add_argument("--out", type=Path, default=REPO / "docs" / "CLI.md")
    d.set_defaults(func=cmd_docs)


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


def cmd_schemas(args, ctx):
    from agentos.gen import schemas

    return {"out": str(args.out.resolve()), "written": schemas.generate(args.out)}


def cmd_docs(args, ctx):
    from agentos.gen import clidocs, reasons

    return {"written": clidocs.generate(args.out),
            "reasons": reasons.generate(Path(args.out).parent / "REASONS.md")}
