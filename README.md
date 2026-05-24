# meta-foundries-overlay

Per-factory user layer for a Foundries.io factory build.

This layer holds the factory-specific image recipe, the kas entrypoint
(`kas/factory.yml`), and the `factory-config.yml` that Foundries CI
consumes. It depends on `meta-foundries` (product layer) plus a BSP layer
plus a distro variant (for example, `meta-qcom` + `meta-qcom-distro` for
Qualcomm boards).

Replaces the legacy `meta-subscriber-overrides` naming for the
agentic-and-later factory generation.

## Layer composition

```
       meta-foundries          <- product layer (sibling repo)
              |
       meta-foundries-overlay  <- this layer (per factory)
```

## CI

`kas/factory.yml` is the canonical entrypoint. It includes layer plumbing
from `meta-foundries` via `header.includes:` and adds this overlay on top.
Foundries CI invokes:

```
kas-container build kas/factory.yml
```

## Layer compatibility

```
LAYERSERIES_COMPAT = "wrynose"
LAYERDEPENDS       = "meta-foundries"
```

## Branches

- `main`: per-factory development branch.

## License

Apache-2.0; see `LICENSE`.
