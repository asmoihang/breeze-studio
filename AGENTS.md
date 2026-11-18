# Prototype Instructions

## Project constraints

- User selected the first off-white/teal three-column mock and its segmented narration editor.
- Production inference runs on a separate Windows PC inside WSL2, with an existing official Breeze TTS 2 installation and RTX 4070 Ti.
- Preserve the official repository, environment, model weights and inference precision. No quantization or audio enhancement.
- This machine hosts UI/API verification only. Never represent local tests as target GPU acceptance.
- Distribute built frontend and standard-library backend; target startup must not require Node.js or dependency upgrades.
- User prefers sweet young-adult female voices for tutorials. Offer clear, gentle and lively variants through the dedicated voice designer; do not overwrite existing project settings on upgrade.
- User requested a public GitHub repository. Never commit data/, recordings, outputs, model weights, environments or personal QA captures. Track dist/client together with frontend source for no-Node updates.

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.
