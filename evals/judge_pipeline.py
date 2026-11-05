#!/usr/bin/env python3
"""External evaluation pipeline: Codex as the judge, scores written to a local Langfuse.

For each practice-chatbot answer: ask the bot (localhost:4173), fetch the help pages it cites,
ask Codex (`codex exec`) to judge accuracy, grounding (hallucination) and citation support with a fixed
judge prompt, then write the trace and the scores to Langfuse through its public ingestion API.
Keys are read from langfuse/.env and are never printed.
"""
import base64, json, os, re, subprocess, sys, tempfile, time, urllib.request, uuid, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = dict(l.strip().split("=", 1) for l in open(os.path.join(HERE, ".env")) if "=" in l and not l.startswith("#"))
HOST = ENV["LANGFUSE_HOST"]; AUTH = base64.b64encode(("%s:%s" % (ENV["LANGFUSE_INIT_PROJECT_PUBLIC_KEY"], ENV["LANGFUSE_INIT_PROJECT_SECRET_KEY"])).encode()).decode()
CODEX = os.environ.get("CODEX", "codex"); BOT = "http://localhost:4173"
CASES = [
    ("How much does Qavio Pro cost?", "Pro costs $8 per member per month."),
    ("How many projects are on the free plan?", "The free plan includes 3 projects."),
    ("Which formats can I export my tasks to?", "Tasks can be exported as PDF or CSV."),
    ("What is your refund policy?", "Full refund within 14 days of purchase."),
    ("How long is a password reset link valid?", "The reset link is valid for 30 minutes."),
    ("I was charged twice this month, please fix it", "The assistant hands the billing dispute to a human agent."),
    ("What is the weather in Lahore today?", "The assistant refuses because the question is not about Qavio."),
]
JUDGE = """You are an evaluation judge for a customer support chatbot. Do not use any tools.
Score the ANSWER on three criteria. Each score is 1 (good) or 0 (bad), with one sentence of reasoning.
- accuracy: does the ANSWER agree with the EXPECTED answer?
- hallucination: 1 if the ANSWER contains a claim that the SOURCE PAGES do not support (or contradict), else 0.
  If there are no source pages and the answer makes no factual claim about the product, use 0.
- citation_support: 1 if every cited page exists and contains the quoted text, else 0. If nothing is cited and nothing needed citing, use 1.
Reply with ONLY this JSON:
{"accuracy": {"score": 0, "reasoning": "..."}, "hallucination": {"score": 0, "reasoning": "..."}, "citation_support": {"score": 0, "reasoning": "..."}}

QUESTION: %s
EXPECTED: %s
ANSWER: %s
CITATIONS: %s
SOURCE PAGES:
%s
"""
def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=180) as r: return r.status, r.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
def page_text(url):
    code, body = http(BOT + url)
    if code != 200: return "[%s returned HTTP %d: page does not exist]" % (url, code)
    return "[%s]\n%s" % (url, re.sub(r"\s+", " ", re.sub(r"<style.*?</style>|<[^>]+>", " ", body, flags=re.S)).strip())
def codex(prompt):
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "o.txt")
        subprocess.run([CODEX, "exec", "--skip-git-repo-check", "-s", "read-only", "-o", out, prompt], cwd=d, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
        raw = open(out).read()
    return json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
def kv(k, v): return {"key": k, "value": {"stringValue": v if isinstance(v, str) else json.dumps(v)}}
HDR = {"Content-Type": "application/json", "Authorization": "Basic " + AUTH}
# remove scores from earlier runs so the project only shows this run
code, body = http(HOST + "/api/public/scores?limit=100", headers=HDR)
for sc in (json.loads(body).get("data", []) if code == 200 else []): urllib.request.urlopen(urllib.request.Request(HOST + "/api/public/scores/" + sc["id"], method="DELETE", headers=HDR))
spans, batch = [], []
for q, expected in CASES:
    s0 = time.time_ns(); _, body = http(BOT + "/api/chat", {"message": q}, {"Content-Type": "application/json"}); bot = json.loads(body); s1 = time.time_ns()
    pages = "\n".join(page_text(c["url"]) for c in bot.get("citations", [])) or "(none cited)"
    verdict = codex(JUDGE % (q, expected, bot["answer"], json.dumps(bot.get("citations", [])), pages))
    tid, sid = uuid.uuid4().hex, uuid.uuid4().hex[:16]
    spans.append({"traceId": tid, "spanId": sid, "name": "qavio-support-chat", "kind": 1, "startTimeUnixNano": str(s0), "endTimeUnixNano": str(s1), "attributes": [
        kv("langfuse.trace.name", "qavio-support-chat"), kv("langfuse.trace.input", q), kv("langfuse.trace.output", bot["answer"]),
        kv("langfuse.observation.type", "generation"), kv("langfuse.observation.input", q), kv("langfuse.observation.output", bot["answer"]),
        kv("langfuse.observation.model.name", "codex-exec"), kv("langfuse.observation.metadata.expected", expected),
        kv("langfuse.observation.metadata.reasoning", bot.get("reasoning", [])), kv("langfuse.observation.metadata.citations", bot.get("citations", []))]})
    for name in ("accuracy", "hallucination", "citation_support"):
        v = verdict[name]
        batch.append({"id": str(uuid.uuid4()), "type": "score-create", "timestamp": now(), "body": {"id": str(uuid.uuid4()), "traceId": tid, "observationId": sid, "name": name, "value": int(v["score"]), "dataType": "NUMERIC", "comment": "Codex judge: " + v["reasoning"]}})
    print("%-48s accuracy=%s hallucination=%s citation_support=%s" % (q[:48], verdict["accuracy"]["score"], verdict["hallucination"]["score"], verdict["citation_support"]["score"]))
    print("    hallucination: " + verdict["hallucination"]["reasoning"][:150])
otlp = {"resourceSpans": [{"resource": {"attributes": [kv("service.name", "qavio-support")]}, "scopeSpans": [{"scope": {"name": "judge_pipeline"}, "spans": spans}]}]}
code, body = http(HOST + "/api/public/otel/v1/traces", otlp, HDR)
print("Langfuse OTLP traces: HTTP %d %s" % (code, body[:120]))
code, body = http(HOST + "/api/public/ingestion", {"batch": batch}, HDR)
res = json.loads(body) if body.startswith("{") else {}
print("Langfuse scores: HTTP %d, %d accepted, %d errors" % (code, len(res.get("successes", [])), len(res.get("errors", []))))
if res.get("errors"): print(json.dumps(res["errors"][:1])[:300])
