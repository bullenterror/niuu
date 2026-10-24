# Resident Learning Consolidation

A resident learns from its own sessions without anyone editing its persona.
After every session, post-session reflection records one candidate lesson.
This page covers how candidates become promoted, in-prompt learnings: matching
by meaning, evidence-weighted promotion, the curation pass in the
consolidation dream, and the injection budget.

## Why

Regin found the same lesson four times on 2026-10-23/24 and kept none of
them: "Use github.com/.diff when api.github.com checks return 403", "Probe
distinct hosts before declaring a capability gap", "Test alternate GitHub web
routes before declaring a read-route capability gap". Word-overlap matching
saw three unrelated candidates, each with one observation. None reached the
three observations needed for promotion. An older candidate, "all routes 403",
contradicted them and was never resolved. Candidates are never injected, so
the next turn still reported that it could not inspect the patch.

## What happens now

1. **Matching by meaning** (`reflection.matching.mode: semantic`). A new
   candidate is compared with the recorded lessons by embedding similarity.
   The closest lessons above `similarity_threshold` (at most `max_related`)
   go to a small judge model, which answers "is this the same lesson?". On a
   match, the new observation is added to the existing candidate: its session,
   its evidence note, and its wording under `## Related observations`. If the
   match is a promoted learning, the learning gets a `last_confirmed` date
   instead. An evidence note that embeds at or above
   `evidence_duplicate_similarity` against one already recorded counts as the
   same fact read twice, not a second observation.
2. **Evidence-weighted promotion**. The agent puts *route recoveries* on
   `ravn.session.ended`. A route recovery is a tool call that failed, followed
   in the same turn by a successful call to the same tool with different
   input. These come from the tool results, not from the model. When the
   reflection says a lesson restates one of them (`verified_by_recovery`), the
   candidate is marked `verified: true`, gets a `## Verification` section, and
   promotes on its first observation (reason `verified_route_recovery`). Set
   `verified_promotion.route_recovery_promotes: false` to turn this off.
   Speculative lessons still need `candidate_min_repetitions` observations.
3. **Curation in the consolidation dream** (`reflection.curation.enabled`).
   This runs at most once every `min_interval_seconds`. It judges up to
   `max_judgments` similar lesson pairs, then:
   - **merges** the lessons the judge calls the same. The survivor is a
     promoted learning if there is one, otherwise the lesson with the
     strongest evidence. If the merged evidence is enough, the survivor
     promotes.
   - **supersedes** one side of a contradiction. The stronger side stands. In
     order, strength is verified evidence, then being a promoted learning,
     then more observations, then newer evidence.
   - **prunes** candidates seen once, never verified, and not confirmed again
     within `prune_after_days`.
   - **rewrites** up to `max_rewrites` promoted learnings into a short
     `When X, do Y.` rule in a `## Procedure` section.

   Nothing is deleted. A retired page keeps its content and gets `status:
   merged|superseded|pruned`, a `merged_into` or `superseded_by` field, and a
   `curation_reason`. Every pass that changes anything writes an audit page
   under `learning-curation/`. Learnings under `learnings/{environment,domain,
   flock,shared,private}/` belong to cross-scope promotion and are never
   rewritten here.
4. **Injection**. At session start, active learnings go into the prompt.
   Merged, superseded and pruned learnings are skipped. With semantic matching
   on, learnings are ranked by similarity to the first input; otherwise the
   most recently updated or confirmed come first. A learning with a procedure
   is injected as its rule. Any other learning is injected as its claim,
   capped at `learning_entry_max_chars`, all within `learning_token_budget`
   and `max_learnings_injected`.

## Configuration

```yaml
embedding:            # required by semantic matching and curation
  enabled: true
  adapter: ravn.adapters.embedding.openai.OpenAIEmbeddingAdapter
  kwargs: {base_url: https://…/v1, model: Qwen/Qwen3-Embedding-0.6B}

reflection:
  enabled: true
  llm_alias: Qwen/Qwen3.8-27B
  candidate_min_repetitions: 3
  learning_token_budget: 500
  max_learnings_injected: 5
  learning_entry_max_chars: 600
  matching:
    mode: semantic                    # lexical | semantic
    similarity_threshold: 0.75
    max_related: 5
    embed_batch_size: 64
    evidence_duplicate_similarity: 0.9
    judge_llm_alias: ""               # empty = reflection.llm_alias
    judge_max_tokens: 512
    judge_attempts: 2
  verified_promotion:
    route_recovery_promotes: true
    max_route_recoveries: 5
    excerpt_chars: 240
  curation:
    enabled: true                     # needs resident_wakefulness.enabled
    min_interval_seconds: 86400
    max_judgments: 40
    max_rewrites: 10
    procedure_max_chars: 280
    prune_after_days: 14
    audit_prefix: learning-curation

resident_wakefulness:
  enabled: true
```

These are startup errors, never a silent fall back to lexical matching:

- `matching.mode: semantic` or `curation.enabled: true` without
  `embedding.enabled: true`;
- either one on a runtime with no native LLM for the judge;
- `curation.enabled: true` when resident wakefulness is not running.

When the judge returns malformed output after `judge_attempts` tries, the
reflection or curation pass raises instead of recording a duplicate. A failed
curation pass still writes its audit page, with an `## Error` section, before
it raises.

## Backfilling existing candidates

Candidates recorded before this existed are consolidated by curation. The
dream pass judges `max_judgments` pairs per run, so a resident with hundreds
of candidates (Regin had 214) would take many dreams to work through them.
Run the backfill once instead, inside the resident pod, after deploying with
`matching.mode: semantic` and `curation.enabled: true`:

```bash
KUBECONFIG=~/.kube/kubeconfigs/valhalla.yaml kubectl -n nats exec deploy/regin -c ravn -- ravn learnings-curate --max-judgments 1000
```

The command runs the same pass the dream runs and prints counts for reviewed,
judged, merged, superseded, pruned, promoted and rewritten lessons. The audit
page under `learning-curation/` lists every change and its reason. It is safe
to rerun: retired lessons are not judged again. Run it once more if the first
run used its whole judgment budget (`pairs_judged` equal to
`--max-judgments`). Use `--max-rewrites 0` to consolidate without the
procedural rewrites.

Before trusting the result, check the audit page for supersessions. Each line
says which evidence decided the contradiction.
