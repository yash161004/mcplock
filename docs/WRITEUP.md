# Why Cosine Similarity Fails to Catch Confusable MCP Tools

*An empirical evaluation of tool ambiguity detection in Model Context Protocol (MCP) servers, and why structural schema substitutability outperforms text vector similarity.*

---

## 1. The Problem: Tool Selection Drift in LLM Agents

Model Context Protocol (MCP) servers expose tool definitions (`tools/list`) to LLM agents at runtime. An agent selects tools based on their string names, natural language descriptions, and JSON schema parameter definitions.

When an MCP server declares multiple tools with overlapping capabilities or ambiguous descriptions (for example, `read_file`, `read_text_file`, and `read_media_file`), LLMs frequently select the wrong tool or fail to construct valid arguments. As MCP servers grow in tool count, detecting confusable tool definitions before deployment becomes a necessary quality and security control.

---

## 2. The Naive Approach: TF-IDF Cosine Similarity

The standard approach to identifying duplicate or confusable text in software tooling is TF-IDF (Term Frequency-Inverse Document Frequency) vectorization followed by cosine similarity scoring.

Under this approach:
1. Tool descriptions are tokenized into term vectors.
2. Pairwise cosine similarity is computed between all tool description vectors on a server.
3. Pairs exceeding a similarity threshold (typically 0.80 or 0.85) are flagged as confusable.

---

## 3. Why Text Vector Similarity Fails (Empirical Data)

We evaluated TF-IDF cosine similarity against the 14 tools of the official `@modelcontextprotocol/server-filesystem` server, producing $\binom{14}{2} = 91$ distinct tool pairs.

### Findings

1. **Zero Detections at Standard Thresholds**: At an 85% cosine similarity threshold ($0.85$), TF-IDF cosine similarity flagged **0 out of 91 tool pairs**.
2. **Linear Inseparability**: Lowering the threshold failed to improve precision. Confusable tool pairs (such as `read_file` vs. `read_text_file`) and clearly distinct tool pairs (such as `read_file` vs. `write_file`) yielded overlapping cosine similarity distributions. 

### Why Cosine Similarity Collapses on Tool Definitions

- **Shared Domain Vocabulary**: Specialized MCP servers repeat identical domain vocabulary across unrelated tools (e.g., `path`, `directory`, `file`, `filesystem`, `permissions`). High term overlap reflects server domain scope, not tool confusability.
- **Opposing Verbs Carry Minimal Weight**: A tool pair like `read_file` and `write_file` shares 80%+ of its description tokens ("file from the local file system"). Cosine similarity treats the single opposing verb (`read` vs `write`) as a minor lexical difference, despite it representing opposite operations.

---

## 4. The Solution: Schema Substitutability Gating

To solve the linear inseparability of text-vector methods, `mcplock` introduces a **two-pass ambiguity pipeline** that gates text scoring behind structural schema analysis.

```
       All Tool Pairs (91)
               │
               ▼
┌──────────────────────────────┐
│ Schema Substitutability Gate │ ──(Fails Gate: 63 pairs)──► Discarded
└──────────────────────────────┘
               │
               ▼ (Passes Gate: 28 pairs)
┌──────────────────────────────┐
│  Affinity & Contrast Engine  │ ──(Opposing Verb Veto)───► Discarded
└──────────────────────────────┘
               │
               ▼ (Scored Output)
      Flagged Pairs (4)
```

### Pass 1: Structural Schema Substitutability

Before evaluating description text, `mcplock` evaluates whether one tool's input schema can accept arguments formatted for another tool. 

Two schemas $A$ and $B$ are **substitutable** if:
- All required properties of schema $A$ exist in schema $B$ with compatible types.
- Neither schema enforces conflicting required parameters that would cause immediate validation failure.

If two tools cannot accept mutually substitutable arguments, an LLM agent cannot inadvertently call tool $B$ using arguments formatted for tool $A$. Therefore, non-substitutable pairs are eliminated immediately.

On the official filesystem server, **this structural gate removes 63 of 91 pairs before any text scoring occurs**.

### Pass 2: Name Affinity & Opposing-Verb Veto

For the remaining 28 candidate pairs, `mcplock` computes a composite score based on:
1. **Name Affinity**: Levenshtein distance and shared prefix/suffix tokens across tool names.
2. **Description Similarity**: Normalized token overlap on non-domain terms.
3. **Opposing-Verb Veto**: A hard veto applied if tool names or descriptions contain antonym pairs (`read`/`write`, `create`/`delete`, `encrypt`/`decrypt`).

---

## 5. Results

When run against the 14 real tools of `@modelcontextprotocol/server-filesystem`:

- **Flagged Pairs**: Exactly **4 pairs** are flagged:
  1. `read_file` / `read_text_file`
  2. `read_file` / `read_media_file`
  3. `read_text_file` / `read_media_file`
  4. `list_directory` / `list_directory_with_sizes`
- **Separation Gap**: The ambiguity scores for these 4 true confusable pairs sit between **0.42 and 0.48**, separated by a clean **0.33–0.50 score gap** from all non-confusable pairs.

```
Confusable Pairs:   [0.42 ──── 0.48]  <-- Flagged
                       (Gap: 0.33 - 0.50)
Distinct Pairs:     [0.00 ── 0.32]    <-- Passed
```

---

## 6. Scope & Limitations

This heuristic evaluates **documentation clarity and schema overlap**, not runtime implementation:
- A flagged pair indicates that an LLM agent is at risk of selecting the wrong tool or confusing arguments based on the published `tools/list` metadata.
- It does not inspect underlying source code execution or verify backend server behavior.

---

## 7. Conclusion & Reference Implementation

Treating tool ambiguity as a pure text similarity problem fails because tool metadata is structured. By pairing **schema substitutability gating** with **antonym-aware affinity scoring**, tool confusability can be detected deterministically.

`mcplock` is an open-source CLI and CI gating tool implementing schema substitutability and scope boundary linting for MCP servers.

- **Repository**: [github.com/yash161004/mcplock](https://github.com/yash161004/mcplock)
- **PyPI Package**: `pip install mcplock`
