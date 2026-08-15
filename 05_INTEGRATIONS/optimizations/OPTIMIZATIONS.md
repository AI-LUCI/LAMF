# LAMF agent optimizations

Agent optimizations are optional instruction modules. They do not read, write,
index, migrate, or own durable memory. LAMF remains fully functional when the
optimization layer or every module is disabled.

## Controls

```text
lamf optimizations status
lamf optimizations on
lamf optimizations off
lamf optimizations enable MODULE_ID
lamf optimizations disable MODULE_ID
lamf optimizations doctor
```

Use `LAMF_OPTIMIZATIONS=off` as the global emergency override. Override one
module with `LAMF_OPTIMIZATION_<MODULE_ID>=off`, replacing hyphens with
underscores. Environment overrides do not rewrite instance configuration.

Configuration lives in `<data-dir>/optimizations.json`. Package modules live
under `05_INTEGRATIONS/optimizations/modules/`. Missing configuration uses safe
package defaults. Malformed configuration disables the optional layer. A
malformed module is quarantined while other valid modules continue to load.

## Module contract

Each module directory contains a JSON manifest, a compact instruction fragment,
a progressively disclosed skill, harness metadata, and provenance. Add one
behavior per module and never require one optimization from another. Validate
new modules with `lamf optimizations doctor`, the skill validator, the
optimization isolation test, the LAMF smoke suite, and package validation.

New candidates follow `discovery/DISCOVERY.md`. Each daily scan records the
sources inspected, adoption decision, interaction with existing modules,
portable fallback, and validation evidence in a dated report. Trend signals are
never installed directly and never override the module, credit, or safety gates.

Before adding or materially changing a module, update `Credit.md` at the package
root. Add or revise one entry per external influence using the ledger schema,
append its stable Credit ID to the module's provenance reference, and state
whether the module is a conceptual synthesis, adapted workflow, vendored code,
or evaluated-only boundary. A module is incomplete if its external influences
are not traceable from its provenance file to the living credit ledger.

## Codex desktop control panel

The Windows overlay is
`05_INTEGRATIONS/optimizations/overlay/Show-LAMFOptimizations.ps1`. It reads and
writes state only through the LAMF CLI. A personal Codex plugin can launch the
panel; the plugin is an adapter and is not an optimization or memory authority.
Codex does not expose a supported permanent-toolbar-button API, so the panel is
an always-on-top companion window and the plugin supplies in-app starter actions.
The launcher starts a compiled, single-instance Windows Forms controller with a
real notification-area message loop; repeated launches reuse the existing
controller rather than creating duplicate windows.
