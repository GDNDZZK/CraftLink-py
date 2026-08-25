import hashlib
import json
import os
import queue
import shutil
import stat
import subprocess
import sys
import threading
import time
import urllib.request
import venv
from pathlib import Path

from logger import Logger

log = Logger()

RUNNER = Path(__file__).resolve().parent / "modrunner.py"
HELLO_TIMEOUT = 10
PIP_TIMEOUT = 600
MIRROR_TTL = 24 * 3600
PROBE_TIMEOUT = 8
RACE_TIMEOUT = 5
PROBE_PACKAGE = "six"


class data:
    def __init__(self, t=None, d=None):
        self.t = t
        self.d = d


class MirrorSelector:
    def __init__(self, venv_dir, index_url=None):
        self.venv_dir = Path(venv_dir)
        self.index_url = index_url
        self.cache = self.venv_dir / ".mirror.json"

    def select(self):
        if self.index_url:
            return self.index_url
        if os.environ.get("PIP_INDEX_URL"):
            return None
        mirrors_file = Path(__file__).resolve().parent / "mirrors.json"
        try:
            mirrors = json.loads(mirrors_file.read_text(encoding="utf-8"))
        except Exception as e:
            log.warn(f"读取 mirrors.json 失败,跳过镜像探测: {e}")
            return None
        if not isinstance(mirrors, list) or not mirrors:
            return None
        digest = hashlib.sha256(json.dumps(mirrors, ensure_ascii=False).encode("utf-8")).hexdigest()
        cached = self._load_cache()
        if cached and cached.get("hash") == digest and time.time() - cached.get("ts", 0) < MIRROR_TTL:
            return cached.get("url")
        url = self._race(mirrors)
        if url:
            self._save_cache(digest, url)
        return url

    def _load_cache(self):
        try:
            return json.loads(self.cache.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _save_cache(self, digest, url):
        try:
            self.venv_dir.mkdir(parents=True, exist_ok=True)
            self.cache.write_text(
                json.dumps({"hash": digest, "url": url, "ts": time.time()}),
                encoding="utf-8",
            )
        except Exception as e:
            log.warn(f"镜像缓存写入失败: {e}")

    def _race(self, mirrors):
        done = threading.Event()
        win = []
        lock = threading.Lock()

        def probe(url):
            try:
                target = url.rstrip("/") + f"/{PROBE_PACKAGE}/"
                req = urllib.request.Request(target, headers={"User-Agent": "pip"})
                with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as r:
                    if r.status != 200:
                        return
                    body = b""
                    while len(body) < 65536:
                        chunk = r.read(8192)
                        if not chunk:
                            break
                        body += chunk
                        if done.is_set():
                            return
                    if PROBE_PACKAGE.encode() not in body:
                        return
                    with lock:
                        if not win:
                            win.append(url)
                            done.set()
            except Exception:
                pass

        for u in mirrors:
            if not isinstance(u, str) or not u:
                continue
            threading.Thread(target=probe, args=(u,), daemon=True).start()
        if done.wait(RACE_TIMEOUT):
            log.info(f"镜像探测完成,使用: {win[0]}")
            return win[0]
        log.warn("镜像探测全部失败,使用 pip 默认源")
        return None


class ModManager:
    def __init__(self, mods_dir, venv_dir=None, auto_install=True, index_url=None):
        self.mods_dir = Path(mods_dir)
        self.venv_dir = Path(venv_dir) if venv_dir else self.mods_dir.parent / ".venvs"
        self.auto_install = auto_install
        self.mirror = MirrorSelector(self.venv_dir, index_url)
        self.mods = []

    def load_all(self):
        self.mods_dir.mkdir(exist_ok=True)
        entries = sorted(self.mods_dir.glob("*/main.py"))
        self._cleanup_orphans({p.parent.name for p in entries})
        for path in entries:
            self._load(path)

    def _cleanup_orphans(self, names):
        if not self.venv_dir.exists():
            return
        for child in self.venv_dir.iterdir():
            if child.is_dir() and (child / "pyvenv.cfg").exists() and child.name not in names:
                log.info(f"清理无对应插件的 venv: {child}")
                self._rmtree(child)

    @staticmethod
    def _rmtree(path):
        def onexc(func, p, exc):
            try:
                os.chmod(p, stat.S_IWRITE)
                func(p)
            except Exception:
                pass

        shutil.rmtree(path, onexc=onexc)

    def _ensure_venv(self, name, req_file):
        env_dir = self.venv_dir / name
        marker = env_dir / ".craftlink-deps"
        digest = hashlib.sha256(req_file.read_bytes()).hexdigest()
        python = self._venv_python(env_dir)
        if python and marker.exists() and marker.read_text(encoding="utf-8").strip() == digest:
            return python
        if env_dir.exists():
            self._rmtree(env_dir)
        log.info(f"[{name}] 创建独立 venv: {env_dir}")
        builder = venv.EnvBuilder(with_pip=True)
        ctx = builder.ensure_directories(env_dir)
        builder.create(env_dir)
        python = ctx.env_exe
        cmd = [python, "-m", "pip", "install", "-r", str(req_file),
               "--no-input", "--disable-pip-version-check"]
        index = self.mirror.select()
        if index:
            cmd += ["-i", index]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=PIP_TIMEOUT)
        if r.returncode != 0:
            raise RuntimeError(f"依赖安装失败:\n{(r.stderr or r.stdout)[-2000:]}")
        marker.write_text(digest, encoding="utf-8")
        return python

    @staticmethod
    def _venv_python(env_dir):
        exe = env_dir / ("Scripts" / "python.exe" if os.name == "nt" else Path("bin") / "python")
        return str(exe) if exe.exists() else None

    def _load(self, path):
        mod_dir = path.parent
        name = mod_dir.name
        req = mod_dir / "requirements.txt"
        try:
            if req.exists():
                if not self.auto_install:
                    log.warn(f"[{name}] 存在依赖声明但已禁用自动安装,跳过")
                    return
                python = self._ensure_venv(name, req)
            else:
                python = sys.executable
        except Exception as e:
            log.err(f"[{name}] 依赖准备失败: {e}")
            return
        try:
            proc = subprocess.Popen(
                [python, "-u", str(RUNNER), str(mod_dir)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        except Exception as e:
            log.err(f"[{name}] 子进程启动失败: {e}")
            return
        q = queue.Queue()
        threading.Thread(target=self._reader, args=(proc, q), daemon=True).start()
        threading.Thread(target=self._stderr_pump, args=(proc, name), daemon=True).start()
        deadline = time.time() + HELLO_TIMEOUT
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                log.err(f"[{name}] 加载超时({HELLO_TIMEOUT}s),已跳过")
                self._kill(proc)
                return
            try:
                item = q.get(timeout=remaining)
            except queue.Empty:
                log.err(f"[{name}] 加载超时({HELLO_TIMEOUT}s),已跳过")
                self._kill(proc)
                return
            if item is None:
                log.err(f"[{name}] 子进程提前退出,加载失败")
                self._kill(proc)
                return
            msg = self._handle_msg(name, item)
            if msg and msg.get("type") == "hello":
                mod_name = msg.get("name", name)
                break
            if msg and msg.get("type") == "load_error":
                log.err(f"[{name}] 加载失败: {msg.get('error', '未知错误')}")
                self._kill(proc)
                return
        lock = threading.Lock()
        self.mods.append((mod_name, str(path), proc, lock))
        threading.Thread(target=self._pump, args=(mod_name, q), daemon=True).start()
        log.info(f"[{mod_name}]:{path} 注册成功")

    @staticmethod
    def _reader(proc, q):
        try:
            for line in proc.stdout:
                q.put(line)
        except Exception:
            pass
        finally:
            q.put(None)

    @staticmethod
    def _handle_msg(name, item):
        try:
            msg = json.loads(item)
        except ValueError:
            log.warn(f"[{name}] 无法解析的子进程输出: {item.strip()[:200]}")
            return None
        t = msg.get("type")
        if t in ("hello", "load_error"):
            return msg
        if t == "log":
            getattr(Logger(name), {"INFO": "info", "WARN": "warn", "ERR": "err"}.get(msg.get("level"), "info"))(msg.get("msg", ""))
        elif t == "error":
            log.err(f"[{name}] 调用异常:\n{msg.get('tb', '')}")
        return None

    def _pump(self, name, q):
        while True:
            item = q.get()
            if item is None:
                log.warn(f"[{name}] 插件进程已退出")
                break
            self._handle_msg(name, item)

    @staticmethod
    def _stderr_pump(proc, name):
        try:
            for line in proc.stderr:
                if line.strip():
                    log.info(f"[{name}] {line.rstrip()}")
        except Exception:
            pass

    @staticmethod
    def _kill(proc):
        try:
            proc.kill()
        except Exception:
            pass

    def dispatch(self, evt: data):
        try:
            payload = json.dumps({"t": evt.t, "d": evt.d})
        except (TypeError, ValueError) as e:
            log.err(f"事件序列化失败: {e}")
            return
        for name, path, proc, lock in list(self.mods):
            if proc.poll() is not None:
                continue
            try:
                with lock:
                    proc.stdin.write(payload + "\n")
                    proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                log.err(f"[{name}] 子进程管道断裂,可能已退出")

    def shutdown(self):
        for name, path, proc, lock in self.mods:
            if proc.poll() is None:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
        deadline = time.time() + 3
        for name, path, proc, lock in self.mods:
            if proc.poll() is not None:
                continue
            try:
                proc.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        log.info("所有插件子进程已停止")
