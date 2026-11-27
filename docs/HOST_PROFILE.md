# Host profiles

`agentos gen codex` writes a ready-made Codex plugin into `plugins/codex/`.
Any other host that loads plugins from a folder of files can be described by a
small TOML profile and generated with `agentos gen host`.

A profile only names files and folders. It holds no secrets and no model settings.

```toml
manifest_dir      = ".myhost-plugin"   # folder that holds the plugin manifest
manifest_file     = "plugin.json"      # manifest file name: {name, version, description}
instructions_file = "MYHOST.md"        # short project instructions pointing at the skill
agents_dir        = "agents"           # one Markdown file per agent, YAML front matter
skills_dir        = "skills"           # the agentos skill is copied to <skills_dir>/agentos/SKILL.md
```

```
agentos gen host --profile hosts\myhost.local.toml --out out\myhost
```

Profiles named `*.local.toml` and the `out/` folder are kept out of version control,
so a profile for your own tools stays on your machine. A UTF-8 byte-order mark (which
Notepad and Windows PowerShell 5.1 add) is fine.

## What gets written

| File | From |
| --- | --- |
| `<manifest_dir>/<manifest_file>` | `definitions/plugin.toml` |
| `<instructions_file>` | fixed text: admit before spawning, grade with evidence, hand over before stopping |
| `<skills_dir>/agentos/SKILL.md` | `definitions/skills/agentos/SKILL.md` |
| `<agents_dir>/<id>.md` | each `definitions/agents/<id>.toml` |

Agent files list read-only tools (`Read, Grep, Glob`) for read-only templates, and add
`Edit, Write, Bash` otherwise. A template's `tools_allow` replaces that list and
`tools_deny` removes entries from it.

## Your edits are kept

Every generator records a hash of each file it wrote in `<out>/.agentos-gen.json`.
On the next run, a file whose content no longer matches its recorded hash was changed
by hand. A file that already existed before the generator first ran counts as yours too.
Both are skipped and listed under `skipped_modified`. Pass `--force` to overwrite them.

## Codex

`plugins/codex/` contains:

- `.codex-plugin/plugin.json`: the plugin manifest, with the skill folder at `./skills/`.
- `agents/<id>.toml`: custom agent files (`developer_instructions`, `sandbox_mode = "read-only"`
  for read-only templates, `model_reasoning_effort` from the template's reasoning hint).
- `config-snippet.toml`: an `[agents]` block (`max_threads = 4`, `max_depth = 2`, matching
  the agentos defaults) that registers each agent file. **agentos never edits your Codex
  config.** Copy what you want into it yourself.
- `.agents/plugins/marketplace.json`: a local marketplace entry, so the folder can be added
  as a plugin source.

## Adapter keys

Optional keys, used by the native adapter (`agentos host ...`, see [HOSTS.md](HOSTS.md)):

```toml
hooks_file          = "hooks/hooks.json"  # write the runtime hooks here
runtime_host        = "cc"                # which `agentos hook run <host>` the hooks call (required with hooks_file)
executable          = "myhost"            # the host CLI, for `--version` in `host list` and drift
plugins_dir         = "~/.myhost/plugins" # scanned by `host check` for other plugins' hooks and agents
agents_home         = "~/.myhost/agents"  # user-level agents, also scanned by `host check`
register_hint       = "myhost plugin add {dest}"  # printed after `host install`
plugin_instructions = false               # skip the instructions file at the plugin root
```

`agentos host install cc` looks for the profile at `~/.agentos/hosts/cc.toml`, then at
`hosts/cc.local.toml` in a checkout (git-excluded).

## Model tiers (optional)

`agentos intel route TASK --host HOST` can pick a model tier and a fallback order, but only from tiers the
host says it has. AgentOS does not guess which models an account can use, so without this table the
answer is `availability: unknown`. List the model name your host uses for each tier you have:

```toml
[models]
small  = "the-host-small-model"
medium = "the-host-medium-model"
large  = "the-host-large-model"   # leave a tier out, or set it to "", if you do not have it
```

The tiers are `small`, `medium` and `large`. For Codex, put the table in `~/.agentos/hosts/codex.toml`
(Codex needs no other key there). When a tier is missing, high-risk work only falls back to a larger
tier; only low-risk work may fall back to a smaller one.

