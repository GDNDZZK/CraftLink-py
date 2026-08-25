import asyncio
import importlib.util
import json
import queue
import sys
import threading
import traceback
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import data
from moddata import open_mod_storage

_out = None
_emit_lock = threading.Lock()
DISPATCH_JOIN_TIMEOUT = 2.5


def emit(obj):
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    with _emit_lock:
        _out.write(line)
        _out.flush()


class RunnerLogger:
    def __init__(self, name):
        self.name = name

    def _log(self, level, msg):
        emit({"type": "log", "level": level, "msg": str(msg)})

    def info(self, msg):
        self._log("INFO", msg)

    def warn(self, msg):
        self._log("WARN", msg)

    def err(self, msg):
        self._log("ERR", msg)


def load_mod(mod_dir):
    path = Path(mod_dir) / "main.py"
    spec = importlib.util.spec_from_file_location(f"craftlink_mod_{path.parent.name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = getattr(module, "CraftLinkModsMain", None)
    if cls is None or not callable(getattr(cls, "craftLinkEvent", None)) or not hasattr(cls, "modsInfo"):
        raise RuntimeError("协议不匹配")
    info = cls.modsInfo
    if not all(hasattr(info, k) for k in ("GDNDZZK", "version", "name")):
        raise RuntimeError("错误的info")
    if info.version != "api_v1":
        raise RuntimeError("版本不匹配")
    return cls, info


def main():
    global _out
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    _out = sys.stdout
    mod_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    with redirect_stdout(sys.stderr):
        try:
            cls, info = load_mod(mod_dir)
            instance = cls()
            name = info.name
            instance.logger = RunnerLogger(name)
            instance.data = open_mod_storage(mod_dir)
        except Exception as e:
            emit({"type": "load_error", "error": f"{e}\n{traceback.format_exc()}"})
            return

        def dispatch_loop():
            while True:
                item = q.get()
                if item is None:
                    return
                evt = data(*item)
                try:
                    r = instance.craftLinkEvent(evt)
                    if asyncio.iscoroutine(r):
                        asyncio.run(r)
                except Exception:
                    emit({"type": "error", "tb": traceback.format_exc()})

        q = queue.Queue()
        q.put(("craftLinkInit", None))
        worker = threading.Thread(target=dispatch_loop, daemon=True)
        worker.start()
        instance.logger.info(f"数据存储后端: {instance.data.backend}")
        emit({"type": "hello", "name": name})
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            q.put((msg.get("t"), msg.get("d")))
        q.put(None)
        worker.join(timeout=DISPATCH_JOIN_TIMEOUT)
        if worker.is_alive():
            instance.logger.warn("存在未返回的事件回调,跳过数据存储关闭")
            return
        try:
            instance.data.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
