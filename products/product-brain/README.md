# Product Brain

Durable, cross-feature product truth for Gravton — written down so Claude (and any
engineer) can carry the product sense that today lives only in a few people's heads.

This is the context that gets loaded to **interrogate a thin PRD**: generate the
senior-level question set, resolve most questions without pinging the (async) product
owner, and only escalate the genuinely novel ones.

## What belongs here (and what does not)

**Belongs:** durable, cross-feature truth that is stable across features and reused
every time — the product mental model, how the modules actually behave, what our
metrics mean *as the code computes them*, and the accreted log of decisions we've
already settled.

**Does NOT belong:** feature intent. A PRD is transient, single-feature, point-in-time
— it is the thing the brain is used to *interrogate*, not a source to build the brain
from. We do not seed the brain from PRDs (that would inherit exactly the gaps we're
trying to cover). We only ever *harvest* the rare durable statement a document happens
to contain, and discard the feature-specific intent around it.

## Where the brain comes from (in priority order)

1. **Tacit knowledge, extracted** — the real ground truth lives with the engineering and
   product teams. Primary source. Captured by *correcting drafts*, not authoring from a
   blank page.
2. **Codebase reality** — how the modules actually branch, and how metrics/taxonomy are
   *actually computed* (grounded in `file:line`), not how a doc describes them.
3. **Stable external references** — outside-world facts the code can't tell you (e.g. how
   third-party AI answer engines behave, industry benchmarks). Add a file here only when
   such a reference earns its keep.
4. **Decision-log exhaust** — every product-intent decision the loop confirms accretes
   into `decision-log.md`. Over time this becomes most of the brain, and it shrinks how
   often the async owner has to be asked.

## Files

- `module-map.md` — the spine: every subsystem in the codebase (the Django apps, the
  Airflow DAG pipeline, the workspace members) and how they relate, so any feature can be
  located. The prompt-generation buyer archetypes are one leaf, in its appendix.
  *(grounded from code + architecture docs)*
- `glossary.md` — core metrics & taxonomy, defined as the code computes them, with
  `file:line`. *(grounded from code)*
- `decision-log.md` — settled product-intent decisions, one per entry. *(grows as exhaust)*

## Conventions (so it doesn't rot)

Every non-trivial entry carries a small header:

    > status: draft | confirmed
    > source: <code file:line | team | reference>
    > owner: engineering team | product team
    > confirmed: <date, when a human ratified it>

- `owner` is always a **team**, never a named person: **engineering team** for
  code-grounded truth (module map, glossary), **product team** for product-intent truth
  (decision log, external references).
- Drafts are machine-generated from code/refs and are **not truth until a human ratifies**.
- The owning team keeps its entries current; entries are corrected, never authored from scratch.
- When a loop decision is confirmed, append it to the decision log — that's the maintenance
  mechanism, not a periodic "update the docs" chore that nobody does.
