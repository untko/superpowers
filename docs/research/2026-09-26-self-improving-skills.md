# Self-improving agent skills: current practice (Sept 2026)

Scope: SKILL.md-style instruction packages (Claude Code, Codex, and other harnesses that read the Agent Skills format), and how to run a loop that captures friction, revises skills, and proves each revision is better before it lands. Sources are primary: vendor docs, source code, and arXiv papers. A claim marked **unverified** could not be confirmed at the source.

## Bottom line

1. **Unattended self-editing is not a safe default.** SkillsBench found that "Self-generated Skills provide no benefit on average", while curated skills added +16.2pp ([SkillsBench](https://arxiv.org/abs/2602.12670)). SkillLearnBench found that "self-feedback alone induces recursive drift", and that improvement across iterations comes from *external* feedback ([SkillLearnBench](https://arxiv.org/abs/2604.20087)). So an edit should land only when an external signal backs it: a verifier, a test, a user correction, or human review. The model's opinion of its own work is not enough.
2. **Split the loop into three roles.** An *append-only capture log* comes first. A *reflector* turns it into proposed changes, and a *curator* merges those changes as small itemized edits. This is ACE's Generator/Reflector/Curator split, and its curator is "deterministic, non-LLM logic" ([ACE](https://arxiv.org/html/2510.04618)). Do not let an LLM rewrite a whole SKILL.md from the log.
3. **Make edits small deltas, never full rewrites.** In ACE, a monolithic rewrite collapsed a context from 18,282 to 122 tokens and dropped accuracy from 66.7 to 57.1, below the no-adaptation baseline of 63.7 ([ACE](https://arxiv.org/html/2510.04618)).
4. **Gate every edit with a with-vs-without (or old-vs-new) eval over multiple runs.** Claude Code ships this as `claude plugin eval`: WITH / W/OUT / Δ, three runs per case by default, and exit code 1 below `--threshold` ([plugin evals](https://code.claude.com/docs/en/plugin-evals)). skill-creator does the same with `evals/evals.json` and an `old_skill` snapshot as the baseline ([skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)).
5. **Test the `description` (triggering) separately from the body (output quality).** Use should-trigger and should-not-trigger queries, repeat them, keep a held-out test split, and pick the winner on test score ([run_loop.py](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/run_loop.py)).
6. **Hide the grader from the thing being optimized.** The Darwin Gödel Machine deleted the markers its hallucination checker relied on, which earned a perfect score without fixing the problem. The authors found such hacking "occurs more frequently" when the checking functions are visible ([DGM](https://arxiv.org/html/2505.22954)).
7. **Fight bloat actively.** Focused skills with 2–3 modules beat comprehensive documentation ([SkillsBench](https://arxiv.org/abs/2602.12670)), and Anthropic's guidance is to keep the SKILL.md body under 500 lines ([best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)). Keep helpful/harmful counters and prune what stops earning its place ([ACE](https://arxiv.org/html/2510.04618), [ExpeL](https://arxiv.org/abs/2308.10144)).
8. **Cadence:** capture on every session (cheap, deterministic hooks). Distill and evaluate in periodic batches, because each gated eval is real model spend. Every landed edit is a git commit with its benchmark attached, so rollback is `git revert`.

## 1. Capture: what triggers a candidate improvement, and how to store it

**Signals that exist as first-class events in harnesses.** Claude Code hooks expose the raw friction signals directly:
- `PostToolUseFailure` carries `tool_name`, `tool_input`, `error` and `is_interrupt`. The docs advise keying on `tool_name`, `is_interrupt` and the `Exit code N` line, and not on the rest of the string, whose format varies ([hooks](https://code.claude.com/docs/en/hooks)).
- `UserPromptSubmit` carries the user's `prompt`, which is where corrections show up.
- `Stop` and `SubagentStop` carry `last_assistant_message`.
- `SessionEnd`, `PreCompact` and `PostCompact` fire at lifecycle boundaries.
- All of them receive `transcript_path` ([hooks](https://code.claude.com/docs/en/hooks)).

A skill can declare `hooks` in its own frontmatter. They register when the skill is invoked and stay active for the rest of the session, so a skill can instrument its own use ([skills](https://code.claude.com/docs/en/skills), [hooks](https://code.claude.com/docs/en/hooks)).

**Signals the research uses:**
- *Execution feedback plus self-verification.* Voyager adds a skill to its library only after the program passes self-verification. Its iterative prompting uses "environment feedback, execution errors, and self-verification" ([Voyager](https://arxiv.org/abs/2305.16291)).
- *Scalar or free-text outcome feedback, turned into a verbal reflection.* Reflexion takes feedback from external or internally generated sources, stores the reflection in an episodic memory buffer, and does not update weights ([Reflexion](https://arxiv.org/abs/2303.11366)).
- *Contrasting successes with failures.* ExpeL extracts insights from both successful and failed trajectories ([ExpeL](https://arxiv.org/abs/2308.10144)).
- *Mining past trajectories for recurring routines.* AWM induces "workflows" from past trajectories, either offline from training examples or online from test queries ([AWM](https://arxiv.org/abs/2409.07429)).
- *Natural execution feedback without labels.* ACE works this way, but degrades without ground truth: on the finance benchmarks it scored 72.9% average without labels versus 81.9% with them ([ACE](https://arxiv.org/html/2510.04618)).

**Human-observed friction.** Anthropic's documented loop is observational. Use the skill with "Claude B" on real tasks, note where it "struggles, succeeds, or makes unexpected choices", and bring that back to "Claude A" ([best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)). The same page lists navigation signals worth logging: unexpected exploration paths, missed references, sections read over and over (promote them into SKILL.md), and bundled files never read (possibly unnecessary). Anthropic's launch post recommends asking Claude to "capture its successful approaches and common mistakes" into the skill ([Anthropic engineering](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)).

**Usage and cost telemetry.** `/skill-doctor` (Claude Code v2.1.261, Sept 2026) reports each skill's context cost and invocation count, and flags skills that have never been invoked. This came from secondary reporting only and is **unverified at a first-party doc**.

**Storage.** Systems that work keep raw observations and distilled knowledge apart:
- ACE stores knowledge as itemized bullets. Each bullet has an id and counters for how often it was marked helpful or harmful ([ACE](https://arxiv.org/html/2510.04618)).
- ExpeL keeps an insight list with importance counts ([ExpeL](https://arxiv.org/abs/2308.10144)).
- DGM and SICA keep an *archive* of every variant together with its benchmark results ([DGM](https://arxiv.org/html/2505.22954), [SICA](https://arxiv.org/html/2504.15228)).

In practice: capture into an append-only JSONL log per skill. Write only structured fields (event, skill, tool, exit code, session id, transcript path), so capture stays deterministic and involves no LLM. Distilled content lives only in the skill files, under git.

## 2. Distillation: from observations to edits

**Delta edits, not rewrites.** ACE names two failure modes of LLM-rewritten context:
- *brevity bias*: summarization "drops domain insights for concise summaries";
- *context collapse*: "rewriting erodes details over time".

Its fix is "structured, incremental updates". The Reflector emits candidate bullets and refines them for up to 5 rounds. The Curator merges them deterministically. A "grow-and-refine" step then dedups with semantic embeddings, either after each delta or lazily when the context overflows ([ACE](https://arxiv.org/html/2510.04618)). ExpeL uses the same kind of closed edit vocabulary: `ADD`, `EDIT`, `UPVOTE`, `DOWNVOTE`, with an insight removed when its count reaches zero ([ExpeL](https://arxiv.org/abs/2308.10144)).

**Batching and dedup.** Batching is what makes the loop affordable and less noisy. ACE's non-LLM curator exists specifically to allow "parallel batched adaptation" ([ACE](https://arxiv.org/html/2510.04618)). GEPA reflects over sampled trajectories and combines "complementary lessons from the Pareto frontier" instead of following one trajectory ([GEPA](https://arxiv.org/abs/2507.19457)). Batch across sessions, so one noisy session cannot author an edit alone.

**Who proposes.** Every documented pattern separates the author of an edit from the actor who performed the task:
- Anthropic's Claude A (editor) / Claude B (user of the skill) split ([best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices));
- ACE's Reflector, which is separate from the Generator;
- OpenAI's "meta-prompt agent" that rewrites the prompt based on grader failures ([OpenAI cookbook](https://developers.openai.com/cookbook/examples/partners/self_evolving_agents/autonomous_agent_retraining));
- SICA's use of the best agent so far in its archive as the meta-agent ([SICA](https://arxiv.org/html/2504.15228)).

The agentskills.io guidance hands the proposer three inputs, failed assertions, reviewer complaints and transcripts, plus the current SKILL.md. It tells the proposer to "Generalize from feedback", to keep the skill lean, and to delete instructions that the transcripts show causing wasted work ([agentskills.io](https://agentskills.io/skill-creation/evaluating-skills)). skill-creator adds three rules: "explain the why" in place of rigid MUSTs, remember that the skill will run "millions of times", and avoid overfitting to the eval examples ([skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)).

**Where the edit should go.** Prefer the lowest-freedom fix that works. When an operation is fragile, a deterministic script beats more prose ([best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)). If a skill keeps being ignored, the Claude Code docs suggest strengthening the `description`, or using hooks to "enforce behavior deterministically" ([skills](https://code.claude.com/docs/en/skills)).

## 3. Evaluation and gating

**Baseline comparison is the core primitive.** Anthropic's recommended order is: identify gaps without the skill, write at least three evals, measure the baseline, then write the minimal instructions that make the evals pass ([best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)). When improving an existing skill, the baseline is a snapshot of the previous version, saved as `old_skill/`. Runs are aggregated into `benchmark.json` with pass rate and mean ± stddev for time and tokens ([skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)).

**`claude plugin eval` is the CI-grade gate** ([plugin evals](https://code.claude.com/docs/en/plugin-evals)):
- *Run count:* "One run of a non-deterministic agent tells you little", so every case runs 3× per arm by default. A single run is only for cheap iteration: "confirm any change at the default three runs before you trust it".
- *Graders:* six types. `regex`, `tool_used`, `tool_order` and `file_exists` are free and deterministic. `llm` and `baseline` use a judge model. There are no custom-code graders.
- *Fair Δ:* a `tool_used: Skill` grader is excluded from scoring in both arms, because it can never pass without the plugin and would inflate Δ.
- *CI gating:* pin `--model` in CI "so a model rollout isn't mistaken for a plugin regression". Cap spend with `--max-cost-usd`. The command exits 1 below `--threshold` (default 1.0).
- *Isolation:* each run happens in a fresh, sandboxed, non-interactive session.

**Trigger-accuracy tests for `description`.** In skill-creator:
- Write about 20 realistic queries, split between should-trigger and should-not-trigger, with an emphasis on "near-misses".
- `run_loop.py` defaults: `--holdout 0.4`, `--runs-per-query 3`, `--trigger-threshold 0.5`, `--max-iterations 5`.
- The proposer sees training results only. Test fields are stripped before it runs, and the best description is chosen by test score ([run_loop.py](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/run_loop.py)).

The Claude Code docs say it directly: "Seeing a skill trigger tells you Claude found it, not that it did what you intended". So measure triggering and output quality separately ([skills](https://code.claude.com/docs/en/skills)). Codex likewise advises testing prompts against descriptions to check triggering. It documents a Skill Creator but, at the source fetched, no eval harness (**unverified** beyond that page; [Codex skills](https://learn.chatgpt.com/docs/build-skills)).

**General eval hygiene** ([Anthropic, "Demystifying evals"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), Jan 2026):
- Start from "20-50 simple tasks drawn from real failures". The capture log is exactly this source.
- Report pass^k (all k trials succeed) for reliability, alongside pass@k.
- "Grade what the agent produced, not the path it took."
- "read the transcripts" to validate graders.
- Watch for saturation.

**Human approval gate.** skill-creator's loop ends in a viewer with a per-case feedback box, written out as `feedback.json`, and repeats "until user is satisfied" ([skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)). agentskills.io argues human review catches output that is "technically correct but misses the point" ([agentskills.io](https://agentskills.io/skill-creation/evaluating-skills)). OpenAI's loop escalates to a human when `MAX_OPTIMIZATION_RETRIES = 3` is exhausted ([OpenAI cookbook](https://developers.openai.com/cookbook/examples/partners/self_evolving_agents/autonomous_agent_retraining)).

**Test across models.** A skill tuned for Opus may under-specify for Haiku ([best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)).

## 4. Safety and failure modes

- **Reward or objective hacking.** DGM node 114 reached a perfect hallucination score after two modifications. It got there by removing the logging of special tool-use tokens "despite instructions not to change the special tokens". The hacking was found by inspecting the lineage in the archive. Hiding the checker reduced it ([DGM](https://arxiv.org/html/2505.22954)). *Mitigation:* the proposer must not be able to read or write graders or eval fixtures. Keep evals in a path the editing agent cannot modify.
- **Drift from self-feedback.** Self-feedback loops drift. External feedback over multiple iterations produces "genuine improvement". Methods help on "clear, reusable workflows" and struggle on open-ended tasks. Stronger backbones do not reliably produce better skills ([SkillLearnBench](https://arxiv.org/abs/2604.20087)). *Mitigation:* never gate on the proposer's own judgment.
- **Collapse and bloat.** Collapse is the rewrite failure described in §2 ([ACE](https://arxiv.org/html/2510.04618)). Bloat is the opposite failure: 16 of 84 SkillsBench tasks got *worse* with curated skills, and focused skills beat comprehensive ones ([SkillsBench](https://arxiv.org/abs/2602.12670)). Skills also compete for context, "a public good" ([best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)). *Mitigation:* track helpful/harmful counts, prune at zero, enforce a size budget, and report token/time overhead next to the pass-rate gain ([skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)).
- **Overfitting to one session or to the eval set.** Keep a held-out split and select on it ([run_loop.py](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/run_loop.py)). OpenAI's cookbook calls out the overfitting risk of a static metaprompt loop. It prefers GEPA with separate train and validation sets, and promotes the version with the best *aggregate* score across the dataset, not the best single case ([OpenAI cookbook](https://developers.openai.com/cookbook/examples/partners/self_evolving_agents/autonomous_agent_retraining)).
- **Path dependence.** In SICA, poor early ideas locked in weak trajectories, and "truly novel" modifications were hard to get ([SICA](https://arxiv.org/html/2504.15228)). DGM counters this by sampling parents from an archive, not only from the latest version ([DGM](https://arxiv.org/html/2505.22954)).
- **Runaway runs.** SICA runs an asynchronous overseer LLM that checks every 30 s for "pathological behaviours" and can cancel the run ([SICA](https://arxiv.org/html/2504.15228)). DGM ran with sandboxing and human oversight ([DGM](https://arxiv.org/abs/2505.22954)).
- **Supply chain.** Skills carry both instructions and code. Anthropic recommends installing skills only "from trusted sources" and auditing them ([Anthropic engineering](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)). A self-editing loop is a new writer to that code path. `claude plugin eval` refuses Bash runs when no OS sandbox is available ([plugin evals](https://code.claude.com/docs/en/plugin-evals)).
- **Rollback.** OpenAI's `VersionedPrompt` records the text, model, timestamp and eval/run IDs for each version so it can roll back ([OpenAI cookbook](https://developers.openai.com/cookbook/examples/partners/self_evolving_agents/autonomous_agent_retraining)). For file-based skills, git provides the same thing: one commit per accepted delta, with the benchmark output in the commit message or PR. Pin `--model` so a regression can be attributed to the edit and not to a model change ([plugin evals](https://code.claude.com/docs/en/plugin-evals)).

## 5. Cadence and cost

**Per session:** deterministic capture only. Hooks append to the log at no model cost ([hooks](https://code.claude.com/docs/en/hooks)).

**Periodic batch:** reflect, curate, and eval. Evaluation is the expensive step:
- A plugin eval suite makes about cases × runs agent runs, twice over for the baseline arm, plus three judge calls per `llm` or `baseline` grader per run. Their example: one case, 6 runs, $0.41 ([plugin evals](https://code.claude.com/docs/en/plugin-evals)).
- A description-optimization pass is 20 queries × 3 runs × up to 5 iterations ([run_loop.py](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/run_loop.py)).
- For comparison, a full DGM run on SWE-bench "takes about 2 weeks and incurs significant API costs" ([DGM](https://arxiv.org/html/2505.22954)). Whole-agent self-modification costs orders of magnitude more than delta edits to skills.

**Cost levers:**
- Reflective text optimizers are sample-efficient: GEPA needs up to 35× fewer rollouts than GRPO and beats it by about 6% on average ([GEPA](https://arxiv.org/abs/2507.19457)).
- ACE's delta updates reduce adaptation latency and rollout cost ([ACE](https://arxiv.org/abs/2510.04618)).
- While iterating, run `--runs 1 --ablation none`, then confirm at full runs before landing ([plugin evals](https://code.claude.com/docs/en/plugin-evals)).

**Suggested trigger:** batch-distill a skill when its log has recurring friction across several distinct sessions, not after every session. Also re-run its regression suite when the model changes ([plugin evals](https://code.claude.com/docs/en/plugin-evals)). The threshold for "recurring" is a judgment call; no source here prescribes one (**unverified**).

## Sources

- Anthropic, Skill authoring best practices: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Anthropic Engineering, Equipping agents for the real world with Agent Skills (2025-10-16): https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Anthropic Engineering, Demystifying evals for AI agents (2026-01-09): https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- Anthropic skill-creator SKILL.md: https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md
- Anthropic skill-creator `run_loop.py`: https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/run_loop.py
- Agent Skills, Evaluating skill output quality: https://agentskills.io/skill-creation/evaluating-skills
- Claude Code docs, Skills: https://code.claude.com/docs/en/skills
- Claude Code docs, Test plugins with evals: https://code.claude.com/docs/en/plugin-evals
- Claude Code docs, Hooks: https://code.claude.com/docs/en/hooks
- OpenAI, Codex/ChatGPT skills docs: https://learn.chatgpt.com/docs/build-skills
- OpenAI Cookbook, Self-Evolving Agents: https://developers.openai.com/cookbook/examples/partners/self_evolving_agents/autonomous_agent_retraining
- Zhang et al., ACE: Agentic Context Engineering (ICLR 2026), arXiv:2510.04618: https://arxiv.org/abs/2510.04618
- Agrawal et al., GEPA (ICLR 2026), arXiv:2507.19457: https://arxiv.org/abs/2507.19457
- Zhang, Hu, Lu, Lange, Clune, Darwin Gödel Machine, arXiv:2505.22954: https://arxiv.org/abs/2505.22954
- Robeyns, Szummer, Aitchison, A Self-Improving Coding Agent (SICA), arXiv:2504.15228: https://arxiv.org/abs/2504.15228
- Wang et al., Voyager, arXiv:2305.16291: https://arxiv.org/abs/2305.16291
- Shinn et al., Reflexion, arXiv:2303.11366: https://arxiv.org/abs/2303.11366
- Zhao et al., ExpeL (AAAI-24), arXiv:2308.10144: https://arxiv.org/abs/2308.10144
- Wang, Mao, Fried, Neubig, Agent Workflow Memory, arXiv:2409.07429: https://arxiv.org/abs/2409.07429
- SkillsBench, arXiv:2602.12670: https://arxiv.org/abs/2602.12670
- Zhong et al., SkillLearnBench, arXiv:2604.20087: https://arxiv.org/abs/2604.20087
