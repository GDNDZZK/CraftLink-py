from datetime import datetime


class Logger:
    def __init__(self, source: str = "sys"):
        self.source = source

    def _write(self, level: str, msg: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] [{level}] [{self.source}] {msg}", flush=True)

    def info(self, msg: str):
        self._write("INFO", str(msg))

    def warn(self, msg: str):
        self._write("WARN", str(msg))

    def err(self, msg: str):
        self._write("ERR", str(msg))
