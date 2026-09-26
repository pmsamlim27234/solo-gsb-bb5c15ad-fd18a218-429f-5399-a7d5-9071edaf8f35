# MIDI 延音解析 API

供钢琴教学软件调用的延音踏板解析服务：输入以毫秒计时的 `note_on` / `note_off` / `pedal_down` / `pedal_up` 事件及 `end_ms`，输出每次按键的发声半开区间 `[start_ms, end_ms)` 与结束原因。

## 快速启动

单条命令（Docker Compose）：

```bash
docker compose up --build
```

- API 地址：`http://localhost:8000`
- 解析接口：`POST http://localhost:8000/parse`
- 交互式文档（Swagger UI）：`http://localhost:8000/docs`
- 健康检查：`GET http://localhost:8000/health`

也可以不用 Compose：

```bash
docker build -t midi-sustain-api . && docker run -p 8000:8000 midi-sustain-api
```

本地开发（不用 Docker）：

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

运行测试：

```bash
pytest
```

## API 说明

### `POST /parse`

请求体：

```json
{
  "end_ms": 5000,
  "events": [
    {"type": "note_on",    "time_ms": 100,  "pitch": 60},
    {"type": "pedal_down", "time_ms": 200},
    {"type": "note_off",   "time_ms": 300,  "pitch": 60},
    {"type": "pedal_up",   "time_ms": 800}
  ]
}
```

- `end_ms`：片段结束时间（毫秒，≥ 0），用于关闭所有仍未结束的音符。
- `events[]`：
  - `type`：`note_on` / `note_off` / `pedal_down` / `pedal_up`
  - `time_ms`：事件时间（毫秒），须在 `0 ~ end_ms` 之间
  - `pitch`：MIDI 音高 `0 ~ 127`，仅 `note_on` / `note_off` 需要

响应（`notes` 按按键序号排列）：

```json
{
  "notes": [
    {
      "note_index": 0,
      "pitch": 60,
      "start_ms": 100,
      "end_ms": 800,
      "end_reason": "pedal_up"
    }
  ]
}
```

- 发声区间为半开区间 `[start_ms, end_ms)`。
- `end_reason` 取值：
  - `note_off`：踏板未按下时正常松键结束
  - `pedal_up`：踏板按下期间松键的音符被延音，抬踏板时结束
  - `end_ms`：片段结束时仍按住或仍被延音，强制关闭

## 解析规则

1. 事件按 `(time_ms, 输入序号)` 排序处理；时间相同时保持输入先后。
2. 同一音高重复按下各成独立音符；`note_off` 释放该音高**最早仍按住**的一次。
3. 踏板按下期间松键的音符继续发声；`pedal_up` 只结束这些被延音的音符，不影响仍按住的音符。
4. 重复的踏板状态事件（已按下再 `pedal_down`、已抬起再 `pedal_up`）不改变状态。
5. `end_ms` 关闭所有剩余未结束的音符。

## 错误处理

请求不合法时返回 `422 Unprocessable Entity`，包括：

- 音高不在 `0 ~ 127`
- `time_ms` 超出 `0 ~ end_ms`
- `note_on` / `note_off` 缺少 `pitch`
- `note_off` 没有对应仍按住的按键（响应 `detail` 中含说明）

## 项目结构

```
app/
  main.py      FastAPI 入口（POST /parse, GET /health）
  models.py    请求 / 响应模型与校验
  parser.py    延音解析核心逻辑
tests/
  test_parser.py
Dockerfile
docker-compose.yml
requirements.txt
```
