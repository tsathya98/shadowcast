from typing import Any

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from google.genai import types

from shadowcast_geo.api import create_app
from shadowcast_geo.config import Settings
from shadowcast_geo.models import Asset, ScenarioDetail
from shadowcast_geo.voice import LIVE_MODEL, instructions, ist, live_config, run_tool, tool_asset
from tests.conftest import FakeLiveClient, FakeLiveSession, MemoryArtifacts, make_asset

ORIGIN = {"origin": "https://shadowcast.test"}
URL = "/scenarios/fani-2019/voice"


def app_client(store: MemoryArtifacts, live: FakeLiveClient, **settings: Any) -> TestClient:
    return TestClient(
        create_app(Settings(allowed_origins=("https://shadowcast.test",), **settings), store, store, live)
    )


def turn(**content: Any) -> types.LiveServerMessage:
    return types.LiveServerMessage(server_content=types.LiveServerContent(**content))


@pytest.mark.parametrize(("iso", "expected"), [(None, None), ("2019-05-02T11:00:00Z", "2 May 16:30 IST")])
def test_ist(iso: str | None, expected: str | None) -> None:
    assert ist(iso) == expected


def test_tool_asset_speaks_times_in_ist() -> None:
    asset = Asset.model_validate(
        {
            **make_asset("osm:node/1", 1, "hospital", 0.9, 86.0, "Puri Hospital"),
            "gale_arrival": "2019-05-02T11:00:00Z",
            "access_road": "NH316",
            "access_closes": "2019-05-02T22:45:00Z",
        }
    )
    record = tool_asset(asset)
    assert record["gale_arrival"] == "2 May 16:30 IST"
    assert record["access_closes"] == "3 May 04:15 IST"
    assert record["name"] == "Puri Hospital"
    assert "lat" not in record


@pytest.mark.parametrize(
    ("issued", "language", "expected"),
    [
        (None, None, ["observed best track", "language the officer speaks"]),
        ("2019-05-01T12:00:00Z", "or", ["forecast issued 1 May 17:30 IST", "Always reply in Odia"]),
    ],
)
def test_instructions(store: MemoryArtifacts, issued: str | None, language: str | None, expected: list[str]) -> None:
    detail = ScenarioDetail.model_validate(store.read_json("scenarios/fani-2019/scenario.json"))
    asset = Asset.model_validate(make_asset("osm:node/1", 1, "hospital", 0.9, 86.0, "Puri Hospital"))
    text = instructions(detail, issued, asset, language)
    assert all(fragment in text for fragment in expected)
    assert '"Puri Hospital"' in text
    config = live_config(detail, issued, None, language)
    assert config.response_modalities == [types.Modality.AUDIO]
    assert config.tools[0].function_declarations[0].name == "search_assets"


def test_run_tool() -> None:
    def search(args: dict[str, Any]) -> dict[str, Any]:
        if args.get("query") == "x":
            raise ValueError("query too short")
        return {"total": 1, "args": args}

    ok = run_tool(search, types.FunctionCall(name="search_assets", args={"query": "Puri"}))
    assert ok == {"total": 1, "args": {"query": "Puri"}}
    assert run_tool(search, types.FunctionCall(name="search_assets", args={"query": "x"})) == {
        "error": "query too short"
    }
    assert run_tool(search, types.FunctionCall(name="drop_tables")) == {"error": "unknown tool drop_tables"}


def test_voice_call_relays_audio_transcripts_and_tool_calls(store: MemoryArtifacts) -> None:
    audio = types.Part(inline_data=types.Blob(data=b"\x01\x02", mime_type="audio/pcm"))
    session = FakeLiveSession([
        [types.LiveServerMessage(tool_call=types.LiveServerToolCall(function_calls=[
            types.FunctionCall(id="c1", name="search_assets", args={"query": "Hospital", "limit": 3})]))],
        [types.LiveServerMessage(),
         turn(interrupted=True, input_transcription=types.Transcription(text="why first?"),
              output_transcription=types.Transcription(text="Highest risk."),
              model_turn=types.Content(parts=[audio]), turn_complete=True)],
    ])  # fmt: skip
    live = FakeLiveClient(session)
    url = f"{URL}?language=hi&asset=osm:node/1"
    with app_client(store, live) as client, client.websocket_connect(url, headers=ORIGIN) as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(b"\x00\x10")
        assert ws.receive_json() == {"type": "tool", "name": "search_assets"}
        assert ws.receive_json() == {"type": "interrupted"}
        assert ws.receive_json() == {"type": "transcript", "role": "user", "text": "why first?"}
        assert ws.receive_json() == {"type": "transcript", "role": "model", "text": "Highest risk."}
        assert ws.receive_bytes() == b"\x01\x02"
        assert ws.receive_json() == {"type": "turn"}
        assert ws.receive_json() == {"type": "end", "reason": "call ended"}
    assert session.audio == [b"\x00\x10"]
    result = session.tool_responses[0].response
    assert result["total"] == 1
    assert result["assets"][0]["name"] == "District Hospital Puri"
    model, config = live.configs[0]
    assert model == LIVE_MODEL
    assert "Always reply in Hindi" in config.system_instruction
    assert '"District Hospital Puri"' in config.system_instruction


def test_voice_call_on_a_forecast_replay(store: MemoryArtifacts) -> None:
    live = FakeLiveClient(FakeLiveSession([]))
    url = f"{URL}?forecast=20190501T12Z"
    with app_client(store, live) as client, client.websocket_connect(url, headers=ORIGIN) as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(b"\x00")
        assert ws.receive_json() == {"type": "end", "reason": "call ended"}
    assert "forecast issued 1 May 17:30 IST" in live.configs[0][1].system_instruction


@pytest.mark.parametrize(
    ("live", "settings", "reason"),
    [
        (FakeLiveClient(FakeLiveSession([], hang=True)), {"voice_call_s": 0.3}, "time limit reached"),
        (FakeLiveClient(error=RuntimeError("Vertex unavailable")), {}, "voice call failed"),
    ],
)
def test_voice_call_ends_cleanly(
    store: MemoryArtifacts, live: FakeLiveClient, settings: dict[str, Any], reason: str
) -> None:
    with app_client(store, live, **settings) as client, client.websocket_connect(URL, headers=ORIGIN) as ws:
        if live.error is None:
            assert ws.receive_json() == {"type": "ready"}
            ws.send_bytes(b"\x00")
        assert ws.receive_json() == {"type": "end", "reason": reason}


def test_officer_hangs_up(store: MemoryArtifacts) -> None:
    session = FakeLiveSession([], hang=True)
    with app_client(store, FakeLiveClient(session)) as client:
        with client.websocket_connect(URL, headers=ORIGIN) as ws:
            assert ws.receive_json() == {"type": "ready"}
            ws.send_bytes(b"\x00")
        assert session.audio == [b"\x00"]


@pytest.mark.parametrize(
    ("url", "headers", "settings", "code"),
    [
        (URL, {"origin": "https://evil.test"}, {}, 1008),
        ("/scenarios/nope/voice", ORIGIN, {}, 1008),
        (f"{URL}?forecast=19990101T00Z", ORIGIN, {}, 1008),
        (f"{URL}?language=xx", ORIGIN, {}, 1008),
        (URL, ORIGIN, {"voice_calls": 0}, 1013),
    ],
)
def test_voice_call_refused(
    store: MemoryArtifacts, url: str, headers: dict[str, str], settings: dict[str, Any], code: int
) -> None:
    with (
        app_client(store, FakeLiveClient(), **settings) as client,
        pytest.raises(WebSocketDisconnect) as refused,
        client.websocket_connect(url, headers=headers),
    ):
        pass
    assert refused.value.code == code


def test_creates_the_vertex_client_on_first_call(store: MemoryArtifacts, monkeypatch: pytest.MonkeyPatch) -> None:
    live = FakeLiveClient(FakeLiveSession([]))
    made: list[dict[str, Any]] = []

    def client_factory(**kwargs: Any) -> FakeLiveClient:
        made.append(kwargs)
        return live

    monkeypatch.setattr("shadowcast_geo.api.genai.Client", client_factory)
    with (
        TestClient(create_app(Settings(allowed_origins=("*",)), store, store)) as client,
        client.websocket_connect(URL) as ws,
    ):
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(b"\x00")
        assert ws.receive_json()["type"] == "end"
    assert made == [{"vertexai": True, "project": "argmax-cyclone-2026", "location": "us-central1"}]
