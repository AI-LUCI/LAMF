# Blueprints

Three architecture blueprints, each with an editable Graphviz source and a rendered
SVG:

| blueprint | source | rendered | normative text |
|---|---|---|---|
| Retrieval pipeline (11 stages) | `blueprints/retrieval_pipeline.dot` | `blueprints/retrieval_pipeline.svg` | `04_STORAGE/INDEXING_AND_SEARCH.md` |
| OpenClaw integration | `blueprints/openclaw_integration.dot` | `blueprints/openclaw_integration.svg` | `05_INTEGRATIONS/OPENCLAW_INTEGRATION.md` |
| Portable restore (import order per DECISIONS section M) | `blueprints/portable_restore.dot` | `blueprints/portable_restore.svg` | `07_PORTABILITY/PORTABILITY_AND_TRANSFER.md` |

## Provenance

The SVGs originate from the v1 package and are copied as-is. The `.dot` files are
new editable sources written during the v2.0.0 reconditioning: they reproduce the v1
node labels and flow, updated where DECISIONS changed the flow (the portable-restore
import sequence now follows DECISIONS section M exactly; the retrieval pipeline keeps
its 11 stages; the OpenClaw diagram is unchanged). Where a `.dot` and its `.svg`
disagree, the `.dot` is current — re-render to reconcile.

## Re-rendering

Requires Graphviz (`dot`):

```text
dot -Tsvg retrieval_pipeline.dot > retrieval_pipeline.svg
dot -Tsvg openclaw_integration.dot > openclaw_integration.svg
dot -Tsvg portable_restore.dot > portable_restore.svg
```

The inventory is three blueprints with editable sources — no other diagrams are part
of this package (see `DECISIONS.md` section B).
