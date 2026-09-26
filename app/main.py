"""FastAPI 入口。"""
from fastapi import FastAPI, HTTPException

from .models import ParseRequest, ParseResponse
from .parser import ParseError, parse_events

app = FastAPI(
    title="MIDI Sustain Parser",
    description="解析 note_on / note_off / pedal_down / pedal_up 事件，"
                "输出每次按键的发声半开区间与结束原因。",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/parse", response_model=ParseResponse)
def parse(req: ParseRequest) -> ParseResponse:
    try:
        notes = parse_events(req.end_ms, req.events)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ParseResponse(notes=notes)
