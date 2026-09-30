"""Real-time voice for the duty analyst: a WebSocket bridge between the officer's microphone and Gemini Live.

The browser streams 16 kHz PCM from the microphone; this service relays it to a Gemini Live session on Vertex AI and
streams the spoken answer (24 kHz PCM), both transcripts and interruptions back. Gemini's tool calls are answered
here from the scenario held in memory, so every number it speaks comes from ShadowCast's model, never from Gemini.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta
from typing import Any, Protocol

from fastapi import WebSocket, WebSocketDisconnect
from google.genai import types

from shadowcast_geo.models import Asset, ScenarioDetail

logger = logging.getLogger(__name__)

LIVE_MODEL = "gemini-live-2.5-flash-native-audio"
INPUT_MIME = "audio/pcm;rate=16000"
IST = timedelta(hours=5, minutes=30)
LANGUAGES = {"en": "English", "hi": "Hindi", "or": "Odia", "te": "Telugu", "bn": "Bengali", "ta": "Tamil"}
TOOL_FIELDS = (
    "rank", "name", "kind", "district", "p_outage", "peak_wind_kt", "min_dist_km", "gale_arrival", "population",
    "rain_mm", "observed_rain_mm", "surge_m", "flood_m", "access_road", "access_closes", "p34", "p64", "reasons",
)  # fmt: skip
TIME_FIELDS = ("gale_arrival", "access_closes")

Search = Callable[[dict[str, Any]], dict[str, Any]]


class LiveSession(Protocol):
    """The parts of a Gemini Live session the bridge uses."""

    async def send_realtime_input(self, *, audio: types.Blob) -> None:
        """Send a chunk of microphone audio."""
        ...

    async def send_tool_response(self, *, function_responses: list[types.FunctionResponse]) -> None:
        """Answer Gemini's tool calls."""
        ...

    def receive(self) -> AsyncIterator[types.LiveServerMessage]:
        """Messages from Gemini for the current turn."""
        ...


def ist(iso: str | None) -> str | None:
    """Render an ISO 8601 UTC time as IST for speaking, e.g. ``2 May 16:30 IST``.

    Args:
        iso: ISO 8601 time, or None.

    Returns:
        str | None: The IST time, or None when there is none.
    """
    if not iso:
        return None
    local = datetime.fromisoformat(iso.replace("Z", "+00:00")) + IST
    return f"{local.day} {local:%b %H:%M} IST"


def tool_asset(asset: Asset) -> dict[str, Any]:
    """The fields of one asset Gemini may quote, with times converted to IST.

    Args:
        asset: Ranked asset (best track or forecast).

    Returns:
        dict[str, Any]: Compact record for the tool response.
    """
    record = asset.model_dump(include=set(TOOL_FIELDS), exclude_none=True)
    for field in TIME_FIELDS:
        if field in record:
            record[field] = ist(record[field])
    return record


def instructions(detail: ScenarioDetail, issued: str | None, asset: Asset | None, language: str | None) -> str:
    """The system instruction for one voice call.

    Args:
        detail: Scenario being replayed.
        issued: Issue time of the forecast being replayed, or None for the best track.
        asset: Asset the officer selected on the map, if any.
        language: Code of the language the officer chose for replies (see ``LANGUAGES``), or None.

    Returns:
        str: Instruction text.
    """
    replay = f"the ECMWF ensemble forecast issued {ist(issued)}" if issued else "the observed best track, in hindsight"
    selected = (
        f'The officer has selected "{asset.name or asset.asset_id}" on the map; "this site" means it.' if asset else ""
    )
    speak_in = (
        f"Always reply in {LANGUAGES[language]}, whatever language the officer speaks."
        if language
        else "Reply in the language the officer speaks: English, Hindi, Odia, Telugu, Bengali or Tamil."
    )
    return f"""You are ShadowCast's duty analyst on a live voice call with a district emergency officer on the \
{detail.region.name}, India.
Storm: {detail.storm} {detail.season}, landfall {ist(detail.landfall)}. The officer is replaying {replay}. This is an \
exercise on a past storm.
{selected}
Rules:
- Every number, name and time you say must come from search_assets. Never estimate. If it has no answer, say so.
- Speak briefly, in two or three short sentences, like a colleague on the radio. Give times in IST.
- {speak_in}
- You cannot issue advisories on a call. To draft one for approval, the officer uses the chat.
- IMD and OSDMA remain the authority for warnings."""


def search_tool(kinds: list[str]) -> types.Tool:
    """The one tool Gemini gets on a call: look up ranked assets.

    Args:
        kinds: Asset kinds present in the scenario.

    Returns:
        types.Tool: The tool declaration.
    """
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="search_assets",
                description="Assets in priority order, optionally filtered by part of the name and by kind. Each has "
                "its rank, outage probability, peak wind, gale arrival, population, rain, surge and access road.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "query": types.Schema(type=types.Type.STRING, description="Part of the asset's name"),
                        "kinds": types.Schema(
                            type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING, enum=kinds)
                        ),
                        "limit": types.Schema(type=types.Type.INTEGER, description="How many, 1 to 10"),
                    },
                ),
            )
        ]
    )


def live_config(detail: ScenarioDetail, issued: str | None, asset: Asset | None, language: str | None) -> Any:
    """Configure a Gemini Live session: spoken answers, both transcripts and the asset search tool.

    Args:
        detail: Scenario being replayed.
        issued: Issue time of the forecast being replayed, or None for the best track.
        asset: Asset selected on the map, if any.
        language: Reply language code, or None to follow the officer.

    Returns:
        types.LiveConnectConfig: The session configuration.
    """
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=instructions(detail, issued, asset, language),
        tools=[search_tool(sorted(detail.asset_counts))],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore"))
        ),
    )


def run_tool(search: Search, call: types.FunctionCall) -> dict[str, Any]:
    """Answer one of Gemini's tool calls; a bad argument becomes an error Gemini can read, not a dropped call.

    Args:
        search: Asset search over the replay being viewed.
        call: The function call.

    Returns:
        dict[str, Any]: The tool result, or ``{"error": ...}``.
    """
    if call.name != "search_assets":
        return {"error": f"unknown tool {call.name}"}
    try:
        return search(dict(call.args or {}))
    except (ValueError, TypeError) as error:
        return {"error": str(error)[:300]}


async def listen(websocket: WebSocket, session: LiveSession) -> None:
    """Relay the officer's microphone (binary 16 kHz PCM frames) to Gemini until they hang up.

    Args:
        websocket: The browser's socket.
        session: The Gemini Live session.

    Raises:
        WebSocketDisconnect: When the officer hangs up.
    """
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))
        if message.get("bytes"):
            await session.send_realtime_input(audio=types.Blob(data=message["bytes"], mime_type=INPUT_MIME))


async def speak(websocket: WebSocket, session: LiveSession, search: Search) -> None:
    """Relay Gemini's spoken answer, transcripts and interruptions to the browser, answering tool calls on the way.

    Returns when Gemini closes the session (a turn that yields nothing).

    Args:
        websocket: The browser's socket.
        session: The Gemini Live session.
        search: Asset search over the replay being viewed.
    """
    while True:
        received = False
        async for message in session.receive():
            received = True
            if message.tool_call:
                calls = message.tool_call.function_calls or []
                for call in calls:
                    await websocket.send_json({"type": "tool", "name": call.name})
                await session.send_tool_response(
                    function_responses=[
                        types.FunctionResponse(id=call.id, name=call.name, response=run_tool(search, call))
                        for call in calls
                    ]
                )
            content = message.server_content
            if content is None:
                continue
            if content.interrupted:
                await websocket.send_json({"type": "interrupted"})
            for role, transcript in (("user", content.input_transcription), ("model", content.output_transcription)):
                if transcript and transcript.text:
                    await websocket.send_json({"type": "transcript", "role": role, "text": transcript.text})
            for part in (content.model_turn.parts if content.model_turn else None) or []:
                if part.inline_data and part.inline_data.data:
                    await websocket.send_bytes(part.inline_data.data)
            if content.turn_complete:
                await websocket.send_json({"type": "turn"})
        if not received:
            return


async def relay(websocket: WebSocket, client: Any, config: Any, search: Search, max_s: float) -> None:
    """Run one call: connect to Gemini Live, then relay both ways until either side ends or ``max_s`` passes.

    The browser gets ``{"type": "ready"}`` once Gemini is listening and ``{"type": "end", "reason": ...}`` before the
    socket closes, unless the officer hung up first.

    Args:
        websocket: The browser's socket (already accepted).
        client: ``google.genai.Client`` configured for Vertex AI.
        config: Session configuration from ``live_config``.
        search: Asset search over the replay being viewed.
        max_s: Longest call allowed, in seconds.
    """
    reason = "call ended"
    try:
        async with asyncio.timeout(max_s), client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
            await websocket.send_json({"type": "ready"})
            tasks = {
                asyncio.create_task(listen(websocket, session)),
                asyncio.create_task(speak(websocket, session, search)),
            }
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
    except WebSocketDisconnect:
        return
    except TimeoutError:
        reason = "time limit reached"
    except Exception:  # any Live failure must still close the officer's call cleanly
        logger.exception("voice call failed")
        reason = "voice call failed"
    with contextlib.suppress(RuntimeError, WebSocketDisconnect):
        await websocket.send_json({"type": "end", "reason": reason})
        await websocket.close()
