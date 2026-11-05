#!/usr/bin/env python3
"""Local server for the Qavio Support practice chatbot.

Serves the static page and POST /api/chat, which asks a real model for the answer.
The model is the Codex CLI (`codex exec`) using your own Codex login; set CODEX=/path/to/codex if needed.
No API keys are stored here.
"""
import json, os, subprocess, sys, tempfile, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = os.path.dirname(os.path.abspath(__file__))
CODEX = os.environ.get("CODEX", "codex")
KB = open(os.path.join(ROOT, "kb.md")).read()
PROMPT = """You are Qavio Support, the customer support assistant for Qavio (a project management app).
Do not use any tools or read any files. Answer ONLY from the knowledge notes below.
Rules:
- Keep the answer to one or two short sentences. Do not write [1] style markers in the answer text.
- Cite every article the notes list for the fact you use, in order, as numbered citations.
  Each citation has the article title, its url exactly as written, and a short quote of the sentence you relied on.
- If the customer has a billing dispute (for example a duplicate charge), do not try to solve it:
  say you are handing the conversation to a human agent, set "escalate" to true, and cite the billing article.
- If the question is not about Qavio, reply exactly: "I can only help with questions about Qavio." with no citations.
- "reasoning" is 2 to 4 short steps describing how you got the answer.
Reply with ONLY this JSON:
{"reasoning": ["..."], "answer": "...", "citations": [{"title": "...", "url": "...", "quote": "..."}], "escalate": false}

KNOWLEDGE NOTES
%s

CUSTOMER MESSAGE
%s
"""

def ask_model(message):
    t0 = time.time()
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "out.txt")
        subprocess.run([CODEX, "exec", "--skip-git-repo-check", "-s", "read-only", "-o", out, PROMPT % (KB, message)],
                       cwd=d, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        raw = open(out).read().strip() if os.path.exists(out) else ""
    start, end = raw.find("{"), raw.rfind("}")
    data = json.loads(raw[start:end + 1])
    data["seconds"] = round(time.time() - t0, 1)
    data["model"] = "Codex (codex exec)"
    return data

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=ROOT, **k)
    def log_message(self, *a): pass
    def do_POST(self):
        if self.path != "/api/chat": self.send_error(404); return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        try: data = ask_model(str(body.get("message", ""))[:500])
        except Exception as e: data = {"reasoning": [], "answer": "Sorry, the model did not answer. Please try again.", "citations": [], "escalate": False, "error": str(e)[:200]}
        payload = json.dumps(data).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4173
    print("Qavio Support practice chatbot on http://localhost:%d" % port)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
