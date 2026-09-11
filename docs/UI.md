# Browser UI

Milestone 10 adds a same-origin browser client served by the FastAPI process. It is deliberately a presentation layer over the Milestone 9 HTTP contract, not a browser-side game engine.

## Run

```bash
emergent-rpg-api --db emergent-rpg.db --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`; the root redirects to `/ui/`.

The client has no Node/build step and no external assets. `index.html`, `app.js`, and `styles.css` live inside the `emergent_rpg` package tree and are served by FastAPI `StaticFiles`.

## Capabilities

The browser can:

- create a new persisted session;
- load a session by id, including the last id stored in local browser storage;
- render the player-visible location/time, exits, visible items/NPCs, inventory, and known facts;
- render bounded session history;
- submit raw player commands through `POST /sessions/{id}/actions`;
- show loading/connected state;
- distinguish deterministically rejected actions from transport/provider failures.

All world mutations still occur behind the existing Web API and `GameEngine.process_text()` path.

## Authority boundary

```text
browser DOM
→ same-origin fetch()
→ Milestone 9 Web API
→ GameEngine
→ parser / resolver / typed events / validators
→ persistence / replay
→ player-visible response projection
→ browser rendering
```

The JavaScript never imports engine internals, reads SQLite, constructs domain events, or attempts to reconstruct raw `WorldState`. It receives only the already-bounded API projection. Rendering uses DOM `textContent` for world/player data rather than injecting returned strings as HTML.

The session id in `localStorage` is only a convenience pointer for a single-user local deployment; it is not an authentication mechanism. Authentication/multi-user isolation remain future server concerns.

## Error behavior

`setBusy()` disables conflicting controls while a request is active and updates `aria-busy`/connection state. HTTP/API failures are shown in the alert banner. A resolver-rejected action still returns its unchanged player state and reason; the UI refreshes history and renders the rejection rather than treating it as a successful mutation.

## Packaging evidence

The Hatch wheel target already packages the complete `src/emergent_rpg` package tree, including the static directory. CI does not assume that this continues to work: it builds a standard wheel and opens the archive to assert these exact distribution paths exist:

- `emergent_rpg/web/static/index.html`
- `emergent_rpg/web/static/app.js`
- `emergent_rpg/web/static/styles.css`

This prevents a source-checkout-only UI from being mistaken for an installable feature. An earlier redundant `force-include` experiment was rejected by the wheel builder because the same static files were already included through the package target; the final configuration keeps one inclusion path plus an executable archive check.

## Verification

`tests/test_web_ui.py` verifies root routing, static asset serving, absence of known hidden-world content in shipped assets, the create-session/action/history API workflow consumed by the UI, and rejected-action state preservation. The broader API tests continue to cover provider-failure transaction atomicity and the player-visible knowledge boundary.
