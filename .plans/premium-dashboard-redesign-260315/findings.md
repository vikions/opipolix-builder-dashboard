# Findings & Decisions

## Requirements
- Make the current site visually stronger, more beautiful, and more premium.
- Do not change the way data is fetched.
- Visual changes can include layout changes, table relocation, and overall UI upgrades.
- `react-bits` in the repo root may be used as a source of design ideas or reusable pieces if practical.

## Research Findings
- The frontend appears to live entirely in `index.html` with inline CSS and JS.
- The backend logic is isolated in `api/stats.py`, which aligns well with the user's request to leave data fetching untouched.
- Current design already has cards, charts, and tables, but uses a generic gradient/card dashboard pattern and default system typography.
- The referenced `react-bits` directory is not present at the repo root in the current workspace.
- The latest Vercel web interface guidelines emphasize semantic structure, visible focus states, avoiding `transition: all`, better number/date formatting via `Intl`, and motion that respects reduced-motion preferences.
- The current frontend can absorb a major visual upgrade without changing architecture because all presentation logic is centralized in one file.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Treat redesign as a static-frontend refactor | Minimizes risk to working data flow |
| Preserve `load()` fetch contract and rendering pipeline semantics | Keeps backend/data behavior stable |
| Use the design guidelines as constraints, not as a reason to add framework complexity | Current app is plain HTML/JS, so direct, compliant improvements are lower risk |
| Use Google Fonts (`Fraunces` + `Manrope`) and a premium editorial layout | Stronger brand feel without requiring a framework migration |
| Reorganize the dashboard into hero, performance, insights, charts, and ledger sections | Improves hierarchy and perceived polish while preserving the same data content |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| README references `public/index.html`, but repo currently uses root `index.html` | Use actual repo structure, not README wording |
| `react-bits` folder was expected by user but not found in workspace root | Search alternate locations; if absent, continue with custom visual implementation |
| One-shot `apply_patch` rewrite was rejected | Rebuilt `index.html` in smaller patches |

## Resources
- `C:\Users\plamb\liderboard\opipolix-builder-dashboard\index.html`
- `C:\Users\plamb\liderboard\opipolix-builder-dashboard\api\stats.py`
- `C:\Users\plamb\liderboard\opipolix-builder-dashboard\README.md`
- `https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md`

## Visual/Browser Findings
- Current UI uses a purple-blue full-page gradient, white cards, and default dashboard styling.
- Header, stat blocks, chart area, and tables are visually separated but not strongly art-directed.
- The interface likely benefits from stronger visual hierarchy, richer surfaces, better table containers, and a more intentional hero/header treatment.
- Guideline-sensitive items already visible in current UI include `transition: all`, lack of reduced-motion handling, and room for more semantic layout structure.
- Final redesign direction: premium editorial dashboard with a warm light canvas, dark hero/chart panels, serif display typography, and glassy ledger panels.
