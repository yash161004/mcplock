# External repo validation plan — §3.5

**Prerequisite:** mcplock 0.1.1 must be published on PyPI before the
Action can resolve `mcplock` (the default value of `mcplock-version`)
without a git URL.

## Once 0.1.1 is live

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

**This file is a plan, not a completed deliverable.** Execute it after
0.1.1 is on PyPI and `pip install mcplock` resolves without a git URL.
The demo repo can be created any time; the first CI run must wait.
