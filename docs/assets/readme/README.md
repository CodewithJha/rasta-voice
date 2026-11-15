# README visuals

| File | Source |
| --- | --- |
| `logo.svg` | Product wordmark |
| `architecture.svg` | Diagram Design export from `diagrams/architecture.html` |
| `dispatch-desk.png` | Anatomy capture of `anatomy/dispatch-desk.html` |
| `anatomy/*.html` | Standalone interactive figure (kit inlined) |

Rebuild architecture:

```bash
python3 ~/.cursor/skills/diagram-design/scripts/export_svg.py \
  docs/assets/readme/diagrams/architecture.html \
  docs/assets/readme/architecture.svg --system-fonts
```

Rebuild desk (requires Anatomy skill on this machine):

```bash
cd docs/assets/readme/anatomy && node build.mjs && node build.mjs --light
node ~/.cursor/skills/anatomy/scripts/capture.mjs dispatch-desk.html \
  --out ../dispatch-desk.png
```
