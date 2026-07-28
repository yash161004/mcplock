# Responsible disclosure policy

This policy is published *before* any findings exist, so that it is clearly not
written to fit a particular case.

mcplock inspects publicly available MCP server tool definitions. When it
surfaces something that looks like a real ambiguity, missing scope boundary, or
unannounced change in a third-party server, we handle it as follows.

## 1. Private report first

We contact the maintainer privately before anyone else — via the project's
declared security contact, `SECURITY.md`, a private GitHub security advisory, or
the maintainer's published email, in that order of preference. The report
includes:

- the affected server, version/commit, and tool name(s)
- the exact tool definition text as we observed it, with the date observed
- a clear reproduction (the `mcplock` command and its output)
- why we believe an agent could be misled by it
- our proposed disclosure date

## 2. 90-day window

The default window is 90 days from the date of first private contact.

- Shorter if the maintainer fixes it sooner — we publish once a fix is released.
- Longer only if the maintainer is actively engaged and asks for more time with
  a concrete plan. Silence is not a reason to extend.

## 3. No public mention before then

Until the issue is fixed or the window lapses, we do not name the server or the
finding publicly — not in the README, not in `FINDINGS.md`, not in talks, posts,
or screenshots. Aggregate statistics that cannot identify a specific server are
the only exception.

## 4. Honest credit

The public writeup records the maintainer's response as it actually happened —
fast fix, no response, or disagreement — without editorializing. If a maintainer
disputes that a finding is a real issue, their position is stated alongside ours.

## 5. Scope of this policy

We report on *tool definitions* — names, descriptions, and input schemas that are
publicly readable from a server's `tools/list`. We do not test authentication,
attempt to access other users' data, run denial-of-service tests, or exploit any
issue beyond what is needed to confirm it.

## Reporting an issue in mcplock itself

Open a private security advisory on this repository. The same 90-day standard
applies to us.
