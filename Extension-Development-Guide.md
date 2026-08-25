# CraftLink Extension Development Guide

This guide explains how to write extensions for CraftLink. Extensions live in the `mods/` directory, one folder per extension, with the entry file named `main.py`:

```
mods/
└── my_mod/
    └── main.py
```

On startup the server scans every `main.py` under `mods/`, validates it, and registers it.

## Minimal Example

```python
from core import data
from logger import Logger


class CraftLinkModsMain:
    class modsInfo:
        GDNDZZK = "CraftLink"
        version = "api_v1"
        name = "my_mod"

    def __init__(self):
        self.logger = Logger(modsInfo.name)

    def craftLinkEvent(self, evt: data):
        self.logger.info(f"t={evt.t} d={evt.d}")
```

A successful registration logs:

```
[INFO] [sys] [my_mod]:mods/my_mod/main.py registered successfully
```

> Note: log messages themselves are emitted in Chinese by the framework.

## Structure Requirements

`main.py` must define a `CraftLinkModsMain` class containing:

| Member | Description |
| --- | --- |
| `craftLinkEvent(self, evt)` | Event callback, invoked once per event |
| `modsInfo` | Nested class declaring extension metadata |

### modsInfo Fields

| Field | Requirement |
| --- | --- |
| `GDNDZZK` | Must be `"CraftLink"` |
| `version` | Must be `"api_v1"` |
| `name` | Any string; used as the log source |

If any condition fails, the extension is not registered and a warning is logged:

| Log message | Cause |
| --- | --- |
| `注册失败,协议不匹配` (registration failed, protocol mismatch) | Missing CraftLinkModsMain / craftLinkEvent / modsInfo, or wrong GDNDZZK |
| `注册失败,错误的info` (registration failed, invalid info) | modsInfo is missing fields |
| `注册失败,版本不匹配` (registration failed, version mismatch) | version is not api_v1 |

## Dependencies and Runtime

Each extension runs in its own subprocess, fully isolated from the host and from other extensions. An extension may declare its third-party dependencies:

```
mods/
└── my_mod/
    ├── main.py
    └── requirements.txt   # optional, standard pip format
```

### Automatic dependency installation

- For extensions with a `requirements.txt`, the framework creates a dedicated venv under `.venvs/<extension-dir>/` (sibling of `mods/`) and installs the dependencies at startup; the venv is rebuilt automatically when the file changes
- The `mods/` directory is treated as read-only; all venvs and caches live under `.venvs/` (orphaned venvs are cleaned up on the next startup after their extension is removed)
- Extensions without a `requirements.txt` run on the host interpreter, unchanged
- A failed install (bad package name, network down) only skips that extension; the server still starts
- Pass `--no-auto-install` to disable auto-installation; extensions declaring dependencies are then skipped with a warning

### pip mirror selection

When installing, the framework reads mirror candidates from `mirrors.json` in the project root (by default: official PyPI, Aliyun/Tencent/Huawei clouds, and university mirrors — TUNA, USTC, PKU, NJU, ZJU, SJTU, BFSU, HUST, JLU, SUSTech, NJTech, etc.), probes them concurrently, and picks the fastest. The result is cached for 24 hours (`.venvs/.mirror.json`); editing `mirrors.json` invalidates it immediately.

Priority: `--index-url` argument > `PIP_INDEX_URL` environment variable > auto-probe > pip default. Set `mirrors.json` to an empty array `[]` to disable probing.

> Note: automatic mirrors imply trusting third-party mirror integrity; for security-sensitive deployments pin the official index via `--index-url`.

### Runtime model and limitations

- A crashing or killed extension only affects itself; the framework logs it and keeps running
- Events are delivered as JSON, so `evt.d` must be JSON-serializable
- `print` output inside an extension is redirected to framework logs and never breaks inter-process communication
- Async callbacks execute sequentially within each extension's own process

## Receiving Events

Events are delivered to `craftLinkEvent` as a `data` instance:

- `evt.t`: event type (str)
- `evt.d`: event payload, or `None` when absent

After startup the server sends an initialization event to every extension:

```python
def craftLinkEvent(self, evt: data):
    if evt.t == "craftLinkInit":
        ...
        return
```

Both sync and async callbacks are supported:

```python
async def craftLinkEvent(self, evt: data):
    await do_something()
```

Any exception raised inside the callback is caught by the framework and logged at err level with the extension name, error message, and stack trace; other extensions keep running.

## Logging

The framework injects `self.logger` into your instance once registration succeeds — just use it:

```python
self.logger.info("ready")
self.logger.warn("missing config")
self.logger.err("something went wrong")
```

Output format:

```
[2026-08-23 19:38:18] [INFO] [my_mod] ready
```

The log source is the `modsInfo.name` recorded by the framework at registration time, so it cannot be altered by extension code at runtime; do not construct your own `Logger` instead. Framework logs use `sys` as the source.
