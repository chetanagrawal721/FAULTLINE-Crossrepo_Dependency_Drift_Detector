#!/usr/bin/env python3
"""Faultline playbook tracker.

Single source of truth: playbook/phases/*.yaml (milestones and test cases) + playbook/phases.yaml.
State: playbook/state.json.  Outputs: LOGBOOK.md (append-only), CHECKLIST.md and docs/FAULTLINE_PLAYBOOK.md (generated).

Usage (run from the repository root):
  python tools/track.py status [--gate G]
  python tools/track.py next
  python tools/track.py start M1.4
  python tools/track.py tc TC-1.4.1 pass --evidence "tests/out/m1.4.txt" --note "ran make e2e"
  python tools/track.py tc TC-1.4.1 fail --note "reference also failed"
  python tools/track.py done M1.4                  # refuses unless every test case passed
  python tools/track.py done M1.4 --waive "reason" # records the waiver in the log; use sparingly
  python tools/track.py block M1.4 --reason "docker not installed"
  python tools/track.py gate C                     # checks and declares a gate
  python tools/track.py note "free text for the logbook"
  python tools/track.py render                     # regenerates CHECKLIST.md and the playbook
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PB = os.path.join(ROOT, "playbook")
STATE = os.path.join(PB, "state.json")
LOG = os.path.join(ROOT, "LOGBOOK.md")
CHECK = os.path.join(ROOT, "CHECKLIST.md")
PLAYBOOK = os.path.join(ROOT, "docs", "FAULTLINE_PLAYBOOK.md")

LOG_HEADER = """# FAULTLINE LOGBOOK

Append-only record of build progress. Entries are written by `tools/track.py` when a milestone starts,
a test case is recorded, a milestone completes (or is blocked or waived), or a gate is declared.
Do not edit past entries. Add context with `python tools/track.py note "..."`.

Format: `### <UTC time> | <EVENT> | <id> | by <name>` followed by details.

---
"""


def now():
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")


def who(args=None):
    if args is not None and getattr(args, "by", None):
        return args.by
    if os.environ.get("FAULTLINE_USER"):
        return os.environ["FAULTLINE_USER"]
    try:
        return subprocess.check_output(["git", "config", "user.name"], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip() or "unknown"
    except Exception:
        return "unknown"


def sort_key(mid):
    m = re.match(r"M(\d+)\.(\w+)$", mid)
    ph, rest = int(m.group(1)), m.group(2)
    return (ph, 9999 if rest == "G" else int(rest))


def load_plan():
    meta = yaml.safe_load(open(os.path.join(PB, "phases.yaml"), encoding="utf-8"))
    miles, exits = {}, {}
    for f in sorted(glob.glob(os.path.join(PB, "phases", "*.yaml"))):
        d = yaml.safe_load(open(f, encoding="utf-8"))
        for m in d["milestones"]:
            m["phase"] = int(m["id"][1:].split(".")[0])
            if m["id"] in miles:
                sys.exit(f"duplicate milestone {m['id']}")
            miles[m["id"]] = m
        if d.get("gate_exit"):
            exits[d["gate_exit"]["id"]] = d["gate_exit"]
    tcs = {}
    for m in miles.values():
        for t in m.get("tcs", []):
            if t["id"] in tcs:
                sys.exit(f"duplicate test case {t['id']}")
            t["milestone"] = m["id"]
            tcs[t["id"]] = t
    return meta, miles, tcs, exits


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    return {"milestones": {}, "tcs": {}, "gates": {}}


def save_state(s):
    json.dump(s, open(STATE, "w", encoding="utf-8"), indent=2, sort_keys=True)


def log(event, ident, lines, by):
    if not os.path.exists(LOG) or os.path.getsize(LOG) == 0:
        open(LOG, "w", encoding="utf-8").write(LOG_HEADER)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n### {now()} | {event} | {ident} | by {by}\n")
        for ln in lines:
            if ln:
                f.write(f"- {ln}\n")


def mstat(s, mid):
    return s["milestones"].get(mid, {}).get("status", "todo")


def tc_counts(s, miles, mid):
    ids = [t["id"] for t in miles[mid].get("tcs", [])]
    ok = sum(1 for i in ids if s["tcs"].get(i, {}).get("status") == "pass")
    return ok, len(ids)


def cmd_start(a, meta, miles, tcs, exits, s):
    mid = a.id
    if mid not in miles:
        sys.exit(f"unknown milestone {mid}")
    s["milestones"].setdefault(mid, {})
    s["milestones"][mid].update(status="in_progress", started=now())
    save_state(s)
    log("START", mid, [miles[mid]["title"]], who(a))
    print(f"started {mid}: {miles[mid]['title']}")


def cmd_tc(a, meta, miles, tcs, exits, s):
    if a.id not in tcs:
        sys.exit(f"unknown test case {a.id}")
    if a.result == "pass" and not a.evidence:
        sys.exit("a PASS must cite evidence: --evidence <path, command output file, or CI run url>")
    s["tcs"][a.id] = {"status": a.result, "date": now(), "evidence": a.evidence or "", "note": a.note or ""}
    mid = tcs[a.id]["milestone"]
    s["milestones"].setdefault(mid, {}).setdefault("status", "in_progress")
    if s["milestones"][mid]["status"] == "todo":
        s["milestones"][mid]["status"] = "in_progress"
    save_state(s)
    log(f"TC {a.result.upper()}", a.id, [tcs[a.id]["title"], f"evidence: {a.evidence}" if a.evidence else "",
                                      a.note or ""], who(a))
    ok, n = tc_counts(s, miles, mid)
    print(f"{a.id} -> {a.result}  ({mid}: {ok}/{n} test cases passed)")


def cmd_done(a, meta, miles, tcs, exits, s):
    mid = a.id
    if mid not in miles:
        sys.exit(f"unknown milestone {mid}")
    missing = [t["id"] for t in miles[mid].get("tcs", []) if s["tcs"].get(t["id"], {}).get("status") != "pass"]
    if missing and not a.waive:
        sys.exit(f"cannot complete {mid}: test cases not passed: {', '.join(missing)}")
    entry = s["milestones"].setdefault(mid, {})
    entry.update(status="done", done=now())
    if missing:
        entry["waived"] = {"tcs": missing, "reason": a.waive, "date": now()}
    save_state(s)
    ok, n = tc_counts(s, miles, mid)
    lines = [miles[mid]["title"], f"test cases passed: {ok}/{n}"]
    if missing:
        lines.append(f"WAIVED {', '.join(missing)}: {a.waive}")
    log("DONE (waived)" if missing else "DONE", mid, lines, who(a))
    cmd_render(a, meta, miles, tcs, exits, s, quiet=True)
    print(f"{mid} done ({ok}/{n})" + (" WITH WAIVER" if missing else ""))


def cmd_block(a, meta, miles, tcs, exits, s):
    s["milestones"].setdefault(a.id, {}).update(status="blocked", reason=a.reason)
    save_state(s)
    log("BLOCKED", a.id, [a.reason], who(a))
    print(f"{a.id} blocked")


def gate_milestones(miles, g):
    return [m for m in sorted(miles, key=sort_key) if miles[m]["gate"] == g]


def gate_state(meta, miles, s, g):
    ms = gate_milestones(miles, g)
    pending = [m for m in ms if mstat(s, m) != "done"]
    waived = [m for m in ms if s["milestones"].get(m, {}).get("waived")]
    req = [r for r in meta["gates"][g]["requires"] if r not in s["gates"]]
    return ms, pending, waived, req


def cmd_gate(a, meta, miles, tcs, exits, s):
    g = a.id
    if g not in meta["gates"]:
        sys.exit(f"unknown gate {g}")
    ms, pending, waived, req = gate_state(meta, miles, s, g)
    print(f"Gate {g} - {meta['gates'][g]['name']}: {len(ms) - len(pending)}/{len(ms)} milestones done")
    if req:
        print("  prerequisite gates not declared:", ", ".join(req))
    for m in pending:
        print(f"  pending {m} [{mstat(s, m)}] {miles[m]['title']}")
    if waived:
        print("  waivers recorded on:", ", ".join(waived))
    if a.check:
        return
    if pending or req:
        sys.exit(f"Gate {g} cannot be declared")
    if waived and not a.accept_waivers:
        sys.exit("waivers exist; review them and rerun with --accept-waivers to declare the gate")
    s["gates"][g] = {"declared": now(), "waivers": waived}
    save_state(s)
    log("GATE DECLARED", f"Gate {g}", [meta["gates"][g]["name"],
                                       f"waivers: {', '.join(waived)}" if waived else "no waivers"], who(a))
    cmd_render(a, meta, miles, tcs, exits, s, quiet=True)
    print(f"Gate {g} declared")


def cmd_note(a, meta, miles, tcs, exits, s):
    log("NOTE", "-", [a.text], who(a))
    print("logged")


def cmd_status(a, meta, miles, tcs, exits, s):
    tot_t = sum(len(m.get("tcs", [])) for m in miles.values())
    ok_t = sum(1 for t in tcs if s["tcs"].get(t, {}).get("status") == "pass")
    done = sum(1 for m in miles if mstat(s, m) == "done")
    print(f"Milestones {done}/{len(miles)} done | test cases {ok_t}/{tot_t} passed | gates declared: "
          f"{', '.join(sorted(s['gates'])) or 'none'}")
    for g in meta["gates"]:
        if a.gate and g != a.gate:
            continue
        ms = gate_milestones(miles, g)
        d = sum(1 for m in ms if mstat(s, m) == "done")
        print(f"\nGate {g} ({meta['gates'][g]['name']}): {d}/{len(ms)}" + ("  [DECLARED]" if g in s["gates"] else ""))
        for m in ms:
            ok, n = tc_counts(s, miles, m)
            print(f"  [{ {'done':'x','in_progress':'~','blocked':'!','todo':' '}[mstat(s, m)] }] {m:6} {miles[m].get('hackathon','-'):3} {ok}/{n} {miles[m]['title']}")


def cmd_next(a, meta, miles, tcs, exits, s):
    order = sorted(miles, key=sort_key)
    cur = [m for m in order if mstat(s, m) == "in_progress"]
    if cur:
        m = cur[0]
        print(f"IN PROGRESS: {m} {miles[m]['title']}")
    else:
        todo = [m for m in order if mstat(s, m) == "todo" and miles[m]["gate"] != "X"]
        if not todo:
            print("nothing left outside expansion")
            return
        m = todo[0]
        print(f"NEXT: {m} {miles[m]['title']}   (run: python tools/track.py start {m})")
    for t in miles[m].get("tcs", []):
        st = s["tcs"].get(t["id"], {}).get("status", "-")
        print(f"   {st:5} {t['id']} {t['title']}")


# ---------------------------------------------------------------- rendering
def render_checklist(meta, miles, tcs, s):
    out = ["# FAULTLINE CHECKLIST", "",
           "Generated by `python tools/track.py render`. Do not edit by hand: change state with the tracker.",
           f"Last rendered: {now()}", "",
           "Legend: `[x]` done and all test cases passed, `[~]` in progress, `[!]` blocked, `[ ]` not started. "
           "Priority P0 = needed for a convincing demo, P1 = strongly improves it, P2 = can be cut.", ""]
    tot_t = len(tcs)
    ok_t = sum(1 for t in tcs if s["tcs"].get(t, {}).get("status") == "pass")
    done = sum(1 for m in miles if mstat(s, m) == "done")
    out += [f"**Overall:** {done}/{len(miles)} milestones, {ok_t}/{tot_t} test cases passed.", "",
            "| Gate | Name | Milestones | Declared |", "|---|---|---|---|"]
    for g, gm in meta["gates"].items():
        ms = gate_milestones(miles, g)
        d = sum(1 for m in ms if mstat(s, m) == "done")
        decl = s["gates"].get(g, {}).get("declared", "no")
        out.append(f"| {g} | {gm['name']} | {d}/{len(ms)} | {decl} |")
    out.append("")
    for g, gm in meta["gates"].items():
        ms = gate_milestones(miles, g)
        if not ms:
            continue
        out += [f"## Gate {g}: {gm['name']}", ""]
        for m in ms:
            st = mstat(s, m)
            box = {"done": "x", "in_progress": "~", "blocked": "!", "todo": " "}[st]
            ok, n = tc_counts(s, miles, m)
            w = " (WAIVER)" if s["milestones"].get(m, {}).get("waived") else ""
            amend = " **[amendment]**" if miles[m].get("amend") else ""
            out.append(f"- [{box}] **{m}** {miles[m]['title']} ({miles[m].get('hackathon', '-')}, "
                       f"{miles[m]['tier']}) {ok}/{n}{w}{amend}")
            for t in miles[m].get("tcs", []):
                ts = s["tcs"].get(t["id"], {}).get("status")
                tb = {"pass": "x", "fail": "!"}.get(ts, " ")
                out.append(f"  - [{tb}] {t['id']} {t['title']}")
            if st == "blocked":
                out.append(f"  - BLOCKED: {s['milestones'][m].get('reason', '')}")
        out.append("")
    return "\n".join(out) + "\n"


def md_escape(x):
    return str(x).replace("|", "\\|").replace("\n", " ")


def render_playbook(meta, miles, tcs, exits):
    intro = open(os.path.join(PB, "intro.md"), encoding="utf-8").read()
    outro = open(os.path.join(PB, "outro.md"), encoding="utf-8").read()
    intro = intro.replace("{{PRIORITY_TABLE}}", priority_table(miles))
    out = [intro, "\n---\n\n# PART C - PHASE-BY-PHASE IMPLEMENTATION\n",
           "Every milestone lists tasks, files, and the **test cases that must pass before it is marked done**. "
           "`[AMENDMENT]` marks a change I made to plan v3.1; everything else follows the plan.\n"]
    by_phase = {}
    for m in sorted(miles, key=sort_key):
        by_phase.setdefault(miles[m]["phase"], []).append(m)
    for ph in sorted(by_phase):
        pm = meta["phases"][ph]
        out.append(f"\n## Phase {ph}: {pm['name']}  (gate {pm['gate']})\n")
        for mid in by_phase[ph]:
            m = miles[mid]
            tag = " [AMENDMENT]" if m.get("amend") else ""
            out.append(f"### {mid} {m['title']}{tag}\n")
            out.append(f"**Gate:** {m['gate']} | **Tier:** {m['tier']} | **Hackathon priority:** {m.get('hackathon', '-')}\n")
            if m.get("amend"):
                out.append(f"> **Amendment.** {m['amend']}\n")
            out.append(f"**Goal.** {m['goal']}\n")
            out.append("**Tasks**\n")
            out += [f"- {t}" for t in m["tasks"]]
            if m.get("files"):
                out.append("\n**Expected files:** " + ", ".join(f"`{f}`" for f in m["files"]) + "\n")
            out.append("\n**Validation test cases** (all must pass before `done`)\n")
            out.append("| ID | Test | Kind | Steps | Expected result |")
            out.append("|---|---|---|---|---|")
            for t in m["tcs"]:
                out.append(f"| {t['id']} | {md_escape(t['title'])} | {t['kind']} | {md_escape(t['steps'])} | {md_escape(t['expect'])} |")
            out.append(f"\n**Record progress:** `python tools/track.py start {mid}`, then "
                       f"`python tools/track.py tc {m['tcs'][0]['id']} pass --evidence <file-or-url>` for each test case, "
                       f"then `python tools/track.py done {mid}`.\n")
    out.append("\n---\n\n# PART D - GATE EXIT CRITERIA\n")
    for gid, e in exits.items():
        out.append(f"**Gate {gid}.** {e['statement']}  \n*Must not claim:* {e['must_not_claim']}\n")
    out.append(outro)
    return "\n".join(out)


def priority_table(miles):
    rows = ["| Priority | Milestones (build order) |", "|---|---|"]
    for pr, label in (("P0", "P0 - needed for a convincing demo"), ("P1", "P1 - strongly improves it"),
                      ("P2", "P2 - can be cut")):
        ids = [m for m in sorted(miles, key=sort_key) if miles[m].get("hackathon") == pr]
        rows.append(f"| {label} | " + ", ".join(ids) + " |")
    return chr(10).join(rows)


def cmd_render(a, meta, miles, tcs, exits, s, quiet=False):
    open(CHECK, "w", encoding="utf-8").write(render_checklist(meta, miles, tcs, s))
    os.makedirs(os.path.dirname(PLAYBOOK), exist_ok=True)
    open(PLAYBOOK, "w", encoding="utf-8").write(render_playbook(meta, miles, tcs, exits))
    if not quiet:
        print("rendered CHECKLIST.md and docs/FAULTLINE_PLAYBOOK.md")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--by", help="who is recording this (default: git user.name)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("render")
    sub.add_parser("next")
    x = sub.add_parser("status"); x.add_argument("--gate")
    x = sub.add_parser("start"); x.add_argument("id")
    x = sub.add_parser("tc"); x.add_argument("id"); x.add_argument("result", choices=["pass", "fail"])
    x.add_argument("--evidence"); x.add_argument("--note")
    x = sub.add_parser("done"); x.add_argument("id"); x.add_argument("--waive")
    x = sub.add_parser("block"); x.add_argument("id"); x.add_argument("--reason", required=True)
    x = sub.add_parser("gate"); x.add_argument("id"); x.add_argument("--check", action="store_true")
    x.add_argument("--accept-waivers", action="store_true")
    x = sub.add_parser("note"); x.add_argument("text")
    a = p.parse_args()
    meta, miles, tcs, exits = load_plan()
    s = load_state()
    {"render": cmd_render, "next": cmd_next, "status": cmd_status, "start": cmd_start, "tc": cmd_tc,
     "done": cmd_done, "block": cmd_block, "gate": cmd_gate, "note": cmd_note}[a.cmd](a, meta, miles, tcs, exits, s)
    if a.cmd in ("start", "tc", "block"):
        cmd_render(a, meta, miles, tcs, exits, load_state(), quiet=True)


if __name__ == "__main__":
    main()
