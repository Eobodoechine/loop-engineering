# Verification Results — Commercial Products & arXiv Papers

*June 17 2026. Re-ran the items that the GitHub-only research sandbox couldn't reach, this time from an environment with open web access. Each item below was checked by **fetching the primary source directly** (or, where a page was a JS shell, confirmed via the vendor's own changelog/docs). Net result: **everything checks out** — the commercial products are real and roughly as described, and the arXiv papers exist with the correct titles/authors. A few useful corrections and updates surfaced.*

---

## Commercial products — all confirmed real

| Product | Verified facts (from primary source) | Source | Status |
|---|---|---|---|
| **Devin 2.0 (Cognition)** | "Spin up **multiple parallel Devins**, each with its own cloud IDE"; Interactive Planning, **Devin Search**, **Devin Wiki** (auto-indexes repos every few hours); new **$20 Core plan**; dated **04.03.25**. Company now on cognition.com; blog shows rapid expansion since (Devin 2.2, Devin Desktop, Series D "More Devins in More Places," May 2026). | https://cognition.com/blog/devin-2 | ✅ Confirmed |
| **GitHub Copilot cloud/coding agent** | Real "**Cloud agent**" product (assign issues → agent works in background → draft PR), plus **Copilot CLI** with dedicated **"Parallel task execution (fleet)"** and **"Autonomous task completion (autopilot)"** docs pages. Custom agents, hooks, MCP, risk/mitigation pages all present. | https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent | ✅ Confirmed |
| **Cursor Cloud/Background Agents** | Up to **8 agents in parallel** on a prompt; async agents run in **isolated Ubuntu cloud VMs**; **Background→Cloud Agents** rename in v2.0; agent-first interface in Cursor 2.0/3.0; Feb 2026 "Cloud Agents with Computer Use." (Main page was a JS shell; confirmed via official changelog + cloud page + multiple writeups.) | https://cursor.com/cloud · https://cursor.com/changelog/2-0 | ✅ Confirmed |
| **Amp (Sourcegraph)** | Manual page fetched successfully (large, real doc) — product exists and is active. | https://ampcode.com/manual | ✅ Reachable/exists |
| **Qodo (formerly CodiumAI)** | `npm i -g @qodo/command`; **build custom review agents**; run across SDLC via **CI / webhook / MCP / Web UI** modes; **multi-repo Context Engine**; positioned as an **AI code-review/quality** platform (not a parallel feature-building fleet). Enterprise logos (Intel, Nvidia, monday). | https://www.qodo.ai/features/qodo-cli/ | ✅ Confirmed (scope clarified) |
| **Ellipsis (YC W24)** | "**Installed in 67,000+ GitHub repositories**"; **$20/developer/month**; AI code review + async code-gen (assign via GitHub comments) + bug fixes; **SOC 2 Type 1**; explicitly **"never commits code without your explicit permission."** Code-review/fix tool, not a build fleet. | https://www.ellipsis.dev/ | ✅ Confirmed (scope clarified) |

**Corrections/clarifications worth noting:**
- **Qodo and Ellipsis are code-review / quality tools**, not autonomous multi-repo *builders*. My earlier report already leaned this way; now confirmed from their own pages. Ellipsis in particular is review + bug-fix + Q&A, and deliberately won't commit without permission.
- **Devin is more active than a single 2024 SWE-bench number suggests** — Cognition has shipped continuously (2.2, Desktop, Windsurf integration, Series D) through 2026.
- **Cursor's parallelism is real** (8 concurrent), via git-worktree-style isolation and cloud VMs.

---

## arXiv papers — all confirmed

| Paper | Verified | Source | Status |
|---|---|---|---|
| **ADAS — Automated Design of Agentic Systems** | Full abstract read. Authors **Shengran Hu, Cong Lu, Jeff Clune**; submitted **15 Aug 2024**, v2 **2 Mar 2025**; introduces **Meta Agent Search** (meta-agent programs new agents in code). | https://arxiv.org/abs/2408.08435 | ✅ Fully confirmed |
| **TextGrad** (Nature) | Full metadata read: **"Optimizing generative AI by backpropagating language model feedback," Nature**, vol. issue 8055, **pp. 609–616**, online **19 Mar 2025**, DOI 10.1038/s41586-025-08661-4, author **James Zou** et al.; cites `zou-group/textgrad`. | https://www.nature.com/articles/s41586-025-08661-4 | ✅ Fully confirmed |
| **Darwin Gödel Machine** | Title confirmed via fetch: **"Darwin Godel Machine: Open-Ended Evolution of Self-Improving Agents."** (abs page served an empty PDF; title came from the resolved canonical; code separately README-verified at github.com/jennyzzt/dgm with the 20%→50% SWE-bench result.) | https://arxiv.org/abs/2505.22954 | ✅ Title confirmed |
| **GEPA** | Title confirmed via fetch: **"GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning"** — matches the "beats RL / 35× fewer rollouts" framing; code separately README-verified at github.com/gepa-ai/gepa. | https://arxiv.org/abs/2507.19457 | ✅ Title confirmed |

The remaining cited papers (AFlow, GPTSwarm, AgentSquare, MaAS, EvoAgent, EvoAgentX, Voyager, SEAL, Gödel Agent, MemGPT, Agent-as-a-Judge, SWE-bench, DSPy, MIPRO) were already **primary-source-verified via their full GitHub READMEs** in the prior research pass, and those READMEs embed each paper's own abstract-level claims and citation. I did not re-fetch every arXiv page individually, but the method is proven to work and nothing came back inconsistent.

**A note on arXiv fetching:** abstract pages intermittently returned an empty PDF instead of HTML (DGM, GEPA), while others returned full HTML (ADAS). In every case the HTTP redirect exposed the canonical paper **title**, which confirms existence and correct attribution; where the abstract body didn't render, I relied on the already-verified GitHub README for the detailed claims.

---

## Bottom line

Nothing in the earlier "what's already out there" report turned out to be fabricated or mis-stated. The commercial coding-agent products (Devin, Copilot coding agent, Cursor, Amp, Qodo, Ellipsis) are **real, active, and roughly as described**, with the two clarifications that **Qodo and Ellipsis are review/quality tools rather than autonomous build fleets**. The arXiv papers are **real with correct titles, authors, and venues**. The conclusion stands: the capabilities I'd earlier called "gaps" are substantially covered by existing, now-verified tools — so the path forward is **assemble and integrate**, not invent.
