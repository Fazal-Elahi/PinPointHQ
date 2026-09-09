#!/usr/bin/env python3
"""Show the precedent store learning across four runs.

    python3 run_learning.py

Runs the pipeline four times with --auto and reports, for each, how many Gate 1
decisions the human was asked for versus how many a stored precedent answered.
Full transcripts land in out/scenario_N.txt.
"""
import subprocess, json, sys, os, shutil

PY = "../.venv/bin/python" if os.path.exists("../.venv/bin/python") else sys.executable
SCENARIOS = [
 ("1. Cold start",
  "Acme · original file · precedents wiped",
  ["--forget", "--source","fixtures/legacy_ats_small.csv", "--account","fixtures/target_account.json"],
  "Nothing is known. Every mapping and every status decision is asked."),
 ("2. Same account, new file",
  "Acme · second file, same column shape",
  ["--source","fixtures/legacy_ats_second.csv", "--account","fixtures/target_account.json"],
  "Semantic precedent AND bindings both apply. Only genuinely new statuses are asked."),
 ("3. New account, same file shape",
  "Beta · original file",
  ["--source","fixtures/legacy_ats_small.csv", "--account","fixtures/target_account_beta.json"],
  "Transforms carry over. Value maps do NOT — Beta's job and stage ids are different."),
 ("4. Same account, a stage was retired",
  "Acme v2 · original file · stage 12 deleted",
  ["--source","fixtures/legacy_ats_small.csv", "--account","fixtures/target_account_acme_v2.json"],
  "The stored binding points at a stage that no longer exists. It is invalidated, not repaired."),
]

rows=[]
for i,(name, setup, args, expect) in enumerate(SCENARIOS, start=1):
    print(f"\n{'='*78}\n{name}\n  {setup}\n  expect: {expect}\n{'='*78}")
    r=subprocess.run([PY,"run_demo.py","--auto","--no-execute"]+args,
                     capture_output=True, text=True)
    open(f"out/scenario_{i}.txt","w").write(r.stdout+r.stderr)
    if r.returncode!=0:
        print(f"  FAILED (exit {r.returncode}) — see out/scenario_{i}.txt"); print(r.stdout[-1500:]); sys.exit(1)
    L=json.load(open("out/learning.json"))
    M=json.load(open("workbook/manifest.json"))
    rows.append((name, L, M))
    print(f"  asked={L['asked']}  from precedent={L['prefilled']}  invalidated={L['invalidated']}"
          f"   |  tier1={M['counts']['tier1_rows']} tier2={M['counts']['tier2_rows']}"
          f" queued={M['counts']['queued']}")

print(f"\n\n{'='*78}\n  THE LEARNING CURVE\n{'='*78}")
print(f"  {'scenario':<36} {'sem':>4} {'bind':>5} {'model':>6} {'reuse':>6} {'ask':>4} {'stale':>6} {'auto':>6}")
print("  "+"-"*74)
for name,L,M in rows:
    tot=L["asked"]+L["prefilled"]+L["by_model"]
    pct=f"{(tot-L['asked'])*100//tot}%" if tot else "-"
    print(f"  {name:<36} {'YES' if L['semantic_hit'] else '-':>4} "
          f"{'YES' if L['binding_hit'] else '-':>5} "
          f"{L['by_model']:>6} {L['prefilled']:>6} {L['asked']:>4} {L['invalidated']:>6} {pct:>6}")
print("  "+"-"*74)
print("""
  sem / bind  did a stored precedent of that kind apply
  model       status decisions the AI matched by name against this account's stages
  reuse       decisions a stored binding supplied, re-resolved as still valid first
  ask         decisions that reached a human
  stale       stored ids that no longer existed, thrown away rather than repaired

  Read it this way:

  1 -> 2  The same customer sending another export of the same shape is nearly free.
          Both stores apply. That is the case Technical Success actually sees most.
  2 -> 3  A DIFFERENT customer keeps the file-shape knowledge (sem YES) and loses the
          account knowledge (bind -). Not a limitation, the safety property: replaying
          'Phone Screen -> stage 12' into another tenant points at a different job.
  3 -> 4  When the destination changes under a stored binding, it is invalidated and
          re-asked. Never quietly repaired: a stage id that silently moved is how a
          migration lands people in the wrong pipeline.

  Retention appears in no column here. It is asked every run, by design.
""")
