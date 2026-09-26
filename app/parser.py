"""延音踏板解析核心逻辑。

规则：
- 事件按 (time_ms, 输入序号) 排序处理，时间相同时保持输入先后。
- 同音高重复按下各成独立音符；note_off 释放该音高最早仍按住的一次。
- 踏板按下期间松键的音符继续发声（转入延音集合）。
- pedal_up 只结束这些被延音的音符；note_off 在踏板未按下时立即结束音符。
- 重复的踏板状态事件（已按下再 pedal_down / 已抬起再 pedal_up）不改变状态。
- end_ms 关闭所有剩余未结束的音符。
"""
from collections import defaultdict, deque
from typing import List

from .models import EndReason, Event, EventType, NoteResult


class ParseError(ValueError):
    """输入事件序列不合法（如 note_off 无对应按住音符）。"""


def parse_events(end_ms: int, events: List[Event]) -> List[NoteResult]:
    # 按时间及输入序号稳定排序
    ordered = sorted(enumerate(events), key=lambda p: (p[1].time_ms, p[0]))

    pedal_down = False
    held = defaultdict(deque)   # pitch -> 仍按住的音符（FIFO，队首为最早按下）
    sustained = []              # 踏板期间已松键、仍在发声的音符
    notes = []                  # 全部音符，按按键（处理）顺序记录

    for _, ev in ordered:
        if ev.type is EventType.NOTE_ON:
            rec = {
                "note_index": len(notes),
                "pitch": ev.pitch,
                "start_ms": ev.time_ms,
                "end_ms": None,
                "end_reason": None,
            }
            notes.append(rec)
            held[ev.pitch].append(rec)

        elif ev.type is EventType.NOTE_OFF:
            queue = held.get(ev.pitch)
            if not queue:
                raise ParseError(
                    f"note_off at {ev.time_ms}ms for pitch {ev.pitch} "
                    "has no matching held note_on"
                )
            rec = queue.popleft()  # 释放最早仍按住的一次
            if pedal_down:
                sustained.append(rec)  # 踏板按下：继续发声
            else:
                rec["end_ms"] = ev.time_ms
                rec["end_reason"] = EndReason.NOTE_OFF

        elif ev.type is EventType.PEDAL_DOWN:
            pedal_down = True  # 重复按下不改变状态

        elif ev.type is EventType.PEDAL_UP:
            if pedal_down:
                pedal_down = False
                for rec in sustained:
                    rec["end_ms"] = ev.time_ms
                    rec["end_reason"] = EndReason.PEDAL_UP
                sustained.clear()
            # 踏板本已抬起：重复事件无效果

    # end_ms 关闭其余音符（仍按住的 + 仍被延音的）
    for rec in notes:
        if rec["end_ms"] is None:
            rec["end_ms"] = end_ms
            rec["end_reason"] = EndReason.END_MS

    return [NoteResult(**rec) for rec in notes]
