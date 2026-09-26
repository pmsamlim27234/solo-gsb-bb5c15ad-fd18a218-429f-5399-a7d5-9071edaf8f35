"""请求 / 响应数据模型。"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class EventType(str, Enum):
    NOTE_ON = "note_on"
    NOTE_OFF = "note_off"
    PEDAL_DOWN = "pedal_down"
    PEDAL_UP = "pedal_up"


class Event(BaseModel):
    """单个输入事件。note 事件必须带 pitch，踏板事件不需要。"""

    type: EventType
    time_ms: int = Field(ge=0, description="事件时间（毫秒），须在 0 ~ end_ms 之间")
    pitch: Optional[int] = Field(
        default=None, ge=0, le=127, description="MIDI 音高 0~127，仅 note 事件需要"
    )

    @model_validator(mode="after")
    def _pitch_required_for_notes(self) -> "Event":
        if self.type in (EventType.NOTE_ON, EventType.NOTE_OFF) and self.pitch is None:
            raise ValueError(f"pitch is required for {self.type.value} events")
        return self


class ParseRequest(BaseModel):
    end_ms: int = Field(ge=0, description="片段结束时间（毫秒），用于关闭所有仍未结束的音符")
    events: List[Event] = Field(default_factory=list)

    @model_validator(mode="after")
    def _times_within_end(self) -> "ParseRequest":
        for i, ev in enumerate(self.events):
            if ev.time_ms > self.end_ms:
                raise ValueError(
                    f"events[{i}].time_ms ({ev.time_ms}) exceeds end_ms ({self.end_ms})"
                )
        return self


class EndReason(str, Enum):
    NOTE_OFF = "note_off"    # 正常松键结束（踏板未按下）
    PEDAL_UP = "pedal_up"    # 踏板抬起，结束被延音的音符
    END_MS = "end_ms"        # 片段结束，强制关闭


class NoteResult(BaseModel):
    """一次按键的发声区间，半开区间 [start_ms, end_ms)。"""

    note_index: int = Field(description="按键序号，按下事件的处理顺序从 0 开始")
    pitch: int
    start_ms: int
    end_ms: int
    end_reason: EndReason


class ParseResponse(BaseModel):
    notes: List[NoteResult]
