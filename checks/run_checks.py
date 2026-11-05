#!/usr/bin/env python3
"""Chatbot QA with the Vibium CLI: accuracy checks, then citation checks.

The bot answers with a real model, so each prompt takes about 10 seconds.

Usage: python3 checks/run_checks.py [base_url]
Needs the `vibium` CLI (npm install -g vibium) or VIBIUM=/path/to/vibium.
Every browser action is a real `vibium` command; they are echoed with a leading "$".
"""
import json, os, subprocess, sys

VIBIUM = os.environ.get("VIBIUM", "vibium")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"
SHOTS = os.environ.get("SHOTS")  # optional folder for screenshots

CASES = [
    {"prompt": "How much does Qavio Pro cost?", "expect": ["$8"]},
    {"prompt": "How many projects are on the free plan?", "expect": ["3 projects"]},
    {"prompt": "Which formats can I export my tasks to?", "expect": ["PDF", "CSV"]},
    {"prompt": "What is your refund policy?", "expect": ["14 days"]},
    {"prompt": "How long is a password reset link valid?", "expect": ["30 minutes"]},
    {"prompt": "I was charged twice this month, please fix it", "expect": ["human agent"], "escalation": True},
    {"prompt": "What is the weather in Lahore today?", "expect": ["only help with questions about Qavio"], "refusal": True},
]
results = []

def vibium(*args):
    print("$ vibium " + " ".join('"%s"' % a if (" " in a or "#" in a) else a for a in args))
    out = subprocess.run([VIBIUM, *args], capture_output=True, text=True).stdout.strip()
    return out

def check(name, ok, detail):
    results.append(ok)
    print("    %-22s %s  %s" % (name, "PASS" if ok else "FAIL", detail))

def shot(name):
    if SHOTS: vibium("screenshot", "-o", os.path.join(SHOTS, name))

vibium("go", BASE)
citations = []
print("\n== Part 1: accuracy ==")
for n, case in enumerate(CASES, 1):
    print("\n[%d] %s" % (n, case["prompt"]))
    vibium("fill", "#prompt", case["prompt"])
    vibium("click", "#send")
    vibium("wait", "#answer-%d" % n)
    answer = vibium("text", "#answer-%d .answer-text" % n)
    print("    answer: " + answer)
    missing = [e for e in case["expect"] if e.lower() not in answer.lower()]
    check("refusal" if case.get("refusal") else "escalation" if case.get("escalation") else "accuracy", not missing,
          "matches expected" if not missing else 'expected "%s"' % missing[0])
    js = ("JSON.stringify({m:[...document.querySelectorAll('#answer-%d sup.cite a')].map(a=>a.dataset.cite),"
          "s:[...document.querySelectorAll('#answer-%d ol.sources li')].map(li=>({href:li.querySelector('a').href,"
          "quote:li.querySelector('q').textContent}))})" % (n, n))
    if case.get("escalation"):
        badge = vibium("text", "#handoff-%d" % n)
        check("handoff badge", "HUMAN AGENT" in badge.upper(), "handed to a human agent" if "HUMAN AGENT" in badge.upper() else "no handoff shown")
    raw = vibium("eval", js)
    try: data = json.loads(json.loads(raw) if raw.startswith('"') else raw)
    except Exception: data = {"m": [], "s": []}
    citations.append((n, data))
    shot("chat_%d.png" % n)

print("\n== Part 2: citations ==")
for n, data in citations:
    markers, sources = data["m"], data["s"]
    print("\n[%d] %d marker(s), %d source(s)" % (n, len(markers), len(sources)))
    if not markers and not sources:
        check("no citation needed", bool(CASES[n - 1].get("refusal")), "refusal has no sources"); continue
    orphans = [m for m in markers if int(m) > len(sources)]
    check("marker has source", not orphans, "all markers listed" if not orphans else "[%s] has no source" % orphans[0])
    for i, src in enumerate(sources, 1):
        name = src["href"].rsplit("/", 1)[-1]
        vibium("go", src["href"])
        title = vibium("eval", "document.title").strip('"')
        alive = title != "Error response"
        check("source %d resolves" % i, alive, name if alive else name + " is a 404")
        shot("src_%d_%d.png" % (n, i))
        if alive:
            page = vibium("text")
            found = src["quote"].lower() in page.lower()
            check("quote on page", found, '"%s"' % src["quote"] if found else 'not found: "%s"' % src["quote"])

vibium("stop")
print("\n== Summary ==")
print("%d prompts, %d checks: %d passed, %d failed" % (len(CASES), len(results), sum(results), len(results) - sum(results)))
sys.exit(0 if all(results) else 1)
