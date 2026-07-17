# Prompt for Claude Code: Human-Like Search Simulator & Browser Metrics Harness

## Project Overview

This repo runs automated searches in a browser (Edge, but should generalize to any Chromium/Selenium-supported browser) that **look and behave like a real human searching**, so we can capture realistic browser telemetry/metrics afterward. The existing codebase (Python + Selenium) already does basic search automation, but the "human-ness" and metrics layers are incomplete.

Before writing any code, read through the existing repo structure and existing modules, and give me a short summary of what's there and what's missing relative to the plan below. Then propose an architecture (feel free to push back or suggest better structure) before implementing.

## Core Concept: `HumanEngine`

Build a `HumanEngine` (or a small set of cooperating classes — your call on architecture) that governs *what* a simulated human searches for, *when*, and *how*, decoupled from the low-level Selenium driving. Rough responsibilities:

1. **Persona / memory model** — a persona has a set of recurring topics of interest, each with a "strength" that reinforces or decays over time (think spaced-repetition/forgetting-curve math, but inverted: things the persona can't retain get searched again and again, just with different phrasing each time — synonyms, rewordings, typos, shorthand, follow-up questions). Some topics are stable long-term interests; others are transient (learned once, rarely revisited); one or two are "chronic forgets" that recur indefinitely.
   - Don't hardcode a single persona — define a **character roster**: a set of distinct personas, each a data file (YAML/JSON), not code, so new ones can be added without touching `HumanEngine`. The engine should pick one persona per run (via config/CLI flag), and it should be straightforward to later run several personas concurrently under separate browser profiles if we want that down the line — keep that door open architecturally even if you only implement single-persona selection now.
   - Each character definition should cover everything persona-specific: topic list (with per-topic strength/decay/chronic-forget flags), work/leisure ratio and typical topics for each, chronotype (day person vs. night owl — see pacing section), typing speed and error rate, tab-hoarding tendency, and daily search-volume ceiling. See the roster below for a concrete starting set.
2. **Query generation / morphing** — given a topic, generate a query that's plausibly different from past queries on that topic (not just template-filling — vary phrasing, specificity, and sometimes make it a follow-up to a previous search).
   - Use a **local Ollama model** (invoked from the terminal / via its local REST API at `http://localhost:11434/api/generate`, not a hosted API) as the primary query generator — it'll produce far more natural, varied phrasing than a static template/random bank, and running locally avoids per-call cost and latency of a hosted LLM. Feed it the persona's topic, memory strength, and recent query history as context so it can plausibly "morph" the phrasing rather than repeat itself.
   - Design a fallback (template/Markov-based) for when Ollama isn't running or a model isn't pulled, so the engine degrades gracefully rather than hard-failing.
   - Recommend a small, fast model for this (e.g., something in the llama3.2/qwen2.5 small-parameter range) — pick based on latency, since this runs per-query — and note the choice + reasoning.
3. **Work vs. Leisure state machine** — two search modes:
   - **Work**: task-driven, narrower, more goal-directed, often session-initiating.
   - **Leisure**: passing-time browsing, wider topic drift, less goal-directed.
   - Typical flow is Work → Leisure → Work → Leisure ... but Leisure does **not** organically produce a Work session. This matches research on cyberloafing/online procrastination: browsing during a work context is largely driven by depleted self-regulation ("ego depletion" / the strength model of self-control) after effortful task work, by boredom, or by stress — and it serves a recovery function. Critically, the *return* to work is driven by external or state-based pressure (elapsed time, deadline proximity/temporal discounting, guilt, a new task arriving) rather than by anything encountered during the leisure browsing itself — nothing in cat videos organically produces a work thought. Model this as: Work session ends when task completes or a self-regulation/"focus" budget depletes → Leisure session starts → Leisure session ends via a timeout/guilt/deadline-pressure variable crossing a threshold (not content-driven) → either idles or a new Work session starts from an external trigger. Flag any part of this you think needs a cleaner state-machine formulation — I want the nuance preserved but am open on implementation.
4. **Session pacing** — realistic dwell time on results, scroll behavior, occasional query abandonment/refinement, idle gaps between sessions. See the dedicated section below — this needs to run in real wall-clock time, not compressed.

## Realism, Pacing & Volume Constraints

This is the part that actually determines whether the output looks human, so treat it as a first-class design concern, not a detail to fill in later.

**Run in real time, at real volume.** The engine should be a long-lived process (daemon/scheduler), not a script that blasts through searches quickly. Sleep for genuinely human-scale gaps between actions and sessions — seconds to minutes within a session, and minutes to hours between sessions. On volume: published estimates of per-person daily search counts vary a lot depending on source and skew from heavy/professional users (rough estimates cluster somewhere in the single digits to low double digits per day for a typical individual, with a lot of variance) — so treat "single digits per persona per day" as the target ceiling, not something to approach. Err toward less.

**Time-of-day modulation, grounded in circadian attention research:**
- Attention/alertness is lowest just after waking (early morning, roughly the first couple hours), rises through late morning, and peaks around midday.
- A well-documented dip follows lunch (roughly early-to-mid afternoon) — this is a circadian effect, not just a food coma — and is a natural place to bias probability toward Leisure/cyberloafing sessions rather than Work, consistent with research linking low-effort browsing to lapses in self-regulation.
- A second, smaller alertness rise typically occurs in the later afternoon/evening.
- Attention bottoms out overnight. Most personas should have little to no activity in that window; a minority "night owl" persona type is realistic and worth supporting as a config option rather than the default.
- Use this as a probability weighting on session type and start time, not a rigid schedule — add per-persona jitter/chronotype variance so multiple personas don't all sync to the same clock.
- For work-session *length*, use something on the order of a ~90-minute ultradian cycle as a loose unit (a stretch of focus followed by a natural dip) rather than a fixed duration — vary it per persona and per time of day.

**Interruptions and "getting an idea" mid-task.** Not all task-switching is externally triggered — a meaningful share of real interruptions are self-generated (the person just thinks of something else and acts on it), which is the mechanism to model for "has an idea, opens a new tab" behavior: it should fire probabilistically during a Work (or Leisure) session, independent of any external event. When it fires:
- Open a new tab, and either (a) follow through — type a query, read for a bit, and optionally let that topic bleed into memory as a new thread — or (b) abandon it almost immediately (start typing or just sit on the blank tab a few seconds, decide it's not worth it, close it). Bias toward abandonment for low-strength/impulsive ideas and follow-through for ideas tied to a real topic in memory.
- Returning to the original task afterward shouldn't always be instant or clean — sometimes it happens right away, sometimes only after drifting through one or two more tabs/topics first, and sometimes the original task just doesn't get resumed this session. Treat "time to resume" as a distribution, not a fixed constant — widely-cited numbers here (e.g. "23 minutes to refocus") are frequently misquoted as a universal constant when the underlying research actually measured full interruption chains, not a single clean reset, so don't hardcode a specific figure as gospel.

**Tab lifecycle.** Real people don't manage tabs tidily:
- Tabs from completed Work tasks tend to close fairly promptly and deliberately.
- Tabs from abandoned Leisure detours may close quickly (impulsive "nah") or may just sit open, sometimes for the rest of the session.
- Model tab accumulation over a session with occasional batch "cleanup" closes, rather than always closing one-for-one after use.
- Also include: revisiting a previous results page, refining a query in place instead of opening a fresh tab, hitting back, and re-searching a slightly reworded version of a query you already ran a few minutes ago — not every impulse needs a brand-new tab.

**Target & volume safety.** Given the low-volume constraint above and that this will run against real Selenium (not a stealth/anti-detection layer — see note below), default the config to a safe test target (a local mock search page or self-hosted engine) and treat pointing it at a live third-party search engine as an explicit opt-in config change, not the default — that's on me to review each engine's terms of service before flipping that switch, but the engine itself should make "low volume, single stable session, no parallelism" the path of least resistance regardless of target.

## Example Character Roster

Seed the roster with a handful of distinct starting characters so there's real variety to choose from — treat these as a starting point, not a fixed list:

- **Grad student** — Work topics: a specific research area, citation formatting, funding/grant deadlines. Leisure topics: a hobby (climbing, a TV show fandom), recipes. Chronic-forget: some recurring statistics/software syntax they never quite retain. Day-type chronotype, moderate-to-heavy tab-hoarder, low volume, frequent post-lunch leisure dip.
- **Freelancer/contractor** — Work topics: shift constantly per active client/project (topic list should churn faster than other personas'). Leisure topics: travel planning/dreaming, personal finance. Chronic-forget: a recurring tool/platform quirk. Irregular chronotype (work hours aren't 9–5), low tab-hoarding (tidier out of professional habit).
- **Night-owl developer** — Work topics: a programming ecosystem, debugging a specific recurring error. Leisure topics: gaming, tech news. Chronic-forget: a CLI flag or config syntax they look up every time. Evening/night chronotype, heavy tab-hoarder, fast/error-prone typing.
- **Parent balancing work and household admin** — Work topics: task-oriented and narrow, high focus during defined windows. Leisure topics: parenting advice, recipes, local events. Chronic-forget: a kid's school-related detail or scheduling logistic. Fragmented sessions (short, interrupted often), lowest volume of the roster.
- **Retiree hobbyist** — Work topics: minimal or none (or a light volunteer/admin task instead of "work" in the job sense — worth deciding whether to relabel this state per-persona). Leisure topics: a deep, narrow hobby (genealogy, gardening, a specific hobbyist forum topic). Chronic-forget: a recurring how-to they never fully internalize. Strong day chronotype, low volume, slow/deliberate typing.

Each should be fleshed out into a real data file with concrete topic lists and parameter values — the above is the shape, not the final content. Flag if you think a different set of archetypes would give better behavioral variety than these five.

## Human-Like Interaction Layer

For the actual browser-driving mechanics (mouse movement, typing, scrolling), don't reinvent this — evaluate and integrate existing libraries as pip deps or git submodules. Candidates I found worth looking at:

- **[HumanCursor](https://github.com/riflosnake/HumanCursor)** — realistic mouse movement for Selenium (web + system cursor), actively maintained.
- **[pyclick](https://github.com/patrikoss/pyclick)** — Bezier-curve-based human mouse movement.
- **[Emunium](https://pypi.org/project/emunium/)** — mimics human mouse/typing/scroll for Selenium or Pyppeteer.
- **[human_typer](https://github.com/UnMars/human_typer)** — human-like typing with configurable CPM and typo rate, has direct Selenium element support.
- **[HumanTyping](https://github.com/Lax3n/HumanTyping)** — Markov-chain-based typing simulator (errors, corrections, fatigue, speed variation) for Selenium/Playwright.

Pick whichever combination best covers mouse + typing + scroll without excessive overlap, and tell me which you chose and why. Clone as git submodules under something like `vendor/` if you go that route, and note it in the README.

Note: some of the wider "undetected-chromedriver" / "selenium-stealth" ecosystem exists for evading bot-detection on live third-party sites — that's a different concern from ours (we're not trying to evade anything, just generate realistic behavior for our *own* metrics), so don't pull those in unless you think there's a legitimate metrics-related reason to.

## Metrics Collection

After each search, capture whatever's available via the WebDriver/DevTools Protocol:
- Navigation Timing / Resource Timing API (via `driver.execute_script`)
- Performance log entries (`goog:loggingPrefs` / CDP `Performance.getMetrics`, where supported)
- Page load time, DNS/connect/TTFB breakdown, resource counts/sizes
- Anything browser-specific worth capturing in Edge vs. Chrome vs. Firefox — flag capability differences since we want this to generalize across browsers, not just Edge

Design this as a pluggable `MetricsCollector` so swapping browsers doesn't require touching the `HumanEngine` logic. Output format: your call, but make it structured (JSON lines or similar) and easy to correlate back to the search session/query that produced it.

## What I want from you

1. First pass: explore the existing repo, summarize current state vs. this plan, and propose a concrete class/module architecture (e.g., `HumanEngine`, `Persona`, `TopicMemory`, `QueryGenerator`, `SessionPlanner`, `MetricsCollector`) with how they interact, including how the character roster is loaded/selected.
2. Flag any design decisions or ambiguities in the above (especially the Leisure→Work transition rule) before you commit to an implementation — ask me rather than guessing on anything that materially changes behavior.
3. Recommend specific libraries/submodules with brief justification, then implement.
4. Implement incrementally: persona/memory model and query generation first (it's testable without a browser), then wire into the existing Selenium driver, then the metrics layer, then the timing/pacing and tab-behavior layer.
5. Include basic tests for the query-morphing/memory logic, since that's the part most prone to silent bugs (e.g., a topic never actually decaying, or always producing identical queries).
6. Keep the wall-clock pacing and volume constraints real throughout — a "fast mode" for development/debugging is fine as an explicit flag, but the default behavior should always run at genuine human speed and volume, since that realism is the actual point of the project.
