import asyncio
import importlib.util
import traceback
from pathlib import Path

from logger import Logger

log = Logger()


class data:
    def __init__(self, t=None, d=None):
        self.t = t
        self.d = d


class ModManager:
    def __init__(self, mods_dir):
        self.mods_dir = Path(mods_dir)
        self.mods = []

    def load_all(self):
        self.mods_dir.mkdir(exist_ok=True)
        for path in sorted(self.mods_dir.glob("*/main.py")):
            self._load(path)

    def _load(self, path):
        p = str(path)
        try:
            spec = importlib.util.spec_from_file_location(f"craftlink_mod_{path.parent.name}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            log.err(f"{p} 注册失败: {e}\n{traceback.format_exc()}")
            return
        cls = getattr(module, "CraftLinkModsMain", None)
        if cls is None or not callable(getattr(cls, "craftLinkEvent", None)) or not hasattr(cls, "modsInfo"):
            log.warn(f"{p} 注册失败,协议不匹配")
            return
        info = cls.modsInfo
        if not all(hasattr(info, k) for k in ("GDNDZZK", "version", "name")):
            log.warn(f"{p} 注册失败,错误的info")
            return
        if info.version != "api_v1":
            log.warn(f"{p} 注册失败,版本不匹配")
            return
        instance = cls()
        name = info.name
        instance.logger = Logger(name)
        self.mods.append((name, p, instance))
        try:
            r = instance.craftLinkEvent(data("craftLinkInit", None))
            if asyncio.iscoroutine(r):
                asyncio.run(r)
        except Exception as e:
            self._report_error(p, e)
            return
        log.info(f"[{name}]:{p} 注册成功")

    def dispatch(self, evt: data):
        for name, path, instance in self.mods:
            try:
                r = instance.craftLinkEvent(evt)
                if asyncio.iscoroutine(r):
                    asyncio.ensure_future(r)
            except Exception as e:
                self._report_error(name, e)

    @staticmethod
    def _report_error(name, e):
        log.err(f"[{name}] 调用异常: {e}\n{traceback.format_exc()}")
