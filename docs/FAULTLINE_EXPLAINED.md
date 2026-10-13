# Faultline, explained simply

*Written like a teacher explaining to a student. No jargon without a meaning next to it.*

---

## 1. The problem in one story

Imagine your school has a **shared recipe book** that three different kitchens use.

- The book (we call it the **shared library**) says: "Mix with the standard whisk."
- Kitchen A, B and C each bought their **own tools**. Kitchen C bought a *new* whisk model.
- One day the book works fine in kitchens A and B, but in kitchen C **the whisk does not fit**, and the cake fails.

Nobody planned this. The book did not change. Kitchen C did not do anything wrong. The **tools around the book were different**, and that broke it.

In software this happens all the time:

- A company has **many code repositories** (folders of code on GitHub).
- One repo is a **shared library** (the recipe book). Other repos (the kitchens) **use** it.
- Each repo installs its **own versions of other packages** (its tools). These are called **dependencies**.
- If the versions differ between repos, the shared library can **break in one repo and work in another**.

This hidden difference is called **dependency drift**.

### Our problem statement (PS07)
**"Cross-Repo Dependency Drift Detector":** find out when a shared library will break (or behave differently) in other repositories because their dependency versions have drifted apart, **across many repositories at once**.

---

## 2. Why existing tools are not enough

Tools like **Dependabot** and **Renovate** are great, but they mostly:

| What they do | What they do NOT do |
|---|---|
| Look at **one repo** and say "a newer version exists" | Look at **two repos together** and ask "will the shared code break there?" |
| Raise a **warning** ("this might be outdated") | **Prove** anything. A warning is just a guess |
| Compare version numbers | Actually **run** the code in the other repo's setup |

So developers get a pile of warnings, ignore most of them, and still get surprised by real breakages.

---

## 3. Our idea: "Witnesses, not warnings"

> A **warning** says "maybe it breaks."
> A **witness** says "here, I made it break, and you can repeat it yourself."

Think of a court. A rumour is not enough. A **witness** who saw it happen is.

Faultline only says "this breaks" when it can **show it happening, three times in a row, and the same way each time**.

### The simple rule we use (the "3 + 3 rule")
1. Run the shared code in the library's **own** setup → it must **pass 3 out of 3 times**.
2. Run the same code in the **other repo's** setup → it must **fail 3 out of 3 times, with the same error**.
3. Every one of those runs must be **fresh** (really executed, not remembered from a cache).

If this is true, we have a **witness**. If it is not, we say honestly "inconclusive" or "no difference observed". We **never** say "compatible" or "safe", because we cannot prove that.

---

## 4. How Faultline works, step by step

Imagine a factory line. Each step is a small machine.

```
GitHub links  →  1. Pin  →  2. Fetch  →  3. Read  →  4. Resolve  →  5. Relate
                                                                      ↓
        9. Report  ←  8. Verdict  ←  7. Run & Witness  ←  6. Build worlds
```

1. **Pin.** You give us GitHub links. We turn "the latest version" into an **exact commit number** (a fixed snapshot) so results can be repeated tomorrow.
2. **Fetch safely.** We download that exact snapshot **inside a locked box (a sandbox)**. We never run the downloaded code on your machine here.
3. **Read the files.** We *read* `requirements.txt`, `pyproject.toml`, `package.json`, `pom.xml` and lock files as plain text. We do **not** run them.
4. **Resolve.** We work out the **exact versions** each repo really uses. If a lock file exists, we trust it. If not, we use the official tool (`uv`) as of a recorded date. We **never write our own guessing solver**.
5. **Relate.** We only connect two repos when there is **evidence** (for example "repo B lists repo A's package name in its requirements, line 12"). Look-alike names are put in a **"suspected" tray** and never create a finding on their own.
6. **Build "worlds".** A **world** = the exact list of package versions a repo uses. We build each world in a sealed box with **no internet**, so it is exactly what we think it is.
7. **Run and find witnesses.** We import and run the shared library in the library's world and in the consumer's world, three times each, in the sandbox.
8. **Verdict.** A fixed, ordered rule table decides the result. **No AI is used to decide.** The same evidence always gives the same answer.
9. **Report.** We show the result, the evidence, and a downloadable **evidence bundle** (a zip anyone can re-check).

### Safety, in simple words
- Code from GitHub runs **only inside a locked container**: no internet, no admin rights, limited memory and time.
- We treat everything we read from the internet as **data, not instructions**.
- Secrets are scrubbed from reports.

---

## 5. What a result looks like

Example from our test setup (we call these *fixtures*):

- Shared library: `acme-models` (needs Flask 2.2.2 and Werkzeug 2.2.3).
- Repo `notify-svc` installs **Werkzeug 3** (newer).
- Faultline runs `import acme_models.web`:
  - In the library's own world → **works** (3 of 3).
  - In notify-svc's world → **fails** (3 of 3) with `ImportError: cannot import name 'url_quote' from 'werkzeug.urls'`.
- Result: **BREAK WITNESSED**. We also show *which* package difference caused it.

Other repos get fair results too:
- `orders-svc` has the same versions → **NO DRIFT** (nothing to check).
- `billing-svc` has different versions but only uses safe parts → **NO DIVERGENCE OBSERVED** (we say exactly what we did and did not check).

The possible verdict words are fixed: **BREAK WITNESSED, SILENT DIVERGENCE WITNESSED, NO DIVERGENCE OBSERVED, EXPOSED, POTENTIAL, NOT EXPOSED, INCONCLUSIVE, HYGIENE.**

---

## 6. What makes this new (the novelty and the gap)

**The gap:** today's tools stop at "version A differs from version B." Nobody (in the free tools we looked at) answers: **"Does my shared code actually fail in *their* setup? Prove it."**

**What is new in Faultline**

| Idea | Why it matters |
|---|---|
| **Witnesses, not warnings** | Every claim is a repeatable experiment, not a guess |
| **Cross-repo view** | Looks at the shared library *and* each consumer together |
| **Exact worlds, reproducible** | Pinned commits, hashed packages, built offline: same input, same result |
| **Honest verdicts** | Says "inconclusive" instead of pretending; never says "compatible" |
| **Evidence bundle** | A zip with all runs, checkable by a third party |
| **No AI in the decision** | Deterministic: easy to trust and audit |
| **Safety first** | Untrusted code only runs in a locked sandbox |
| **Root-cause (next stage)** | Find the *smallest* set of packages that causes the break (two-sided ddmin) |

---

## 7. What we have built so far

(From our checklist: 28 of 63 milestones done.)

- **Foundation:** project layout, database, job queue, health and capability pages.
- **Sandbox:** locked container runner and an offline world builder.
- **Proof engine:** import oracle, test oracle, the 3+3 witness rule, evidence bundle with an independent verifier.
- **Real repos:** paste a GitHub link → pinned commit → safe fetch → file inventory.
- **Reading projects:** Python (requirements, pyproject, uv.lock, poetry.lock), npm (package-lock), Maven (pom.xml, with safe XML reading).
- **Worlds:** from lock files or the official resolver; shown in a **World Inspector** (declared range vs resolved version vs visible version).
- **Relationships:** evidence-based links between repos; look-alikes go to a suspected tray.
- **Cells:** one test setup per unique world difference, with exact counts.

We tested on real repos (for example Flask, mocha, spring-petclinic) and fixed real bugs that this found.

## 8. What is still to do

- Run the oracles on real, ingested repos end to end (live slice) and the final verdict table tests.
- Call-site checking (do the consumer's calls still fit the new function signatures?).
- Full dashboard with matrix, witness page and export.
- **Attribution:** which exact package change caused the break.
- Replaying a downloaded evidence bundle on another machine.
- Real-world historical case, demo mode, benchmark with honest numbers, submission pack.

## 9. Honest limits (we say them out loud)

- Our sandbox is Docker Desktop, not a stronger isolation like gVisor.
- Python is fully supported; npm and Maven are **inventory only** (we show what they declare and resolve, but we do not run them yet).
- We cannot prove code is safe. We can only show breaks we can reproduce.
- Numbers in our report come from scripts with denominators, never invented.

---

## 10. One-line summary to remember

**Faultline finds the cross-repo breaks that other tools only guess about, by actually reproducing them three times in the other repo's real dependency setup, and shows you the proof.**
