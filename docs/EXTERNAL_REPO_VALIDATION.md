# External repo validation — §3.5

**Status: EXECUTED, 2026-07-29.** The demo repo exists and both runs are
recorded. What follows is the plan as carried out, kept because it documents
how to reproduce the setup.

| Run | Result | Link |
|---|---|---|
| Baseline captured and verified clean | success | [`30425018340`](https://github.com/yash161004/mcplock-demo/actions/runs/30425018340) |
| Injected description drift | **failure at HIGH severity** | [`30425300912`](https://github.com/yash161004/mcplock-demo/actions/runs/30425300912) |

Repo: [yash161004/mcplock-demo](https://github.com/yash161004/mcplock-demo)
(public, zero credentials — targets `@modelcontextprotocol/server-filesystem`).
Both runs are linked from the mcplock README.

One deviation from the plan below: the drift injection lives in a committed
script rather than an inline workflow step, because the inline heredoc could not
navigate the snapshot dict structure correctly.

**Prerequisite (satisfied):** mcplock had to be published on PyPI before the
Action could resolve `mcplock` (the default value of `mcplock-version`) without
a git URL. PyPI now serves 1.0.1.

## The plan as executed

### Create a minimal public repo

```bash
gh repo create mcplock-demo --public --clone
cd mcplock-demo
```

### Contents

```
mcplock-demo/
├── .github/
│   └── workflows/
│       └── mcplock-check.yml
├── data/                    # <-- server-filesystem target dir
│   └── sample.txt
└── README.md
```

### Baseline workflow (green run)

`.github/workflows/mcplock-check.yml`:

```yaml
name: mcplock check
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Snapshot baseline
        uses: yash161004/mcplock/.github/actions/mcp-lock-action@master
        with:
          server: 'npx -y @modelcontextprotocol/server-filesystem ./data'
      - name: Verify against baseline
        uses: yash161004/mcplock/.github/actions/mcp-lock-action@master
        with:
          server: 'npx -y @modelcontextprotocol/server-filesystem ./data'
```

Step 1 initialises the snapshot if none exists (exit 2 = missing baseline
becomes a stored snapshot). Step 2 re-checks it and exits 0 if clean.

### Deliberately broken run

Modify the baseline snapshot to inject a description change, or swap the
not-yet-created snapshot for a fixture that differs from the live server's
output. The Action's `check` exits 1 when drift at or above `--fail-on`
(default `high`) is detected.

### Link both from README

After both workflow runs are recorded, add badge links to the demo repo's
README showing the green run and a screenshot of the failing run.

---

Both steps above were run and both links are live. This satisfies the brief's
§6 success metric: the Action works in a repository that is not this one.
