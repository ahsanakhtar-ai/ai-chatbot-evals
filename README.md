# AI chatbot evals: a practice support bot tested in a real browser

![I tried Vibium, then I made it QA a chatbot](docs/banner.jpg)

![Vibium](https://img.shields.io/badge/browser%20automation-Vibium-f05a28)
![MCP](https://img.shields.io/badge/protocol-MCP-e8408a)
![Codex](https://img.shields.io/badge/model%20%2B%20judge-Codex%20CLI-4cd680)
![Langfuse](https://img.shields.io/badge/traces%20%2B%20scores-Langfuse-ff5c6c)
![Docker](https://img.shields.io/badge/self--hosted-Docker-4f7cff)
![Python](https://img.shields.io/badge/python-3.9%2B-3776ab)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**Built by [Ahsan Akhtar](https://github.com/ahsanakhtar-ai)** as part of my "Ahsan with AI" experiments.

Most chatbot evals read the model's text. This one checks what the user actually sees: it opens the chatbot in a real browser, asks questions, and follows every citation to see if it holds up.

It answers three questions about a chatbot reply:

1. **Is it accurate?** Does the answer match the expected one?
2. **Are the citations real?** Does every `[n]` have a source, does the link open, and is the quoted text on that page?
3. **Is it grounded?** A second model acts as judge and scores accuracy, hallucination and citation support.

## Contents

- [What is in here](#what-is-in-here)
- [Tech stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Browser checks with Vibium](#browser-checks-with-vibium)
- [Judge with Codex, store in Langfuse](#judge-with-codex-store-in-langfuse)
- [Project structure](#project-structure)
- [Limits and honest notes](#limits-and-honest-notes)
- [Author](#author)
- [License](#license)

## What is in here

**Qavio Support** is a support assistant for a made-up product called Qavio. The layout follows the look of McKay Wrigley's chatbot-ui (dark sidebar, chat history, model selector, message actions); the code here is written from scratch.

The answers are not scripted. `server.py` sends each message to a real model together with `kb.md`, the assistant's knowledge notes, and the model returns its reasoning, an answer and numbered citations to the help pages in `help/`.

Two notes in `kb.md` are out of date on purpose, so the checks have something real to catch:

- the free plan note says "unlimited projects", while `help/pricing.html` says 3 projects
- the export note cites `help/export-guide.html`, a page that no longer exists

![Qavio Support answering with reasoning and numbered sources](docs/chatbot.jpg)

## Tech stack

| Part | What I used | Why |
|---|---|---|
| Browser automation | [Vibium](https://github.com/VibiumDev/vibium) CLI (v26.8.21) with Chrome for Testing | Drives a real browser from the command line: `go`, `map`, `fill`, `click`, `wait`, `text`, `eval`, `screenshot` |
| Agent connection | Vibium's MCP server (`vibium mcp`) | Same browser tools over the Model Context Protocol |
| Chat model | Codex CLI (`codex exec`) | Answers from the knowledge notes, no API key in the repo |
| Judge model | Codex CLI (`codex exec`) | Scores each answer with a fixed judge prompt |
| Traces and scores | [Langfuse](https://langfuse.com) v4, self-hosted with Docker Compose | Stores each chat as a trace with its scores and the judge's reasoning |
| Chat UI and help pages | Plain HTML, CSS and JavaScript | No build step |
| Server and scripts | Python 3 standard library | No packages to install |

## Prerequisites

- Python 3.9 or newer
- Node.js 18 or newer, for `npm install -g vibium` (Vibium downloads its own Chrome for Testing)
- The Codex CLI, signed in (`codex` on your PATH, or set `CODEX=/path/to/codex`)
- Only for the Langfuse part: Docker Desktop, and a Langfuse instance (self-hosted or cloud) with a project's public and secret key

## Quick start

```bash
git clone https://github.com/ahsanakhtar-ai/ai-chatbot-evals.git
cd ai-chatbot-evals
python3 server.py 4173
```

Open http://localhost:4173 and ask a question. Each reply takes about 10 seconds, because a real model is answering.

## Browser checks with Vibium

```bash
npm install -g vibium
python3 checks/run_checks.py
```

`checks/run_checks.py` types each prompt, waits for the reply and reads it back, then follows every citation.

| Check | What it does |
|---|---|
| accuracy | the reply contains the expected answer |
| refusal | an out-of-scope question is declined |
| escalation + handoff badge | a billing dispute is handed to a human agent |
| marker has source | every `[n]` has an entry in the sources list |
| source resolves | the cited link opens (not a 404) |
| quote on page | the quoted text is really on the cited page |

![Following a citation to a help page that does not exist](docs/citation-check.jpg)

My run: 7 prompts, 28 checks, 24 passed, 4 failed. Three failures come from the two stale notes (wrong free-plan answer, its quote missing from the page, the dead link). The fourth was not planted: the model quoted a sentence that is not word for word on the pricing page.

![24 of 28 checks passed](docs/scorecard.jpg)

## Judge with Codex, store in Langfuse

`evals/judge_pipeline.py` asks the bot each prompt, fetches the cited help pages, asks Codex to score accuracy, hallucination and citation support with a fixed judge prompt, and writes the traces and scores to Langfuse.

Create `evals/.env` (never commit it; `.gitignore` already excludes it):

```
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-...
LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-...
```

Then, with the chatbot server running:

```bash
python3 evals/judge_pipeline.py
```

![Judge scores in the local Langfuse](docs/langfuse-scores.jpg)

My run wrote 7 traces and 21 scores, and the judge agreed with the browser checks. Langfuse's built-in LLM-as-a-Judge evaluators were not used, because they need a model API key; the scores come from this script. Traces go to Langfuse's OpenTelemetry endpoint, since Langfuse v4 no longer accepts traces on the older ingestion endpoint.

## Project structure

```
index.html              chat UI (Qavio Support)
server.py               static server + POST /api/chat (calls the model)
kb.md                   the assistant's knowledge notes (two are stale on purpose)
help/                   help-center pages the bot cites
checks/run_checks.py    browser checks through the Vibium CLI
evals/judge_pipeline.py Codex as judge, results written to Langfuse
docs/                   images for this README
```

## Limits and honest notes

- Qavio is a made-up product and the knowledge base is tiny. This is a practice setup, not a benchmark.
- A real model answers and judges, so results can differ from run to run.
- Relevance and multi-turn checks are not implemented.
- The checks match quotes word for word, which is strict by design.

## Author

**Ahsan Akhtar** builds and tests AI agents in public under "Ahsan with AI".

- GitHub: [@ahsanakhtar-ai](https://github.com/ahsanakhtar-ai)
- If this was useful, a star on the repo helps other people find it.
- Found a case the checks miss? Open an issue, I would like to see it.

## License

MIT. See [LICENSE](LICENSE).
