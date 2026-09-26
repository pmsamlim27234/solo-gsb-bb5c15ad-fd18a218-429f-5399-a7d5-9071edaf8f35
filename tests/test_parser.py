"""核心解析逻辑与 API 的单元测试。"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Event, EventType
from app.parser import ParseError, parse_events

client = TestClient(app)


def ev(t, time_ms, pitch=None):
    return Event(type=EventType(t), time_ms=time_ms, pitch=pitch)


def as_tuples(notes):
    return [(n.note_index, n.pitch, n.start_ms, n.end_ms, n.end_reason.value) for n in notes]


def test_simple_note_off():
    notes = parse_events(1000, [ev("note_on", 100, 60), ev("note_off", 400, 60)])
    assert as_tuples(notes) == [(0, 60, 100, 400, "note_off")]


def test_pedal_extends_released_note_until_pedal_up():
    notes = parse_events(1000, [
        ev("note_on", 100, 60),
        ev("pedal_down", 200),
        ev("note_off", 300, 60),   # 踏板按下，松键后仍发声
        ev("pedal_up", 800),       # 抬踏板结束延音
    ])
    assert as_tuples(notes) == [(0, 60, 100, 800, "pedal_up")]


def test_note_off_without_pedal_ends_immediately_even_if_pedal_later():
    notes = parse_events(1000, [
        ev("note_on", 100, 60),
        ev("note_off", 300, 60),   # 踏板未按下，立即结束
        ev("pedal_down", 400),
        ev("pedal_up", 900),
    ])
    assert as_tuples(notes) == [(0, 60, 100, 300, "note_off")]


def test_end_ms_closes_held_and_sustained_notes():
    notes = parse_events(1000, [
        ev("note_on", 100, 60),
        ev("pedal_down", 200),
        ev("note_off", 300, 60),   # 延音中
        ev("note_on", 400, 64),    # 仍按住
    ])
    assert as_tuples(notes) == [
        (0, 60, 100, 1000, "end_ms"),
        (1, 64, 400, 1000, "end_ms"),
    ]


def test_repeated_same_pitch_notes_are_independent_fifo_release():
    notes = parse_events(1000, [
        ev("note_on", 100, 60),
        ev("note_on", 200, 60),    # 同音高再次按下，独立音符
        ev("note_off", 300, 60),   # 释放最早按下的那次
        ev("note_off", 400, 60),
    ])
    assert as_tuples(notes) == [
        (0, 60, 100, 300, "note_off"),
        (1, 60, 200, 400, "note_off"),
    ]


def test_repeated_pedal_events_do_not_change_state():
    notes = parse_events(1000, [
        ev("pedal_down", 100),
        ev("pedal_down", 150),     # 重复，无效果
        ev("note_on", 200, 60),
        ev("note_off", 300, 60),   # 踏板仍按下 -> 延音
        ev("pedal_up", 400),
        ev("pedal_up", 450),       # 重复，无效果
    ])
    assert as_tuples(notes) == [(0, 60, 200, 400, "pedal_up")]


def test_events_sorted_by_time_then_input_order():
    # 输入乱序：note_off 时间更早，应先被处理
    notes = parse_events(1000, [
        ev("note_on", 500, 60),
        ev("note_on", 100, 64),
        ev("note_off", 300, 64),
    ])
    assert as_tuples(notes) == [
        (0, 64, 100, 300, "note_off"),
        (1, 60, 500, 1000, "end_ms"),
    ]


def test_same_time_processed_in_input_order():
    # 同一时刻：先 note_on 后 note_off（按输入序号）
    notes = parse_events(1000, [
        ev("note_on", 100, 60),
        ev("note_off", 100, 60),
    ])
    assert as_tuples(notes) == [(0, 60, 100, 100, "note_off")]


def test_note_off_without_match_raises():
    with pytest.raises(ParseError):
        parse_events(1000, [ev("note_off", 100, 60)])


def test_pedal_up_closes_only_sustained_notes():
    notes = parse_events(2000, [
        ev("pedal_down", 100),
        ev("note_on", 200, 60),
        ev("note_off", 300, 60),   # 延音
        ev("note_on", 400, 64),    # 仍按住
        ev("pedal_up", 900),       # 只结束延音的 60
    ])
    assert as_tuples(notes) == [
        (0, 60, 200, 900, "pedal_up"),
        (1, 64, 400, 2000, "end_ms"),
    ]


def test_api_parse_ok():
    resp = client.post("/parse", json={
        "end_ms": 1000,
        "events": [
            {"type": "note_on", "time_ms": 100, "pitch": 60},
            {"type": "pedal_down", "time_ms": 200},
            {"type": "note_off", "time_ms": 300, "pitch": 60},
            {"type": "pedal_up", "time_ms": 800},
        ],
    })
    assert resp.status_code == 200
    assert resp.json() == {"notes": [{
        "note_index": 0, "pitch": 60, "start_ms": 100,
        "end_ms": 800, "end_reason": "pedal_up",
    }]}


def test_api_unmatched_note_off_returns_422():
    resp = client.post("/parse", json={
        "end_ms": 1000,
        "events": [{"type": "note_off", "time_ms": 100, "pitch": 60}],
    })
    assert resp.status_code == 422
    assert "no matching held note_on" in resp.json()["detail"]


def test_api_pitch_out_of_range_rejected():
    resp = client.post("/parse", json={
        "end_ms": 1000,
        "events": [{"type": "note_on", "time_ms": 0, "pitch": 128}],
    })
    assert resp.status_code == 422


def test_api_time_beyond_end_ms_rejected():
    resp = client.post("/parse", json={
        "end_ms": 100,
        "events": [{"type": "note_on", "time_ms": 200, "pitch": 60}],
    })
    assert resp.status_code == 422


def test_api_note_event_requires_pitch():
    resp = client.post("/parse", json={
        "end_ms": 1000,
        "events": [{"type": "note_on", "time_ms": 0}],
    })
    assert resp.status_code == 422
