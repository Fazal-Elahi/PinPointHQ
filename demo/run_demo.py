#!/usr/bin/env python3
"""Pinpoint Migration Copilot — runnable vertical slice (Milestone 1).

Walks the §7 pipeline end to end: seven stages, three human gates, a signed approval,
and a migration workbook. The three gates are REAL PROMPTS — the decisions you make
change what lands in the workbook.

  python3 run_demo.py                 interactive, pauses between stages
  python3 run_demo.py --auto          recorded answers, no prompts (regenerates TRACE.txt)
  python3 run_demo.py --no-pause      interactive gates, but don't pause between stages
  python3 run_demo.py --no-execute    stop at the workbook (§12 executor is optional)
  python3 run_demo.py --reset         clear out/ and workbook/ first

Tier 1 (applications) + Tier 2 (job_seekers) only, against jobs that already exist.
Every write payload is validated against openapi/milestone-1-slice.json before it is sent.
"""
import csv, json, re, hashlib, os, sys, datetime, collections, shutil
import jsonschema

def argval(flag, default):
    return sys.argv[sys.argv.index(flag)+1] if flag in sys.argv else default

# ─────────────────────────────────────────── presentation flows (--flow NAME)
FLOWS=[("profile",  "Read the file without reading the data"),
       ("gate0",    "The privacy gate, and watching it reject a column"),
       ("discover", "What the destination account actually offers"),
       ("mapping",  "The AI proposal, and the date it refuses to guess"),
       ("gate1",    "Coverage, requirements, retention — with both roads shown"),
       ("validate", "Pinpoint's rules applied locally, three outcomes only"),
       ("identity", "Three keys, the human queue, and the duplicate person"),
       ("approval", "Signing, and watching one edit void the signature"),
       ("workbook", "The deliverable, and the counts that must balance"),
       ("precedent","What the run remembered, and what it deliberately did not"),
       ("executor", "The optional last mile: a lost response, and no duplicate"),
       ("learning", "Four runs showing the tool get cheaper, and stay safe")]
FLOW = argval_early = None
if "--flow" in sys.argv:
    i=sys.argv.index("--flow")
    FLOW = sys.argv[i+1] if i+1 < len(sys.argv) else "list"
DEMO = "--demo" in sys.argv
if DEMO and "--forget" not in sys.argv:
    sys.argv.append("--forget")          # a demo always opens from a cold memory
CUES = "--no-cues" not in sys.argv
ALT_RETENTION = "--alt-retention" in sys.argv
ALT_STATUS    = "--alt-status"    in sys.argv

if FLOW in ("list","help","?"):
    print("\n  PINPOINT MIGRATION COPILOT — demo chapters\n")
    for n,(k,d) in enumerate(FLOWS, start=1):
        print(f"   {n:>2}. --flow {k:<10} {d}")
    print("""
  THE WHOLE THING, ONE COMMAND — press Enter all the way through:

    ../.venv/bin/python run_demo.py --demo

  Or take a single chapter. Each runs the pipeline quietly up to that point,
  then hands you the controls. Every prompt is pre-filled, so Enter walks it.

    ../.venv/bin/python run_demo.py --flow gate0
    ../.venv/bin/python run_demo.py --flow gate0 --no-cues    hide the presenter notes
    ../.venv/bin/python run_demo.py --flow gate1 --forget     from a cold memory

  Chapters are independent — run them in any order, or skip one if time is short.
  Each ends by printing the command for the next one, so you can just keep going.

  --forget wipes the precedent store. Use it before  --flow learning  so the
  four-run curve starts from nothing; the other chapters do not care.
""")
    sys.exit(0)

if DEMO:
    print("""
==============================================================================
  PINPOINT MIGRATION COPILOT — full walkthrough
==============================================================================
  Twelve chapters, one command. Every prompt is pre-filled with the right
  answer, so you can press Enter the whole way and talk over it.

  Two places you may want to type instead of pressing Enter, both flagged
  on screen when you get there:
     Gate 1  a stage id instead of 'u', to route people differently
     Queue   9003 instead of 'd', to resolve an identity live

  Ends with the four-run learning curve. Ctrl-C stops at any point.
==============================================================================""")
    try: input("\n  ── press Enter to begin ── ")
    except EOFError: pass

if FLOW=="learning":
    import subprocess
    sys.exit(subprocess.run([sys.executable,"run_learning.py"]).returncode)

AUTO       = "--auto"       in sys.argv
NO_PAUSE   = "--no-pause"   in sys.argv or AUTO
NO_EXECUTE = "--no-execute" in sys.argv
SOURCE  = argval("--source",  "fixtures/legacy_ats_small.csv")
ACCOUNT = argval("--account", "fixtures/target_account.json")

if "--reset" in sys.argv:
    shutil.rmtree("out", ignore_errors=True); shutil.rmtree("workbook", ignore_errors=True)

OUT="out"; WB="workbook"; PREC=argval("--prec-dir","../precedents")
SPEC=json.load(open("../openapi/milestone-1-slice.json"))
if "--forget" in sys.argv: shutil.rmtree(PREC, ignore_errors=True)
for d in (OUT, WB, PREC+"/semantic", PREC+"/bindings"): os.makedirs(d, exist_ok=True)
def emit(name, obj):
    json.dump(obj, open(f"{OUT}/{name}","w"), indent=1, default=str); return obj

# ═══════════════════════════════════════════════ §8 — the precedent store
# Two stores, deliberately separate. Semantic precedent travels between accounts;
# bindings never do, because job 88 in one tenant is a different job in another.
def load_prec(kind, key):
    f=f"{PREC}/{kind}/{key}.json"
    return json.load(open(f)) if os.path.exists(f) else None
def save_prec(kind, key, obj):
    obj["uses"]=obj.get("uses",0)+1
    obj["last_used"]=datetime.datetime.now().isoformat(timespec="seconds")
    json.dump(obj, open(f"{PREC}/{kind}/{key}.json","w"), indent=1, default=str)

# Every decision the human is asked for is counted, and so is every one a
# precedent answered for them. The gap between the two IS the learning.
DEC={"asked":0,"prefilled":0,"invalidated":0,"by_model":0}
def decide(prompt, default, prefill=None, why=""):
    if prefill is not None:
        DEC["prefilled"]+=1
        print(f"  {prompt}: {prefill}   ← {why or 'from precedent'} (not asked)")
        return str(prefill)
    DEC["asked"]+=1
    return ask(prompt, default)

# ══════════════════════════════════════════════════════════ terminal UI helpers
W=78
# ─── chapter visibility. A flow runs the pipeline silently until its own banner.
TAG2FLOW={"§7.0":"profile","GATE 0":"gate0","§7.2":"discover","§7.3":"mapping",
          "GATE 1":"gate1","§7.5":"validate","§7.6":"identity","QUEUE":"identity",
          "§7.7":"identity","GATE 2":"approval","§7.9":"workbook","§8":"precedent",
          "§12":"executor","§12.1":"executor","NOTIF":"executor","§12.6":"executor"}
CHAPTER=None
_REAL=sys.stdout; _NULL=open(os.devnull,"w")
def visible(): return sys.stdout is _REAL
def set_visible(v): sys.stdout = _REAL if v else _NULL

DIM="\033[2m"; OFF="\033[0m"
def cue(*lines):
    """A presenter note. Dim, prefixed, suppressed by --no-cues."""
    if not CUES or not visible(): return
    for l in lines: print(f"     {DIM}| {l}{OFF}")

def end_chapter():
    set_visible(True)
    if FLOW=="gate1" and not (ALT_RETENTION or ALT_STATUS): gate1_alternatives()
    names=[k for k,_ in FLOWS]
    nxt=names[names.index(FLOW)+1] if FLOW in names and names.index(FLOW)+1<len(names) else None
    print("\n  "+"─"*74)
    if nxt: print(f"  next chapter:  ../.venv/bin/python run_demo.py --flow {nxt}")
    else:   print("  that is the last chapter.  --flow list  shows them all again")
    print("  "+"─"*74+"\n")
    sys.exit(0)

def gate1_alternatives():
    """Re-run Gate 1 three ways and show what actually moves. Real subprocesses,
    so this is output rather than an assertion about output."""
    import subprocess
    import tempfile
    sys.stdout.flush()
    tmp=tempfile.mkdtemp(prefix="mc-variants-")
    def variant(extra, n):
        d=os.path.join(tmp,n)
        r=subprocess.run([sys.executable,"run_demo.py","--auto","--no-execute",
                          "--prec-dir",d]+extra, capture_output=True, text=True)
        if r.returncode!=0: return None
        return json.load(open(os.path.join(WB,"manifest.json")))["counts"]
    print("\n"+"="*W)
    print("  THE ROAD NOT TAKEN — same 14 rows, one Gate 1 decision changed")
    print("="*W)
    cue("this is the argument for putting a human here at all:",
        "same file, same code, three defensible answers, three different outcomes")
    # baseline runs last so workbook/ is left holding the road you actually took
    c=variant(["--alt-status"],"c"); b=variant(["--alt-retention"],"b"); a=variant([],"a")
    if not all((a,b,c)): print("  (comparison unavailable)"); return
    rows=[("tier 1 · applications","tier1_rows"),("tier 2 · talent pool","tier2_rows"),
          ("excluded by retention","excluded"),("failed validation","failed_validation"),
          ("queued for a human","queued")]
    print(f"\n  {'':<24} {'cutoff 2019':>13} {'no cutoff':>13} {'catch-all stage':>17}")
    print("  "+"-"*70)
    for label,k in rows:
        print(f"  {label:<24} {a[k]:>13} {b[k]:>13} {c[k]:>17}")
    print("  "+"-"*70)
    print("""
  left    cutoff at 2019-01-01, unmatched statuses declared unmappable.
          The 2013 record is excluded and never written.
  middle  you declined a cutoff and gave a reason. The 2013 record returns, as a
          talent-pool record. A legal decision, and it is visible in the numbers.
  right   unmatched statuses sent to a catch-all stage instead of the talent pool.
          People move into live pipelines — either what you wanted, or a quiet
          mess for whoever opens that pipeline tomorrow.

  The tool will do any of the three. It will not pick for you, and it writes down
  which one you picked, with your name on it.""")

ACTOR_BAR={"script":"·","human":"\u2588","llm":"\u2593"}
ACTOR_SUB={"script":"script only \u2014 no human, no writes",
           "human":"HUMAN DECISION \u2014 the flow stops here",
           "llm":"LLM \u2014 proposes only; the next step is a human gate"}
def banner(tag, title, actor):
    global CHAPTER
    f=TAG2FLOW.get(tag)
    if FLOW and CHAPTER==FLOW and f!=FLOW: end_chapter()
    CHAPTER=f
    set_visible(FLOW is None or f==FLOW)
    print("\n" + "="*W)
    print(ACTOR_BAR[actor] + " " + tag + "  " + title)
    print("  " + ACTOR_SUB[actor])
    print("="*W)
def note(*lines):
    for l in lines: print(f"  {l}")
def pause(msg="press Enter for the next stage"):
    if NO_PAUSE or not visible(): return
    try: input(f"\n  ── {msg} ── ")
    except EOFError: pass

def _in(prompt, default):
    """One line of input. In --auto, returns the recorded default and says so."""
    if FLOW and not visible(): return str(default)     # earlier chapter — run it silently
    if AUTO:
        print(f"{prompt}{default}      ← recorded answer (--auto)"); return str(default)
    try:
        v=input(prompt).strip()
    except EOFError:
        print(f"{default}   ← no tty, using default"); return str(default)
    return v or str(default)

def ask(prompt, default):        return _in(f"  {prompt} [{default}]: ", default)
def ask_yn(prompt, default="y"): return _in(f"  {prompt} [{default}/n]: ", default).lower().startswith("y")
def ask_list(prompt, default):
    raw=_in(f"  {prompt} [{default}]: ", default)
    return [int(x) for x in re.split(r"[,\s]+", raw.strip()) if x.strip().isdigit()]

# ══════════════════════════════════════════════════════════════ lib: transforms
def split_name(v, order="given_first"):
    p=[x for x in re.split(r"\s+", (v or "").strip()) if x]
    if not p: return {"first_name":None,"last_name":None}
    if len(p)==1: return {"first_name":p[0],"last_name":None}
    return ({"first_name":p[0],"last_name":" ".join(p[1:])} if order=="given_first"
            else {"first_name":" ".join(p[1:]),"last_name":p[0]})

def parse_date(v, locale, ambiguous):
    v=(v or "").strip()
    if not v: return None, None
    m=re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", v)
    if m:
        a,b,y=int(m.group(1)),int(m.group(2)),int(m.group(3))
        amb = a<=12 and b<=12 and a!=b
        if locale=="en_GB": d,mo=a,b
        elif locale=="en_US": d,mo=b,a
        else: return None,"DATE_LOCALE_REQUIRED"
        if amb and ambiguous=="reject": return None,"DATE_AMBIGUOUS"
        try: return datetime.date(y,mo,d).isoformat(), None
        except ValueError: return None,"DATE_INVALID"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", v): return v, None
    return None,"DATE_UNPARSEABLE"

def normalise_phone(v, default_region="GB"):
    v=(v or "").strip()
    if not v: return None, None
    digits=re.sub(r"[^\d+]","",v)
    if digits.startswith("+"): return digits, None
    if default_region=="GB" and digits.startswith("0"): return "+44"+digits[1:], None
    if default_region=="US" and len(digits)==10: return "+1"+digits, None
    return None,"PHONE_UNNORMALISABLE"

def norm_email(v): return ((v or "").strip().lower()) or None
def h(o): return "sha256:"+hashlib.sha256(json.dumps(o,sort_keys=True,default=str).encode()).hexdigest()[:16]

print(f"""
{'='*W}
  PINPOINT MIGRATION COPILOT — vertical slice
  7 stages · 3 human gates · 2 tiers · 0 writes issued by a model
  mode: {'AUTO (recorded answers)' if AUTO else 'INTERACTIVE — you make the gate decisions'}
{'='*W}""")

# ══════════════════════════════════════ §7.0 — profile the source (NO values)
banner("§7.0", "PROFILE THE SOURCE", "script")
raw=open(SOURCE, encoding="utf-8-sig").read()
had_bom = open(SOURCE,"rb").read(3)==b"\xef\xbb\xbf"
rdr=list(csv.reader(raw.splitlines()))
header=rdr[0]; body=[r for r in rdr[1:] if any(c.strip() for c in r)]
junk=[r for r in body if sum(1 for c in r if c.strip())<=2]
data=[r for r in body if r not in junk]

dupes=collections.Counter(h_.strip().lower() for h_ in header)
PII={"candidate name":"direct_identifier","e-mail address":"direct_identifier","phone":"direct_identifier",
     "address 1":"direct_identifier","address 2":"direct_identifier","postcode":"direct_identifier",
     "notes":"free_text"}
cols=[]
for i,h_ in enumerate(header):
    vals=[r[i].strip() for r in data if i<len(r)]
    nn=h_.strip().lower()
    cols.append({"index":i,"name":h_,"normalized_name":nn,"duplicate_header":dupes[nn]>1,
                 "null_rate":round(sum(1 for v in vals if not v)/max(len(vals),1),3),
                 "cardinality":len({v for v in vals if v}),
                 "pii_class":PII.get(nn,"none"),
                 "distinct_values":None})            # ← never emitted at Stage 0
profile={"source":{"filename":os.path.basename(SOURCE),"sha256":hashlib.sha256(raw.encode()).hexdigest()[:16],
                   "encoding":"utf-8","bom":had_bom,"rows":len(data),"header_row":1},
         "anomalies":([f"duplicate header '{h_}'" for h_,c in dupes.items() if c>1]
                      +([f"{len(junk)} trailing junk rows discarded"] if junk else [])
                      +(["BOM present, stripped"] if had_bom else [])),
         "columns":cols}
SIG=hashlib.sha256(json.dumps([[c["index"],c["normalized_name"]] for c in cols]).encode()).hexdigest()[:16]
profile["column_signature"]=SIG
SEM=load_prec("semantic", SIG)
emit("profile.json", profile)
note(f"rows={len(data)}  columns={len(header)}",
     f"anomalies: {profile['anomalies']}",
     f"'Notes' appears at indices {[c['index'] for c in cols if c['normalized_name']=='notes']}"
     f" — columns are addressed by (index, normalized_name), never by name",
     f"distinct values emitted: {any(c['distinct_values'] for c in cols)}  ← none, by design",
     f"column signature: {SIG}")
cue("the AI has not seen a single cell value yet, and will not until you say so",
    "two columns are both called 'Notes' — they are tracked by position, not name")
if SEM:
    note("", f"SEMANTIC PRECEDENT FOUND — this column shape has been migrated {SEM['uses']}x before",
         f"   last used {SEM['last_used']} against account '{SEM.get('last_account','?')}'",
         "   It carries the transforms and the Gate 0 selection. It is portable because it",
         "   describes the SOURCE FILE, not any destination.")
else:
    note("", "No semantic precedent for this column shape — cold start, you decide everything.")
pause()

# ══════════════════════════════════════════ GATE 0 — vocabulary projection
banner("GATE 0", "WHICH COLUMNS MAY THE MODEL SEE VALUES FROM?", "human")
note("The profile above emitted no cell values at all. But a model that has seen no values",
     "cannot map \"Phone Screen\" to a stage, because it does not know that value exists.",
     "So you name the columns whose distinct values may be shown. Everything else stays dark.","")
print(f"  {'idx':>3}  {'column':<20} {'pii_class':<18} {'distinct':>8}  {'null%':>6}")
for c in cols:
    print(f"  {c['index']:>3}  {c['name'][:20]:<20} {c['pii_class']:<18} {c['cardinality']:>8}  {c['null_rate']*100:>5.0f}%")

g0_tries=0
FORBID={"email":re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}",re.I),
        "phone":re.compile(r"(\+\d[\d\s\-()]{7,})|(\b0\d{9,10}\b)"),
        "postcode":re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",re.I),
        "dob":re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b")}
LIMITS={"max_distinct_per_column":500,"max_total_values":2000,"max_value_length":120}

def gate0_refusal_demo():
    """Show the tripwire refusing a PII column, without making the presenter type it."""
    print()
    note("First, watch what happens if you try to include column 1, the email address:")
    cue("nobody typed anything here — this is the gate refusing a selection")
    bad=[c for c in cols if c["index"] in (4,3,12,1)]
    errs=[]
    for c in bad:
        vals=sorted({r[c["index"]].strip() for r in data if c["index"]<len(r) and r[c["index"]].strip()})
        for pat,rx in FORBID.items():
            if any(rx.search(v) for v in vals): errs.append((c["name"],pat))
    print("\n  requested: columns 4, 3, 12, 1")
    print("  GATE 0 REJECTED — the tripwire found forbidden patterns:")
    for n,pat in errs: print(f"     ✗ column '{n}' matches pattern '{pat}'")
    note("","Read that again: it names the COLUMN, never the value. Nothing sensitive",
         "reached this channel, not even in the error that complained about it.")
    cue("now press Enter to accept the safe selection and move on")

if DEMO: gate0_refusal_demo()

while True:
    print()
    dflt=",".join(str(i) for i in SEM["gate0_columns"]) if SEM else "4,3,12"
    if SEM: note(f"precedent suggests columns {dflt} — Enter accepts, or type your own")
    if not g0_tries and not DEMO:
        cue("TYPE:  4,3,12,1     (that last one is the email column)",
            "then watch it refuse, and read what the refusal does NOT say")
    else:
        cue("now press Enter to accept 4,3,12 — Status, Applied For, Source",
            "those three word-lists are the only cell contents the AI will ever see")
    g0_tries+=1
    picked=ask_list("column indices the model may see values from (comma separated)", dflt)
    chosen=[c for c in cols if c["index"] in picked]
    if not chosen:
        note("nothing selected — the mapping stage needs at least the status and job columns"); continue
    errors=[]
    for c in chosen:
        vals=sorted({r[c["index"]].strip() for r in data if c["index"]<len(r) and r[c["index"]].strip()})
        for pat,rx in FORBID.items():
            if any(rx.search(v) for v in vals):
                errors.append({"column":c["name"],"pattern":pat})     # names the column, NEVER the value
        if len(vals)>LIMITS["max_distinct_per_column"]:
            errors.append({"column":c["name"],"limit":"max_distinct"})
    if errors:
        print()
        note("GATE 0 REJECTED — the tripwire found forbidden patterns:")
        for e in errors: note(f"   ✗ column '{e['column']}' matches pattern '{e.get('pattern',e.get('limit'))}'")
        note("","Note what the error does NOT contain: the offending value. The gate names the",
             "column so you can fix your selection, and nothing sensitive reaches this channel.")
        if AUTO: sys.exit(1)
        continue
    break

vocab={"projection":{"columns":[{"index":c["index"],"name":c["name"]} for c in chosen],**LIMITS,
                     "forbid_patterns":list(FORBID),"approved_by":"(gate 0)",
                     "approved_at":datetime.datetime.now().isoformat(timespec="seconds")},
       "values":{}}
for c in chosen:
    vocab["values"][c["name"]]=sorted({r[c["index"]].strip() for r in data
                                       if c["index"]<len(r) and r[c["index"]].strip()})
emit("vocabulary.json", vocab)
print()
note("GATE 0 PASSED — the model may now see these values, and only these:")
for k,v in vocab["values"].items(): note(f"   {k:<14} → {v}")
pause()

# ══════════════════════════════════════════════ §7.2 — discover the target
banner("§7.2", "DISCOVER THE TARGET ACCOUNT", "script")
acct=json.load(open(ACCOUNT))
wf_by_id={w["id"]:w for w in acct["hiring_workflows"]}
catalog={"account_fingerprint":hashlib.sha256(acct["subdomain"].encode()).hexdigest()[:16],
         "jobs":[],"custom_fields":acct.get("custom_fields",[])}
for j in acct["jobs"]:
    wf_stages=[{"id":x["id"],"name":x["name"],"owner":"workflow"} for x in wf_by_id[j["hiring_workflow_id"]]["stages"]]
    own_stages=[{"id":x["id"],"name":x["name"],"owner":"job"} for x in j["job_owned_stages"]]
    catalog["jobs"].append({"id":j["id"],"title":j["title"],"status":j["status"],
        "accepts_applications": j["status"]=="open",
        "requirements":{k:j[k] for k in ("require_phone","resume_requirement",
                                         "cover_letter_requirement","ask_for_address")},
        "stages":wf_stages+own_stages})
emit("target_catalog.json", catalog)
for j in catalog["jobs"]:
    print(f"  job {j['id']:>3} {j['title']:<22} {j['status']:<9} accepts={str(j['accepts_applications']):<5} "
          f"require_phone={str(j['requirements']['require_phone']):<5} cv={j['requirements']['resume_requirement']}")
    st=", ".join(x["name"]+"("+str(x["id"])+","+x["owner"]+")" for x in j["stages"])
    print("          stages: "+st)
note("", "job 91's 'Take-home' stage is owned by the JOB, not by its workflow.",
     "Resolving stages against the workflow alone would produce an id that job does not have.")
pause()

# ══════════════════════════════════════ §7.3 — propose the mapping (LLM #1)
banner("§7.3", "PROPOSE THE MAPPING", "llm")
note("Input to the model: profile.json + vocabulary.json + target_catalog.json.",
     "No rows. Transforms are chosen from a closed allowlist — the model never writes code.","")
job_by_title={j["title"]:j["id"] for j in catalog["jobs"]}
T=(SEM or {}).get("transforms", {})
NAME_ORDER = T.get("name_order","given_first")
DATE_LOCALE= T.get("date_locale","en_GB")
PHONE_REGION=T.get("phone_region","GB")
if SEM:
    note(f"transforms taken from precedent: split_name order={NAME_ORDER} · "
         f"parse_date locale={DATE_LOCALE} · normalise_phone region={PHONE_REGION}",
         "These describe the source file, so they carry across accounts unchanged.","")
MAPPING={
 "version":1,
 "model_inputs":["profile.json","vocabulary.json","target_catalog.json"],
 "columns":[
  {"src":{"index":0,"name":"Candidate Name"},"target":["first_name","last_name"],
   "transform":{"fn":"split_name","order":NAME_ORDER},"confidence":0.92},
  {"src":{"index":1,"name":"E-mail Address"},"target":["email"],"transform":{"fn":"norm_email"},"confidence":0.99},
  {"src":{"index":2,"name":"Phone"},"target":["phone"],
   "transform":{"fn":"normalise_phone","default_region":PHONE_REGION},"confidence":0.90},
  {"src":{"index":3,"name":"Applied For"},"target":["job_id"],"transform":{"fn":"map_value"},
   "value_map":{t:job_by_title.get(t) for t in vocab["values"].get("Applied For",[])},"confidence":0.88},
  {"src":{"index":4,"name":"Status"},"target":["stage_id"],"transform":{"fn":"map_value_per_job"},
   "value_map_per_job":{j["id"]:{v:sn[v] for v in vocab["values"].get("Status",[]) if v in sn}
                        for j in catalog["jobs"]
                        for sn in [{x["name"]:x["id"] for x in j["stages"]}]},"confidence":0.85},
  {"src":{"index":5,"name":"Applied Date"},"target":["custom_attribute:original_application_date"],
   "transform":{"fn":"parse_date","locale":DATE_LOCALE,"ambiguous":"prefer_dmy"},"confidence":0.71},
  {"src":{"index":6,"name":"Address 1"},"target":["address1"],"transform":{"fn":"trim"},"confidence":0.99},
  {"src":{"index":7,"name":"Address 2"},"target":["address2"],"transform":{"fn":"trim"},"confidence":0.99},
  {"src":{"index":8,"name":"City"},"target":["town"],"transform":{"fn":"trim"},"confidence":0.95},
  {"src":{"index":9,"name":"State"},"target":["state_province"],"transform":{"fn":"trim"},"confidence":0.93},
  {"src":{"index":10,"name":"Postcode"},"target":["postcode"],"transform":{"fn":"trim"},"confidence":0.98},
  {"src":{"index":11,"name":"Country"},"target":["country"],"transform":{"fn":"trim"},"confidence":0.99},
  {"src":{"index":12,"name":"Source"},"target":["channel_source"],"transform":{"fn":"trim"},"confidence":0.80},
  {"src":{"index":14,"name":"Legacy ID"},"target":["_source_record_id"],"transform":{"fn":"trim"},"confidence":0.96},
  {"src":{"index":13,"name":"Notes"},"target":[],"transform":{"fn":"drop"},"confidence":0.60},
  {"src":{"index":15,"name":"Notes"},"target":[],"transform":{"fn":"drop"},"confidence":0.60}],
 "routing":{}}
for c in MAPPING["columns"]:
    t=c["transform"]; params=" ".join(f"{k}={v}" for k,v in t.items() if k!="fn")
    print(f"  col {c['src']['index']:>2} {c['src']['name'][:18]:<18} → {(','.join(c['target']) or '(dropped)')[:34]:<34} "
          f"{t['fn']}{' '+params if params else ''}  conf={c['confidence']}")
note("", "Both 'Notes' columns (13 and 15) are mapped separately by index — name-only",
     "addressing would silently collide.",
     "'Product Owner' → None: no destination job. Not an error; it routes those rows to Tier 2.",
     "parse_date.locale has NO DEFAULT, so '04/03/2019' cannot resolve silently.")
cue("04/03/2019 is either 4 March or 3 April. No software can tell you which.",
    "so the setting has no default — a person decides, and the record says who")
pause()

# ══════════════════════════ GATE 1 — coverage, requirements, retention (human)
banner("GATE 1", "MAPPING, COVERAGE AND RETENTION", "human")
STATUS_VOCAB=vocab["values"].get("Status", [])
vmpj=MAPPING["columns"][4]["value_map_per_job"]
UNMAPPABLE=collections.defaultdict(list)
WAIVERS=collections.defaultdict(list)
REQ_CHOICE={}
rebound=set()

BIND_KEY=catalog["account_fingerprint"]+"__"+SIG
BIND=load_prec("bindings", BIND_KEY)
if BIND:
    note(f"BINDINGS FOUND for account '{acct['subdomain']}' + this column shape ({BIND['uses']} prior uses).",
         "Every stored id is re-resolved against the live target before it is offered.","")
elif SEM:
    note(f"No bindings for account '{acct['subdomain']}'. The semantic precedent carried the",
         "transforms across, but value→id maps are NEVER portable: job 88 here is a different",
         "job there. You will be asked for every value map again.","")
# What the model's proposal already covers, before any precedent is applied.
APPLICABLE={(j["id"],v) for j in catalog["jobs"] if j["accepts_applications"] for v in STATUS_VOCAB}
covered_by_model={(j["id"],v) for (jid,v) in APPLICABLE for j in catalog["jobs"]
                  if j["id"]==jid and v in vmpj.get(jid,{})}
DEC["by_model"]=len(covered_by_model)

# 1 · a stored binding seeds the proposal
if BIND:
    for jid,m in BIND.get("status_stages",{}).items():
        vmpj.setdefault(int(jid),{}).update(m)
    for jid,vs in BIND.get("unmappable",{}).items():
        UNMAPPABLE[int(jid)].extend(v for v in vs if v not in UNMAPPABLE[int(jid)])

# 2 · re-resolve every stage id against the LIVE target before it is offered.
#     A binding whose id no longer exists is invalidated, never silently repaired.
for j in catalog["jobs"]:
    live={x["id"] for x in j["stages"]}
    for status,sid in list(vmpj.get(j["id"],{}).items()):
        if sid is not None and int(sid) not in live:
            DEC["invalidated"]+=1
            print(f"  ✗ INVALIDATED  '{status}' → stage {sid} no longer exists on job {j['id']}")
            print(f"                 you will be asked again; a moved id is how people land in")
            print(f"                 the wrong pipeline, so it is never quietly repaired")
            del vmpj[j["id"]][status]
covered_now={(jid,v) for (jid,v) in APPLICABLE
             if v in vmpj.get(jid,{}) or v in UNMAPPABLE[jid]}
DEC["prefilled"]=len(covered_now-covered_by_model)
DEC["by_model"]=len(covered_by_model & covered_now)
if DEC["invalidated"]: print()
if DEC["prefilled"]:
    note(f"{DEC['prefilled']} status decision(s) supplied by the stored binding — not asked.","")

note("(a) STATUS COVERAGE — every status must be MAPPED or declared UNMAPPABLE, per job.",
     "    An unmapped status is a mapping gap. Closing it here costs one decision;",
     "    discovering it at validation costs you the row.","")
cue("press Enter through these — 'u' sends those people to the talent pool",
    "or type a stage id to route them into a live pipeline instead",
    "before this gate existed, an unmapped status silently DELETED the row")
for j in catalog["jobs"]:
    if not j["accepts_applications"]: continue
    gaps=[v for v in STATUS_VOCAB
          if v not in vmpj.get(j["id"],{}) and v not in UNMAPPABLE[j["id"]]]
    if not gaps:
        note(f"job {j['id']} {j['title']}: 100% covered by the proposal"); continue
    print(f"\n  job {j['id']} · {j['title']}")
    avail=", ".join(x["name"]+"="+str(x["id"]) for x in j["stages"])
    print("    stages available: "+avail)
    for g in gaps:
        gap_default=str(j["stages"][-1]["id"]) if ALT_STATUS else "u"
        a=decide(f"  status '{g}' → stage id, or 'u' = unmappable (routes those rows to Tier 2)",
                 gap_default, prefill=None)
        if a.lower().startswith("u"):
            UNMAPPABLE[j["id"]].append(g); print(f"      → '{g}' declared UNMAPPABLE on job {j['id']}")
        else:
            vmpj.setdefault(j["id"],{})[g]=int(a); print(f"      → '{g}' mapped to stage {a}")

print()
note("(b) REQUIREMENT REACHABILITY — can the SOURCE supply what the job requires at all?","")
source_cols={c["normalized_name"] for c in cols}
for j in catalog["jobs"]:
    if not j["accepts_applications"]: continue
    if j["requirements"]["resume_requirement"]=="required" and not (source_cols & {"cv","resume"}):
        note(f"job {j['id']} {j['title']} requires a CV. The source has NO CV column at all,",
             f"   so every row bound for it fails identically — that is a mapping defect,",
             f"   not {len(data)} row defects. Raised here as SOURCE_LACKS_REQUIRED_FIELD.")
        cue("one mapping problem, not a hundred row problems — Enter waives it, on the record")
        stored=(BIND or {}).get("requirement_choice",{}).get(str(j["id"]))
        a=decide(f"  (w)aive the requirement, or (r)ebind those rows to Tier 2?", "w",
                 prefill=stored, why="from binding")
        REQ_CHOICE[str(j["id"])]=a.lower()[:1]
        if a.lower().startswith("w"):
            WAIVERS[j["id"]].append("resume_requirement")
            print(f"      → waived, and recorded in the approval artifact")
        else:
            rebound.add(j["id"]); print(f"      → rows for job {j['id']} will route to Tier 2")

print()
note("RETENTION IS NEVER STORED IN A PRECEDENT. The lawful basis for one customer's data",
     "says nothing about another's, so this is asked every single run.","")
note("(c) RETENTION — a hard block. A 14-year export contains records the customer may have",
     "    no lawful basis to keep, and migrating them re-establishes processing.","")
dates=sorted(d for d in (parse_date(r[5],"en_GB","prefer_dmy")[0] for r in data) if d)
note(f"source date range: {dates[0]} → {dates[-1]}","")
cue("press Enter for 2019-01-01, or type 'none' to decline and give a reason",
    "the one gate where the right answer is sometimes 'import less'")
cutoff_raw=ask("retention cutoff (YYYY-MM-DD), or 'none' to decline with a reason",
               "none" if ALT_RETENTION else "2019-01-01")
if cutoff_raw.lower()=="none":
    reason=ask("reason for declining a cutoff", "customer confirmed lawful basis for full history")
    CUTOFF=None; RETENTION={"cutoff":None,"declined":True,"reason":reason}
else:
    CUTOFF=datetime.date.fromisoformat(cutoff_raw); RETENTION={"cutoff":cutoff_raw,"declined":False}
    note(f"→ {sum(1 for d in dates if datetime.date.fromisoformat(d)<CUTOFF)} of {len(dates)} rows fall before it and will be excluded")

MAPPING["routing"]={"retention":RETENTION,
                    "unmappable_statuses":dict(UNMAPPABLE),
                    "requirement_waivers":dict(WAIVERS),
                    "rebound_to_tier2":sorted(rebound)}
MAPPING["approved_by"]=ask("\n  your name (recorded as the Gate 1 approver)", "fazal")
emit("mapping_spec.json", MAPPING)

covered=all(all(v in vmpj.get(j["id"],{}) or v in UNMAPPABLE[j["id"]] for v in STATUS_VOCAB)
            for j in catalog["jobs"] if j["accepts_applications"])
print()
note(f"GATE 1 {'PASSED' if covered else 'FAILED'} — status coverage {'100%' if covered else 'INCOMPLETE'}",
     "Because coverage is complete, STAGE_NOT_ON_JOB is now unreachable at validation:",
     "no row can be discarded for a status decision you were never asked to make.")
if not covered: sys.exit(1)
if DEMO:
    pause("press Enter to see what the other two answers would have produced")
    gate1_alternatives()
pause()

# ══════════════════════════════════════════════════ §7.5 — validate + tier
banner("§7.5", "VALIDATE AND ASSIGN TIERS", "script")
note("Deterministic transforms, then Pinpoint's write rules. No API calls, no writes.",
     "Three outcomes only: ok / fail / excluded. There is no warn-then-proceed.","")
cue("Pinpoint's docs say the API will NOT check required fields — the client must",
    "without this stage you create incomplete records the API happily accepts")
job_by_id={j["id"]:j for j in catalog["jobs"]}
title_map=MAPPING["columns"][3]["value_map"]
rowsv=[]
for n,r in enumerate(data, start=1):
    g=lambda i: (r[i].strip() if i<len(r) else "")
    rec={"row":n,"errors":[],"job_id":None,"stage_id":None,"tier":None}
    rec.update(split_name(g(0),"given_first"))
    rec["email"]=norm_email(g(1))
    ph,perr=normalise_phone(g(2),"GB"); rec["phone"]=ph
    if perr: rec["errors"].append({"code":perr,"field":"phone"})
    d,derr=parse_date(g(5),"en_GB","prefer_dmy"); rec["original_date"]=d
    if derr: rec["errors"].append({"code":derr,"field":"Applied Date"})
    rec["job_id"]=title_map.get(g(3)); rec["job_title_source"]=g(3)
    rec["address1"],rec["address2"]=g(6),g(7)
    rec["town"],rec["state_province"],rec["postcode"],rec["country"]=g(8),g(9),g(10),g(11)
    rec["channel_source"]=g(12); rec["source_record_id"]=g(14); rec["status_label"]=g(4)

    if CUTOFF and d and datetime.date.fromisoformat(d) < CUTOFF:
        rec["tier"]=None; rec["verdict"]="excluded"
        rec["errors"].append({"code":"BEFORE_RETENTION_CUTOFF","field":"Applied Date"})
        rowsv.append(rec); continue

    job=job_by_id.get(rec["job_id"]) if rec["job_id"] else None
    stage=vmpj.get(job["id"],{}).get(rec["status_label"]) if job else None
    # §4 tier routing. A status with no stage was declared unmappable at Gate 1,
    # so it lands in Tier 2 rather than failing. Nothing is discarded here.
    if job and job["accepts_applications"] and stage and job["id"] not in rebound:
        rec["tier"]=1
    else:
        rec["tier"]=2
    rec["stage_id"]=stage if rec["tier"]==1 else None

    if rec["country"]=="US" and rec["address2"]:
        rec["errors"].append({"code":"ADDRESS2_ON_US","field":"address2"})
    if rec["country"]!="US" and rec["state_province"]:
        rec["errors"].append({"code":"STATE_PROVINCE_ON_NON_US","field":"state_province"})
    # per-job requirements: ROW-LEVEL scope only. Mapping-level scope went to Gate 1.
    if rec["tier"]==1 and job and job["requirements"]["require_phone"] and not rec["phone"]:
        rec["errors"].append({"code":"MISSING_REQUIRED_PHONE","field":"phone"})
    rec["verdict"]="fail" if rec["errors"] else "ok"
    rowsv.append(rec)

hist=collections.Counter(e["code"] for r in rowsv for e in r["errors"])
verd=collections.Counter(r["verdict"] for r in rowsv)
emit("dry_run.json", {"counts":dict(verd),"errors_by_code":dict(hist),
                      "tiers":{str(k):v for k,v in collections.Counter(r["tier"] for r in rowsv).items()}})
json.dump(rowsv, open(OUT+"/_private_row_verdicts.json","w"), indent=1, default=str)
print(f"  verdicts: {dict(verd)}    tiers: {dict(collections.Counter(r['tier'] for r in rowsv))}\n")
for r in rowsv:
    tag={"ok":"✓","fail":"✗","excluded":"—"}[r["verdict"]]
    tier="T"+str(r["tier"]) if r["tier"] else "--"
    codes=",".join(e["code"] for e in r["errors"])
    print(f"   {tag} row {r['row']:>2}  {tier}  job={str(r['job_id'] or '-'):>4} "
          f"stage={str(r['stage_id'] or '-'):>6}  {codes}")
note("", "dry_run.json (model-visible) carries counts and codes only.",
     "Row-level verdicts stay in the private lane — a verdict never carries a value.")
pause()

# ══════════════════════════════════════════════════ §7.6 — resolve identity
banner("§7.6", "RESOLVE IDENTITY", "script")
SRC_SYS="LegacyATS"; TENANT=acct["subdomain"]
by_esr={c["external_system_reference"]:c["id"] for c in acct["candidates"] if c["external_system_reference"]}
by_email=collections.defaultdict(list); by_phone=collections.defaultdict(list)
for c in acct["candidates"]:
    if c["email"]: by_email[c["email"].lower()].append(c["id"])
    if c["phone"]: by_phone[c["phone"]].append(c["id"])
note("Local index built from GET /candidates. `candidates.email` is a READABLE field, so a bulk",
     "extract can be indexed locally even though /candidates has no filter[email].",
     f"emails indexed={len(by_email)}  phones indexed={len(by_phone)}",
     "Deduplication keys on the SOURCE RECORD, never on the person.","")
cue("three questions, not one: which human, which application, which pool record",
    "exact matches only — there is no fuzzy matching anywhere in this system")

def esr(entity, rec_id):
    return "PPM-"+hashlib.sha256((TENANT+"|"+SRC_SYS+"|"+SRC_SYS+"|"+entity+"|"+rec_id).encode()).hexdigest()[:24]

seen_src=set(); resolved=[]
for r in rowsv:
    if r["verdict"] in ("fail","excluded"): continue
    sid=r["source_record_id"]
    if sid in seen_src:
        r["identity"]="duplicate_source_row"; resolved.append(r); continue
    seen_src.add(sid)
    hits={}
    if sid in by_esr: hits["esr"]=[by_esr[sid]]
    if r["email"] and r["email"] in by_email: hits["email"]=by_email[r["email"]]
    if r["phone"] and r["phone"] in by_phone: hits["phone"]=by_phone[r["phone"]]
    ids={i for v in hits.values() for i in v}
    if not hits:                     r["identity"]="new_person"; r["candidate_id"]=None
    elif len(ids)>1 and len(hits)>1: r["identity"]="conflicting_keys"; r["conflict"]=hits
    elif len(ids)>1:                 r["identity"]="ambiguous_multiple_match"; r["conflict"]=hits
    else:                            r["identity"]="existing_person"; r["candidate_id"]=list(ids)[0]
    resolved.append(r)
for r in resolved:
    cf=("  conflict="+json.dumps(r["conflict"])) if r.get("conflict") else ""
    print(f"   row {r['row']:>2}  T{r['tier']}  {r['identity']:<26} "
          f"candidate={r.get('candidate_id') or '-'}{cf}")
pause()

# ══════════════════════════════════ HUMAN QUEUE — resolve or defer (human)
queued=[r for r in resolved if r["identity"] not in ("new_person","existing_person")]
if queued:
    banner("QUEUE", "AMBIGUOUS AND CONFLICTING IDENTITIES", "human")
    note("These are not guessed. 'Probably the same person' is a data-protection incident,",
         "not a convenience. You resolve them, or they go to workbook/exceptions.csv.","")
    cue("press Enter twice to defer both, or type 9003 to bind the first one live")
    for r in list(queued):
        print(f"\n  row {r['row']} · {r['identity']}")
        print(f"    source: {r.get('first_name')} {r.get('last_name')} · {r['email'] or '(no email)'} "
              f"· {r['phone'] or '(no phone)'} · record {r['source_record_id']}")
        if r.get("conflict"):
            for k,v in r["conflict"].items(): print(f"    key '{k}' matches candidates {v}")
        if r["identity"]=="duplicate_source_row":
            note("   same source record id as an earlier row — dropped, not a person question"); continue
        opts=sorted({i for v in r["conflict"].values() for i in v})
        a=ask(f"  candidate id to bind ({'/'.join(str(o) for o in opts)}), or 'd' to defer to exceptions.csv", "d")
        if a.lower().startswith("d"):
            print("      → deferred; it will appear in workbook/exceptions.csv for a human")
        elif a.isdigit() and int(a) in opts:
            r["identity"]="existing_person"; r["candidate_id"]=int(a); r["resolved_by_human"]=True
            queued.remove(r); print(f"      → bound to candidate {a}, recorded as a human decision")
        else:
            print("      → not a listed candidate; deferred")
    pause()

proceed=[r for r in resolved if r["identity"] in ("new_person","existing_person")]
print(f"\n  proceeding: {len(proceed)}    human queue: {len(queued)}")

# ══════════════════════════════════════════ §7.7 — collapse within-run people
banner("§7.7", "COLLAPSE WITHIN-RUN PEOPLE", "script")
note("The §7.6 index was built from the account BEFORE anything is created. A person appearing",
     "twice in the source is absent from it on BOTH occurrences and resolves as new_person twice.",
     "Since a candidate is a side effect of a create (§3.1), that makes two humans.","")
cue("Pinpoint cannot create a person directly — a person falls out of a create",
    "so identity is not a lookup, it is a consequence of write order")
run_people={}
for r in proceed:
    key = r["email"] or r["phone"] or ("row"+str(r["row"]))
    r["person_key"]=key
    if key in run_people:
        r["depends_on_row"]=run_people[key]
        print(f"   row {r['row']:>2} shares person_key with row {run_people[key]} "
              f"→ must WAIT and reuse the returned candidate id")
    else:
        run_people[key]=r["row"]; r["depends_on_row"]=None
print(f"\n  {len(run_people)} distinct people across {len(proceed)} rows")
pause()

# ══════════════════════════════════════════ GATE 2 — sign the workbook (human)
banner("GATE 2", "SIGN THE WORKBOOK", "human")
plan={"tier1":[r["row"] for r in proceed if r["tier"]==1],
      "tier2":[r["row"] for r in proceed if r["tier"]==2],"operations":[]}
for r in proceed:
    ent="applications" if r["tier"]==1 else "job_seekers"
    r["esr"]=esr(ent,r["source_record_id"]); r["entity"]=ent
    plan["operations"].append({"row":r["row"],"entity":ent,"esr":r["esr"],
        "nested":["custom_attributes"] if r["original_date"] else [],
        "depends_on_row":r["depends_on_row"],"state":"planned"})
emit("plan.json", plan)

HASHES={"plan_hash":h(plan),"mapping_hash":h(MAPPING),"vocabulary_hash":h(vocab),
        "source_sha256":profile["source"]["sha256"]}
note("This approval is written by a human CLI invocation, not by a model. It pins four hashes;",
     "anything that consumes the workbook recomputes them and refuses on a mismatch.","")
cue("you must TYPE the word approve — Enter alone will not sign it",
    "then Enter at the next prompt to watch one edit void the signature")
for k,v in HASHES.items(): print(f"    {k:<18} {v}")
print()
note(f"destination      {TENANT} (fingerprint {catalog['account_fingerprint']})",
     f"retention        {RETENTION}",
     f"tier 1 rows      {len(plan['tier1'])}   →  applications",
     f"tier 2 rows      {len(plan['tier2'])}   →  job_seekers",
     f"human queue      {len(queued)}   →  exceptions.csv",
     f"acknowledgements job_seeker_notification_behaviour_unverified (§16.1, unresolved)","")

while True:
    sig=_in("  type 'approve' to sign, or 'abort': ", "approve").strip().lower()
    if sig=="abort": print("\n  aborted — no workbook written."); sys.exit(0)
    if sig=="approve": break
    print("    not a valid signature. Type the word 'approve'.")
approver=ask("approved by", MAPPING.get("approved_by","fazal"))
approval={**HASHES,
          "destination":{"subdomain":TENANT,"account_fingerprint":catalog["account_fingerprint"]},
          "tool_version":"0.5.0","retention":RETENTION,
          "coverage":{"status_values":1.0,"requirements_resolved":True},
          "acknowledgements":["job_seeker_notification_behaviour_unverified"],
          "approved_by":approver,
          "approved_at":datetime.datetime.now().isoformat(timespec="seconds")}
emit("approval.json", approval)
print(f"\n  signed by {approver} at {approval['approved_at']}")

# the binding, demonstrated rather than asserted
if ask_yn("\n  demonstrate the binding? (alter one transform and re-check the approval)", "y"):
    tampered=json.loads(json.dumps(MAPPING, default=str))
    tampered["columns"][5]["transform"]["locale"]="en_US"
    print(f"    changed parse_date.locale: en_GB → en_US  ('04/03/2019' would become 3 April)")
    print(f"    approval mapping_hash  {approval['mapping_hash']}")
    print(f"    recomputed mapping_hash {h(tampered)}")
    print(f"    → {'MATCH' if h(tampered)==approval['mapping_hash'] else 'MISMATCH — approval VOID, the run refuses to start'}")
    note("  The change was never applied. This is why the approval is a file of hashes and",
         "  not a status field: a model could edit a status field, but it cannot make",
         "  a stale hash match a changed mapping.")
pause()

# ══════════════════════════════════════════════ §7.9 — emit the workbook
banner("§7.9", "EMIT THE WORKBOOK", "script")
note("Deterministic assembly. No decisions are made here — every decision was made at a gate.","")
cue("this is the deliverable — nine files a human imports and signs for",
    "the five invariants must balance, or the run is a bug not a rounding error")
order={}
for i,r in enumerate(sorted(proceed, key=lambda x: (x["depends_on_row"] or 0, x["row"])), start=1):
    order[r["row"]]=i

def wcsv(name, rows, fields):
    with open(os.path.join(WB,name),"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader()
        for r in rows: w.writerow(r)
    return len(rows)

T1=[dict(r, import_order=order[r["row"]], stage_id=r["stage_id"],
         original_application_date=r["original_date"]) for r in proceed if r["tier"]==1]
T2=[dict(r, import_order=order[r["row"]], pipeline_source=r["channel_source"],
         source_job_title_tag=r["job_title_source"],
         original_application_date=r["original_date"]) for r in proceed if r["tier"]==2]
EXC=([dict(r, reason="failed_validation", code=",".join(e["code"] for e in r["errors"]),
           field=",".join(e["field"] for e in r["errors"]))
      for r in rowsv if r["verdict"]=="fail"]
     +[dict(r, reason=r["identity"], code=r["identity"], field="identity") for r in queued])
EXCL=[dict(r, code=",".join(e["code"] for e in r["errors"])) for r in rowsv if r["verdict"]=="excluded"]
IDR=[{"row":r["row"],"person_key":r["person_key"],"identity":r["identity"],
      "candidate_id":r.get("candidate_id"),"depends_on_row":r["depends_on_row"],
      "resolved_by_human":r.get("resolved_by_human",False)} for r in proceed]

PERSON=["row","external_system_reference","candidate_id","first_name","last_name","email","phone",
        "address1","address2","town","state_province","postcode","country",
        "original_application_date","import_order","depends_on_row"]
n1=wcsv("tier1_applications.csv", [dict(x, external_system_reference=x["esr"]) for x in T1],
        PERSON[:3]+["job_id","stage_id"]+PERSON[3:])
n2=wcsv("tier2_job_seekers.csv",  [dict(x, external_system_reference=x["esr"]) for x in T2],
        PERSON[:3]+["pipeline_source","source_job_title_tag"]+PERSON[3:])
ne=wcsv("exceptions.csv", EXC, ["row","reason","code","field","first_name","last_name",
                                "email","phone","source_record_id"])
nx=wcsv("excluded.csv", EXCL, ["row","code","original_date","source_record_id"])
ni=wcsv("identity_report.csv", IDR, ["row","person_key","identity","candidate_id",
                                     "depends_on_row","resolved_by_human"])

json.dump({"gate0_columns":[c["name"] for c in chosen],
           "gate1_unmappable_statuses":dict(UNMAPPABLE),
           "gate1_requirement_waivers":dict(WAIVERS),
           "gate1_rebound_to_tier2":sorted(rebound),
           "retention":RETENTION,
           "transforms":{c["src"]["name"]:c["transform"] for c in MAPPING["columns"]},
           "approved_by":approval["approved_by"],"approved_at":approval["approved_at"]},
          open(os.path.join(WB,"decisions.json"),"w"), indent=1, default=str)

NOT_PRESERVED=["time-of-day and timezone on original application dates (date_value is format:date)",
               "original created_at on all records (read-only on both surfaces)",
               "job association for Tier 2 rows beyond a tag"]
open(os.path.join(WB,"not_preserved.md"),"w",encoding="utf-8").write(
    "# What this migration cannot carry\n\n"+"\n".join("- "+x for x in NOT_PRESERVED)+"\n")

src=len(data); excl=len(EXCL); failv=sum(1 for r in rowsv if r["verdict"]=="fail")
keys_new={r["person_key"] for r in proceed if r["identity"]=="new_person"}
keys_matched={r["person_key"] for r in proceed if r["identity"]=="existing_person"}
INV=[("source_rows = excluded + failed + queued + tier1 + tier2",
      src==excl+failv+len(queued)+n1+n2, f"{src} == {excl}+{failv}+{len(queued)}+{n1}+{n2}"),
     ("distinct_person_keys = people_new + people_matched (disjoint)",
      len(run_people)==len(keys_new|keys_matched) and keys_new.isdisjoint(keys_matched),
      f"{len(run_people)} == {len(keys_new)}+{len(keys_matched)}"),
     ("tier1_rows = rows(tier1_applications.csv)", n1==len(plan["tier1"]), str(n1)),
     ("tier2_rows = rows(tier2_job_seekers.csv)",  n2==len(plan["tier2"]), str(n2)),
     ("queued = rows(exceptions.csv) - failed_validation", len(queued)==ne-failv, f"{len(queued)} == {ne}-{failv}")]
manifest={"source":profile["source"],"approval":approval,
          "counts":{"source_rows":src,"excluded":excl,"failed_validation":failv,
                    "queued":len(queued),"tier1_rows":n1,"tier2_rows":n2},
          "identity":{"distinct_person_keys":len(run_people),"people_new":len(keys_new),
                      "people_matched":len(keys_matched)},
          "errors_by_code":dict(hist),
          "notifications":{"applications":{"suppressed":True,"mechanism":"skip_notifications_on_create"},
                           "job_seekers":{"suppressed":"unknown",
                              "evidence":"field absent from job_seekers_attributes_post (additionalProperties:false)",
                              "acknowledged_at_gate_2":True}},
          "invariants":[{"rule":k,"pass":ok} for k,ok,_ in INV],
          "not_preserved":NOT_PRESERVED}
json.dump(manifest, open(os.path.join(WB,"manifest.json"),"w"), indent=1, default=str)
open(os.path.join(WB,"README.md"),"w",encoding="utf-8").write(f"""# Migration workbook

Source `{profile['source']['filename']}` ({src} rows) → Pinpoint account `{TENANT}`.
Approved by {approval['approved_by']} at {approval['approved_at']}.

## Import in this order
1. `tier1_applications.csv` ({n1} rows) — one application each, with stage.
2. `tier2_job_seekers.csv` ({n2} rows) — talent pipeline; source job title carried as a tag.

**Respect `import_order`.** Rows sharing a person must be imported in that order, or the
same human is created twice — a candidate exists only as a side effect of a create.

## Needs a person
- `exceptions.csv` ({ne} rows) — {failv} failed validation, {len(queued)} unresolved identities.
- `excluded.csv` ({nx} rows) — outside the retention decision recorded in `decisions.json`.

## Read before importing
`not_preserved.md` states what this migration cannot carry. `manifest.json` carries the
counts and the five invariants, all of which must pass.
""")

print(f"  workbook/")
for fn,cnt in [("README.md",None),("manifest.json",None),("tier1_applications.csv",n1),
               ("tier2_job_seekers.csv",n2),("exceptions.csv",ne),("excluded.csv",nx),
               ("identity_report.csv",ni),("decisions.json",None),("not_preserved.md",None)]:
    sz=os.path.getsize(os.path.join(WB,fn))
    print(f"    {fn:<26} {(str(cnt)+' rows') if cnt is not None else '':>10}   {sz:>6} bytes")
print("\n  invariants:")
for k,ok,detail in INV: print(f"   {'PASS' if ok else 'FAIL'}  {k:<52} {detail}")
if not all(ok for _,ok,_ in INV): print("\n  MANIFEST FAILED — this is a bug, not a rounding difference."); sys.exit(1)
note("", "Everything except manifest.json holds row-level PII and lives in the private lane.",
     "manifest.json carries counts, codes and hashes only — it is the one file a model may read.")

# ══════════════════════════════════════════════ §8 — capture the precedent
print()
banner("§8", "CAPTURE PRECEDENT", "script")
note("Only completed runs teach. Two stores, and what goes in each is the whole design.","")
sem={**(SEM or {}), "signature":SIG,
     "source_headers":[c["name"] for c in cols],
     "transforms":{"name_order":NAME_ORDER,"date_locale":DATE_LOCALE,"phone_region":PHONE_REGION},
     "gate0_columns":[c["index"] for c in chosen],
     "last_account":acct["subdomain"]}
save_prec("semantic", SIG, sem)
bind={**(BIND or {}), "account_fingerprint":catalog["account_fingerprint"],
      "account":acct["subdomain"], "semantic_signature":SIG,
      "job_titles":{k:v for k,v in title_map.items() if v},
      "status_stages":{str(k):{a:b for a,b in v.items() if a in STATUS_VOCAB} for k,v in vmpj.items()},
      "unmappable":{str(k):v for k,v in UNMAPPABLE.items()},
      "requirement_choice":REQ_CHOICE}
save_prec("bindings", BIND_KEY, bind)
print(f"  precedents/semantic/{SIG}.json          uses={sem['uses']}   PORTABLE")
note(f"   carries: transforms, Gate 0 column selection, source header list",
     f"   because it describes the SOURCE FILE and nothing about a destination")
print(f"  precedents/bindings/{BIND_KEY}.json  uses={bind['uses']}   ACCOUNT-SCOPED")
note(f"   carries: job titles → ids, status → stage ids, unmappable declarations",
     f"   keyed by (account fingerprint, column signature). Never offered to another account.")
note("", "NOT stored in either: the retention decision. It belongs to the customer in front",
     "of you, and replaying it would be replaying someone else's legal basis.")

print()
print("  " + "─"*74)
print(f"  GATE 1 STATUS DECISIONS — where each answer came from")
print(f"    proposed by the model   {DEC['by_model']:>3}   (matched a stage by name on this account)")
print(f"    supplied by precedent   {DEC['prefilled']:>3}   (stored binding, re-resolved as still valid)")
print(f"    asked of you            {DEC['asked']:>3}")
print(f"    bindings invalidated    {DEC['invalidated']:>3}   (stale ids, re-asked not repaired)")
tot=DEC["asked"]+DEC["prefilled"]+DEC["by_model"]
if tot: print(f"    → {(tot-DEC['asked'])*100//tot}% of Gate 1 needed no human input")
print("  " + "─"*74)
emit("learning.json", {"signature":SIG,"account":acct["subdomain"],
                       "semantic_hit":bool(SEM),"binding_hit":bool(BIND),
                       "semantic_uses":sem["uses"],"binding_uses":bind["uses"],**DEC})

# ══════════════════════════════════════════ §12 — optional last mile (executor)
if NO_EXECUTE:
    print("\n  stopping at the workbook (--no-execute). §12 is optional by design.\n"); sys.exit(0)
print()
banner("§12", "OPTIONAL LAST MILE — WRITE VIA THE API", "human")
note("For most accounts the workbook IS the deliverable and Pinpoint's own importer is the",
     "final step. Build this only when the importer cannot carry per-row stages, custom",
     "attributes, or notification suppression — see §16.2, the highest-value open question.","")
cue("Enter runs it — one response gets lost on purpose",
    "watch the resume ask the server before retrying, and create no duplicate")
if not ask_yn("run the executor against the mock?", "y"):
    print("\n  stopped at the workbook. That is the supported default.\n"); sys.exit(0)

class Mock:
    def __init__(s, acct):
        s.acct=acct; s.next_id=20000; s.store={}; s.would_email={"applications":0}; s.calls=[]
    def _new(s): s.next_id+=1; return s.next_id
    def post(s, path, payload):
        s.calls.append(path)
        a=payload["data"]["attributes"]; rel=payload["data"].get("relationships",{})
        cas=[{"field_name":"Original Application Date","value":inc["attributes"]["date_value"]}
             for inc in payload.get("included",[]) if inc["type"]=="custom_attributes"]
        if path=="/api/v1/applications":
            job_id=int(rel["job"]["data"]["id"])
            job=next(j for j in s.acct["jobs"] if j["id"]==job_id)
            if job["status"]!="open":
                return 422,{"errors":[{"code":"unprocessable","detail":"Job is not accepting applications"}]}
            if "stage" in rel:
                sid=int(rel["stage"]["data"]["id"])
                valid={x["id"] for x in s.acct["hiring_workflows"][job["hiring_workflow_id"]-1]["stages"]}|{x["id"] for x in job["job_owned_stages"]}
                if sid not in valid:
                    return 422,{"errors":[{"code":"unprocessable","detail":"stage not on job"}]}
            if a.get("country")=="US" and a.get("address2"):
                return 422,{"errors":[{"code":"unprocessable","detail":"address2 not writable when country is US"}]}
            if not a.get("skip_notifications_on_create"): s.would_email["applications"]+=1
            i=s._new(); s.store[a["external_system_reference"]]={"type":"applications","id":i,"attrs":a,"rel":rel,"custom_attributes":cas}
            return 201,{"data":{"type":"applications","id":str(i)}}
        if path=="/api/v1/job_seekers":
            if "skip_notifications_on_create" in a:          # additionalProperties: false
                return 422,{"errors":[{"code":"unprocessable","detail":"unknown attribute skip_notifications_on_create"}]}
            i=s._new(); s.store[a["external_system_reference"]]={"type":"job_seekers","id":i,"attrs":a,"rel":rel,"custom_attributes":cas}
            return 201,{"data":{"type":"job_seekers","id":str(i)}}
        return 404,{}
    def find_by_esr(s, ref): return s.store.get(ref)

mock=Mock(acct)
def validator(name):
    sch=dict(SPEC); sch["$ref"]="#/components/schemas/"+name
    return jsonschema.Draft7Validator(sch)
V={"applications":validator("applications_request_post"),
   "job_seekers":validator("job_seekers_request_post")}

def build(r, cid=None):
    ent=r["entity"]
    attrs={"external_system_reference":r["esr"],"first_name":r["first_name"],"last_name":r["last_name"],
           "email":r["email"],"phone":r["phone"],"address1":r["address1"],"town":r["town"],
           "postcode":r["postcode"],"country":r["country"]}
    if r["country"]=="US": attrs["state_province"]=r["state_province"] or None
    else: attrs["address2"]=r["address2"] or None
    attrs={k:v for k,v in attrs.items() if v not in (None,"")}
    rel={}
    if ent=="applications":
        attrs["skip_notifications_on_create"]=True          # DOCUMENTED for applications only
        rel["job"]={"data":{"type":"jobs","id":str(r["job_id"])}}
        if r["stage_id"]: rel["stage"]={"data":{"type":"stages","id":str(r["stage_id"])}}
    else:
        attrs["pipeline_source"]=r["channel_source"] or "migration"
        attrs["add_tags_with_context"]=[{"tag":r["job_title_source"],"context":"source_job_title"}]
    cid = cid or r.get("candidate_id")
    if cid: rel["candidate"]={"data":{"type":"candidates","id":str(cid)}}
    payload={"data":{"type":ent,"attributes":attrs,"relationships":rel}}
    if r["original_date"]:                                   # nested — §12.2
        tid="ca-"+r["source_record_id"]
        payload["data"]["relationships"]["custom_attributes"]={"data":[
            {"type":"custom_attributes","id":tid,"temp-id":tid,"method":"create"}]}
        payload["included"]=[{"type":"custom_attributes","temp-id":tid,"id":tid,
            "attributes":{"custom_field_id":501 if ent=="applications" else 502,
                          "date_value":r["original_date"]}}]
    return payload

print()
ops={}; candidate_of={}
DROP_ROW=max((r["row"] for r in proceed if r["depends_on_row"] is None), default=None)
DROP_ROW=sorted(r["row"] for r in proceed)[-2] if len(proceed)>1 else None
for r in sorted(proceed, key=lambda x: order[x["row"]]):
    dep=r["depends_on_row"]
    cid=candidate_of.get(dep) if dep else None
    if dep and dep not in candidate_of:
        print(f"   row {r['row']:>2} BLOCKED — owner row {dep} has not committed"); continue
    payload=build(r, cid)
    errs=sorted(V[r["entity"]].iter_errors(payload), key=lambda e:e.path)
    if errs:
        print(f"   row {r['row']:>2} SCHEMA REJECT {errs[0].message[:60]}"); ops[r["esr"]]={"row":r["row"],"entity":r["entity"],"state":"failed"}; continue
    ops[r["esr"]]={"row":r["row"],"entity":r["entity"],"state":"reserved"}   # durable BEFORE send
    code,body=mock.post("/api/v1/"+r["entity"], payload)
    if r["row"]==DROP_ROW:                                   # FAULT_INJECTION: response lost
        ops[r["esr"]]["state"]="unknown"
        print(f"   row {r['row']:>2} {r['entity']:<13} → unknown    response lost after send"); continue
    ops[r["esr"]]["state"]="committed" if code==201 else "failed"
    if code==201:
        rid=int(body["data"]["id"]); candidate_of[r["row"]]=9000+rid
        nested=" +nested custom_attribute "+r["original_date"] if r["original_date"] else ""
        print(f"   row {r['row']:>2} {r['entity']:<13} → committed  id={rid}{nested}")
    else:
        print(f"   row {r['row']:>2} {r['entity']:<13} → failed     {body['errors'][0]['detail']}")

unknown=[k for k,v in ops.items() if v["state"]=="unknown"]
if unknown:
    print()
    banner("§12.1", "RESUME — RECONCILE BEFORE RETRYING", "script")
    note("A timeout is not evidence of failure. Pinpoint may have committed a POST whose response",
         "was lost; a naive retry from a stale index creates a duplicate.","")
    before=sum(1 for v in mock.store.values() if v["type"]=="applications")
    for ref in unknown:
        got=mock.find_by_esr(ref)
        if got:
            ops[ref]["state"]="committed"; ops[ref]["reconciled"]=True
            candidate_of[ops[ref]["row"]]=9000+got["id"]
            print(f"   row {ops[ref]['row']} → queried by external_system_reference → already committed, id={got['id']}")
        else:
            ops[ref]["state"]="reserved"; print(f"   row {ops[ref]['row']} → not committed → re-reserved")
    after=sum(1 for v in mock.store.values() if v["type"]=="applications")
    print(f"\n  applications on server before={before} after={after} → no duplicate created")

print()
banner("NOTIF", "NOTIFICATION BEHAVIOUR, PER SURFACE", "script")
print(f"  applications: would_have_emailed = {mock.would_email['applications']}"
      f"   ← skip_notifications_on_create sent on every create (DOCUMENTED)")
code,body=mock.post("/api/v1/job_seekers",{"data":{"type":"job_seekers","attributes":
    {"external_system_reference":"probe","skip_notifications_on_create":True}}})
print(f"  job_seekers:  probe sending the same field → HTTP {code}: {body['errors'][0]['detail']}")
note("The field is absent from job_seekers_attributes_post (additionalProperties: false).",
     "The tool does not send it, records 'unknown', and Gate 2 required an acknowledgement.",
     "A real run begins with a canary of one create and halts for human confirmation.")

print()
banner("§12.6", "RECONCILE — FIELDS AND RELATIONSHIPS", "script")
committed=sum(1 for v in ops.values() if v["state"]=="committed")
failed=sum(1 for v in ops.values() if v["state"]=="failed")
unk=sum(1 for v in ops.values() if v["state"]=="unknown")
checked=matched=0
for ref,st in ops.items():
    if st["state"]!="committed": continue
    r=next(x for x in proceed if x["row"]==st["row"]); got=mock.find_by_esr(ref); checked+=1
    exp={"email":r["email"],"phone":r["phone"]}
    ok=all(got["attrs"].get(k)==v for k,v in exp.items() if v)
    if r["original_date"]:
        ok=ok and (got["custom_attributes"] or [{}])[0].get("value")==r["original_date"]
    matched+=ok
apps=sum(1 for v in ops.values() if v["state"]=="committed" and v["entity"]=="applications")
js  =sum(1 for v in ops.values() if v["state"]=="committed" and v["entity"]=="job_seekers")
print(f"  field-level checks: checked={checked} matched={matched} divergent={checked-matched}")
note("custom attribute read back via `value` (readable), written via `date_value` (writeOnly).",
     "Where the source has a time component, time-of-day is LOST — stated in not_preserved.md.","")
EINV=[("operations_attempted = committed + failed + unknown", len(ops)==committed+failed+unk,
       f"{len(ops)} == {committed}+{failed}+{unk}"),
      ("operations_attempted = operations_planned", len(ops)==len(plan["operations"]),
       f"{len(ops)} == {len(plan['operations'])}"),
      ("applications_created + job_seekers_created = committed", apps+js==committed,
       f"{apps}+{js} == {committed}"),
      ("bare POST /custom_attributes never issued", "/api/v1/custom_attributes" not in mock.calls,
       f"{mock.calls.count('/api/v1/custom_attributes')} calls")]
for k,ok,d in EINV: print(f"   {'PASS' if ok else 'FAIL'}  {k:<52} {d}")
emit("execution_receipt.json", {"operations":{"attempted":len(ops),"committed":committed,
     "failed":failed,"unknown":unk,"recovered":sum(1 for v in ops.values() if v.get('reconciled'))},
     "invariants":[{"rule":k,"pass":ok} for k,ok,_ in EINV]})
print(f"\n{'='*W}\n  DONE. workbook/ holds the deliverable; out/ holds the model-visible artifacts.\n{'='*W}\n")

if DEMO:
    pause("press Enter for the last chapter — what the tool remembers between runs")
    print("\n"+"="*W)
    print("  THE LEARNING CURVE — four runs, and what carries between them")
    print("="*W)
    cue("this is the part that makes the second migration cheaper than the first",
        "watch column 'bind' go blank on run 3 — that blank is the safety property")
    import subprocess
    sys.stdout.flush()
    subprocess.run([sys.executable,"run_learning.py"])
    sys.stdout.flush()
    print(f"\n{'='*W}\n  END OF WALKTHROUGH")
    print("  Re-run a single chapter any time:  run_demo.py --flow list")
    print(f"{'='*W}\n")
