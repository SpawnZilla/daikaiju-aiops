# Kaidosho — Documentation Site (local scaffold)

**Status: NOT deployed anywhere public.** This is a locally buildable
and previewable MkDocs site, built 2026-09-24.

Trademark-safe naming DECIDED 2026-09-24: brand = Kaidosho (umbrella),
Daikaiju AIOps stays as the product name underneath it. Agent names:
Mokaima, Bakaidah and Angkai. Applied
throughout this site's content.

Still outside this scaffold's scope: where this actually deploys to
(GitHub Pages, a subdomain, etc.) — depends on the public repo's own
readiness.

## Building and previewing locally

```
python3 -m venv .venv
source .venv/bin/activate
pip install mkdocs
mkdocs serve
```

Then open http://127.0.0.1:8000 in a browser. `mkdocs build` produces
a static `site/` directory if a one-off build is wanted instead of the
live-reloading dev server.

## Content sources

Adapted from `Daikaiju_AIOps.md`, `Kaiju_GAIS.md`, and `Kaiju_Spine.md`
with internal file paths, ticket
numbers, and incident history stripped per the same "portable framing"
standard `MABS_Standalone.md` already uses internally.
