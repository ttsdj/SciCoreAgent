# PubMed Literature MCP Server

PubMed literature search, fetch, and RNA-seq method extraction via NCBI E-utilities API.

## Quickstart

```bash
# Set environment
export NCBI_EMAIL="your_email@example.com"
export NCBI_API_KEY="optional_api_key"  # Optional, increases rate limit to 10 req/s

# Test search
python -m mcp_servers.pubmed_literature.server --test-search "RNA-seq differential expression"

# Check status
python -m mcp_servers.pubmed_literature.server --status

# Run as MCP server
python -m mcp_servers.pubmed_literature.server --stdio
```

## Tools

| Tool | Description |
|---|---|
| `pubmed_search` | Search PubMed for articles, returns PMIDs |
| `pubmed_fetch_details` | Fetch detailed article metadata (title, abstract, authors, etc.) |
| `pubmed_extract_rnaseq_methods` | Deterministic extraction of RNA-seq methods/software from abstracts |
| `pubmed_save_to_rag` | Save articles and review rows to SQLite FTS5 RAG |
| `pubmed_literature_review` | One-stop: search → fetch → extract → save → generate reports |

## Configuration

| Env Var | Required | Description |
|---|---|---|
| `NCBI_EMAIL` | Yes | Email for NCBI API identification |
| `NCBI_API_KEY` | No | API key for higher rate limit (10 vs 3 req/s) |
| `NCBI_TOOL` | No | Tool name registered with NCBI |

## Rate Limiting

- Without API key: 3 requests/second
- With API key: 10 requests/second

## Key Design Rules

1. `corresponding_author` is always `null` unless explicitly found in PubMed metadata
2. Parameters are never invented — if not in the abstract, `parameters: null`
3. Every extracted field traces back to `evidence_text` from the source
4. `last_author ≠ corresponding_author` — we never conflate them
