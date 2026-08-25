"""Mod 数据统一存储。

存储类来自 https://gitee.com/gdndzzk/httpLevelDB/tree/master/Util (WTFPL)。
优先使用 plyvel (LevelDB),不可用时回退 SQLite,两个后端行为一致:
键必须为 str,值支持 None/bool/int/float/str/list/tuple/dict/set 嵌套。
"""

import json
import shutil
import sqlite3
import threading
import time
from pathlib import Path

try:
    import plyvel  # type: ignore
except ImportError:
    plyvel = None


def obj_to_str(obj):
    """
    Recursively converts a Python object to a JSON-compatible string representation.
    Supports nested data structures including sets, lists, dictionaries, strings,
    integers, floats, booleans, None, and tuples.

    The conversion follows this format:
    {
        't': <object_type>,
        'd': <converted_data>
    }
    where <object_type> can be 'set', 'list', 'dict', 'str', 'int', 'float', 'bool', 'None', or 'tuple'

    Args:
        obj: The Python object to be converted

    Returns:
        str: A JSON string representation of the object

    Examples:
        >>> obj_to_str({1, 2, 3})
        '{"type": "set", "data": [{"type": "int", "data": 1}, ...]}'
        >>> obj_to_str([1, "a", None])
        '{"type": "list", "data": [{"type": "int", "data": 1}, ...]}'
    """
    def _convert(obj):
        if obj is None:
            return {'t': 'N', 'd': None}
        elif type(obj) is bool:
            return {'t': 'b', 'd': obj}
        elif type(obj) is int:
            return {'t': 'i', 'd': obj}
        elif type(obj) is float:
            return {'t': 'f', 'd': obj}
        elif type(obj) is str:
            return {'t': 's', 'd': obj}
        elif type(obj) is list:
            return {'t': 'L', 'd': [_convert(item) for item in obj]}
        elif type(obj) is tuple:
            return {'t': 'T', 'd': [_convert(item) for item in obj]}
        elif type(obj) is dict:
            return {
                't': 'D',
                'd': {k: _convert(v) for k, v in obj.items()}
            }
        elif type(obj) is set:
            return {
                't': 'S',
                'd': [_convert(item) for item in obj]
            }
        else:
            raise TypeError(f"Unsupported type: {type(obj)}")

    converted = _convert(obj)
    return json.dumps(converted)


def str_to_obj(json_str):
    """
    Recursively converts a JSON-formatted string with type information back to Python objects.
    This is the inverse function of obj_to_str, supporting all the same types.

    Args:
        json_str: JSON string produced by obj_to_str function

    Returns:
        object: The reconstructed Python object

    Raises:
        ValueError: If the JSON string is malformed
        TypeError: If encountering unsupported type in the JSON
    """

    def _convert(d):
        type_name = d['t']
        data = d['d']

        match type_name:
            case 'N':
                return None
            case 'b':
                return data
            case 'i':
                return int(data)
            case 'f':
                return float(data)
            case 's':
                return data
            case 'L':
                return [_convert(item) for item in data]
            case 'T':
                return tuple(_convert(item) for item in data)
            case 'S':
                return set(_convert(item) for item in data)
            case 'D':
                return {k: _convert(v) for k, v in data.items()}
            case _:
                raise TypeError(f"Unsupported type in JSON: {type_name}")

    return _convert(json.loads(json_str))


class LevelDBDict:
    def __init__(self, path, create_if_missing=True, encoding='utf-8', more_type_suspect=False):
        """
        初始化LevelDB数据库实例
        :param path: 数据库存储路径
        :param create_if_missing: 若路径不存在是否创建新数据库
        :param encoding: 字符编码(默认utf-8)
        """
        self.db = plyvel.DB(path, create_if_missing=create_if_missing)
        self.encoding = encoding
        self.more_type_suspect = more_type_suspect
        self.path = path
        self._count = -2
        # 记录开始时间
        start_time = time.time()
        # 先遍历,如果耗时大于1秒则直接初始化,否则先不初始化
        for _ in self.db.iterator():
            self._count += 1
            # 比较耗时
            if time.time() - start_time > 0.1:
                self._count = -1
                break
        # 如果没有数据,则初始化
        if self._count == -2:
            self._count = 0

    def __getitem__(self, key):
        if not isinstance(key, str):
            raise TypeError("键必须是字符串类型")

        value = self.db.get(key.encode(self.encoding))
        if value is None:
            raise KeyError(key)
        if self.more_type_suspect:
            return str_to_obj(value.decode(self.encoding))
        return value.decode(self.encoding)

    def __setitem__(self, key, value):
        if not isinstance(key, str):
            raise TypeError("键必须是字符串类型")
        if not self.more_type_suspect and not isinstance(value, str):
            raise TypeError("键和值必须是字符串类型")
        # 如果self._count>-1,则说明初始化过长度,则更新长度
        if self._count > -1 and key not in self:
            # 判断是否是新增
            self._count += 1
        if self.more_type_suspect:
            value = obj_to_str(value)
        self.db.put(key.encode(self.encoding), value.encode(self.encoding))

    def __delitem__(self, key):
        if not isinstance(key, str):
            raise TypeError("键必须是字符串类型")
        self.db.delete(key.encode(self.encoding))

    def __contains__(self, key):
        if not isinstance(key, str):
            return False
        return self.db.get(key.encode(self.encoding)) is not None

    def __iter__(self):
        for key in self.keys():
            yield key

    def keys(self):
        """ 返回键的生成器 """
        for key in self.db.iterator(include_value=False):
            yield key.decode(self.encoding)

    def values(self):
        """ 返回值的生成器 """
        for value in self.db.iterator(include_key=False):
            if self.more_type_suspect:
                yield str_to_obj(value.decode(self.encoding))
            else:
                yield value.decode(self.encoding)

    def items(self):
        """ 返回键值对的生成器 """
        for key, value in self.db.iterator():
            if self.more_type_suspect:
                value = str_to_obj(value.decode(self.encoding))
            else:
                value = value.decode(self.encoding)

            yield (key.decode(self.encoding), value)

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def clear(self):
        """
        通过删除数据库文件实现极速清空

        :操作流程:
        1. 关闭数据库连接
        2. 删除数据库目录及其所有文件
        3. 重新创建空数据库

        :注意:
        - 操作不可逆，数据会永久丢失
        - 会短暂释放数据库文件句柄
        """
        if not hasattr(self, 'db'):
            return  # 未初始化时直接返回

        # 关闭现有数据库连接
        self.db.close()
        del self.db

        # 删除数据库目录
        shutil.rmtree(self.path, ignore_errors=True)

        # 重新创建数据库
        self.db = plyvel.DB(self.path, create_if_missing=True)

        # 重置计数
        self._count = 0

    def get(self, __key, __default = None):
        try:
            return self.__getitem__(__key)
        except KeyError:
            return __default

    def pop(self, __key, __default = None):
        result = self.get(__key, __default)
        try:
            self.__delitem__(__key)
        except KeyError:
            pass
        return result

    def __len__(self) -> int:
        """
        获取数据库中的键值对数量（智能选择最优计数方式）

        :性能策略:
        - 首次调用：完整遍历并缓存结果
        - 后续调用：返回缓存值（需要维护计数一致性）
        - 调用clear()后自动重置缓存

        :注意: 在并发写入场景需要外部加锁保证一致性
        """
        if self._count <= -1:
            self._count = sum(1 for _ in self.db)
        return self._count


def retry_on_locked(max_retries=100, delay=0.01):
    """
    重试装饰器,用于处理SQLite锁占用错误
    :param max_retries: 最大重试次数
    :param delay: 重试间隔时间（秒）
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            last_error = None
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "locked" in str(e).lower() or "database is locked" in str(e).lower():
                        last_error = e
                        retries += 1
                        time.sleep(delay)
                        continue
                    raise  # 如果不是锁占用错误，直接抛出
            # 如果重试次数用完，抛出最后的错误
            raise last_error if last_error else sqlite3.OperationalError("Database locked after retries")
        return wrapper
    return decorator


class SQLiteDict:
    def __init__(self, db_path, table_name='kv_store'):
        """
        初始化SQLite数据库实例
        :param db_path: 数据库文件路径
        :param table_name: 表名(默认为'kv_store')
        """
        self.db_path = db_path
        self.table_name = table_name
        self._local = threading.local()
        self._init_db()

    def _get_connection(self):
        """获取线程本地连接"""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(self.db_path)
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection

    @retry_on_locked()
    def _init_db(self):
        """初始化数据库表"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        conn.commit()

    @retry_on_locked()
    def __getitem__(self, key):
        if not isinstance(key, str):
            raise TypeError("键必须是字符串类型")

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f'SELECT value FROM {self.table_name} WHERE key = ?', (key,))
        row = cursor.fetchone()
        if row is None:
            raise KeyError(key)
        return row['value']

    @retry_on_locked()
    def __setitem__(self, key, value):
        if not isinstance(key, str):
            raise TypeError("键必须是字符串类型")
        if not isinstance(value, str):
            raise TypeError("值必须是字符串类型")

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f'''
            INSERT OR REPLACE INTO {self.table_name} (key, value) VALUES (?, ?)
        ''', (key, value))
        conn.commit()

    @retry_on_locked()
    def __delitem__(self, key):
        if not isinstance(key, str):
            raise TypeError("键必须是字符串类型")

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f'DELETE FROM {self.table_name} WHERE key = ?', (key,))
        if cursor.rowcount == 0:
            raise KeyError(key)
        conn.commit()

    @retry_on_locked()
    def __contains__(self, key):
        if not isinstance(key, str):
            return False

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f'SELECT 1 FROM {self.table_name} WHERE key = ?', (key,))
        return cursor.fetchone() is not None

    def __iter__(self):
        for key in self.keys():
            yield key

    @retry_on_locked()
    def keys(self):
        """返回键的生成器"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f'SELECT key FROM {self.table_name}')
        for row in cursor:
            yield row['key']

    @retry_on_locked()
    def values(self):
        """返回值的生成器"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f'SELECT value FROM {self.table_name}')
        for row in cursor:
            yield row['value']

    @retry_on_locked()
    def items(self):
        """返回键值对的生成器"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f'SELECT key, value FROM {self.table_name}')
        for row in cursor:
            yield (row['key'], row['value'])

    def get(self, key, default=None):
        """获取键对应的值，如果不存在则返回默认值"""
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key, default=None):
        """删除键并返回其值，如果不存在则返回默认值"""
        try:
            value = self[key]
            del self[key]
            return value
        except KeyError:
            return default

    @retry_on_locked()
    def clear(self):
        """清空所有数据"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f'DELETE FROM {self.table_name}')
        conn.commit()

    @retry_on_locked()
    def __len__(self):
        """返回键值对数量"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f'SELECT COUNT(*) FROM {self.table_name}')
        return cursor.fetchone()[0]

    def close(self):
        """关闭数据库连接"""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class TypedLevelDBDict(LevelDBDict):
    """强制 more_type_suspect 的 LevelDBDict,并使删除不存在键时抛 KeyError"""

    def __init__(self, path, create_if_missing=True, encoding='utf-8'):
        super().__init__(path, create_if_missing=create_if_missing,
                         encoding=encoding, more_type_suspect=True)

    def __delitem__(self, key):
        if not isinstance(key, str):
            raise TypeError("键必须是字符串类型")
        if key not in self:
            raise KeyError(key)
        self.db.delete(key.encode(self.encoding))


class TypedSQLiteDict(SQLiteDict):
    """值支持复杂类型的 SQLiteDict,磁盘格式与 TypedLevelDBDict 一致"""

    @retry_on_locked()
    def __getitem__(self, key):
        return str_to_obj(super().__getitem__(key))

    @retry_on_locked()
    def __setitem__(self, key, value):
        super().__setitem__(key, obj_to_str(value))

    @retry_on_locked()
    def values(self):
        for value in super().values():
            yield str_to_obj(value)

    @retry_on_locked()
    def items(self):
        for key, value in super().items():
            yield (key, str_to_obj(value))

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key, default=None):
        try:
            value = self[key]
            del self[key]
            return value
        except KeyError:
            return default


def open_mod_storage(mod_dir):
    """打开某个 mod 的数据存储。

    数据根目录为本文件所在目录下的 datas/,每个 mod 一个子目录,
    命名规则与 .venvs 一致(使用 mod 目录名)。
    优先 plyvel,不可用时回退 SQLite。
    """
    root = Path(__file__).resolve().parent / "datas"
    mod_root = root / Path(mod_dir).name
    if plyvel is not None:
        try:
            db = TypedLevelDBDict(str(mod_root / "leveldb"))
            db.backend = "plyvel"
            return db
        except Exception:
            pass
    mod_root.mkdir(parents=True, exist_ok=True)
    db = TypedSQLiteDict(str(mod_root / "data.sqlite"))
    db.backend = "sqlite"
    return db
