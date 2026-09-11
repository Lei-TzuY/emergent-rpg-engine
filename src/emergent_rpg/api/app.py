from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from emergent_rpg.api.models import (
    ActionRequest,
    ActionView,
    HistoryTurnView,
    HistoryView,
    SessionCreateRequest,
    SessionView,
    project_player_state,
)
from emergent_rpg.engine.service import GameEngine, TransitionRejected
from emergent_rpg.persistence.db import SQLiteStore
from emergent_rpg.providers.errors import ProviderError
from emergent_rpg.providers.factory import (
    ActionParserName,
    NarrativeProviderName,
    build_action_parser,
    build_narrative_generator,
)
from emergent_rpg.providers.openai_compatible import JsonTransport


def create_app(
    db_path: str | Path = "emergent-rpg.db",
    narrative_provider: NarrativeProviderName | str = NarrativeProviderName.SCRIPTED,
    action_parser: ActionParserName | str = ActionParserName.DETERMINISTIC,
    *,
    env: Mapping[str, str] | None = None,
    transport: JsonTransport | None = None,
) -> FastAPI:
    store = SQLiteStore(db_path)
    generator = build_narrative_generator(narrative_provider, env=env, transport=transport)
    parser = build_action_parser(action_parser, env=env, transport=transport)
    engine = GameEngine(store, generator=generator, parser=parser)

    app = FastAPI(title="emergent-rpg-engine", version="0.1.0")
    static_dir = Path(__file__).resolve().parent.parent / "web" / "static"
    app.mount("/ui", StaticFiles(directory=static_dir, html=True), name="ui")

    @app.get("/", include_in_schema=False)
    def browser_root() -> RedirectResponse:
        return RedirectResponse(url="/ui/")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/sessions", response_model=SessionView, status_code=status.HTTP_201_CREATED)
    def create_session(request: SessionCreateRequest) -> SessionView:
        try:
            session = engine.new_session(request.name)
            state = store.load_state(session.id)
        except TransitionRejected as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return SessionView(session=session, state=project_player_state(state))

    @app.get("/sessions/{session_id}", response_model=SessionView)
    def get_session(session_id: str) -> SessionView:
        try:
            session = store.get_session(session_id)
            state = store.load_state(session_id)
        except KeyError as exc:
            raise _not_found(session_id, exc) from exc
        return SessionView(session=session, state=project_player_state(state))

    @app.get("/sessions/{session_id}/history", response_model=HistoryView)
    def get_history(
        session_id: str,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> HistoryView:
        try:
            store.get_session(session_id)
            turns = store.list_turns(session_id, limit=limit)
        except KeyError as exc:
            raise _not_found(session_id, exc) from exc
        return HistoryView(
            turns=[
                HistoryTurnView(
                    turn_number=turn.turn_number,
                    raw_input=turn.raw_input,
                    accepted=turn.accepted,
                    reason=turn.reason,
                    narration=turn.narration,
                    location_id=turn.location_id,
                )
                for turn in turns
            ]
        )

    @app.post("/sessions/{session_id}/actions", response_model=ActionView)
    def submit_action(session_id: str, request: ActionRequest) -> ActionView:
        try:
            result, narration, state = engine.process_text(session_id, request.text)
        except KeyError as exc:
            raise _not_found(session_id, exc) from exc
        except ProviderError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        except TransitionRejected as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return ActionView(
            accepted=result.accepted,
            reason=result.reason,
            narration=narration,
            state=project_player_state(state),
        )

    return app


def _not_found(session_id: str, exc: KeyError) -> HTTPException:
    del exc
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"unknown session {session_id}",
    )
