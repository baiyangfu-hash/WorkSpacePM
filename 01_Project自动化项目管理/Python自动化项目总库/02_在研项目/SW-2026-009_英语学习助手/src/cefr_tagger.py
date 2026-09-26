"""
CEFR 词汇标注模块 - 基于 cefrpy 为单词标注 CEFR 等级
"""
import os
import sqlite3
from collections.abc import Callable
from typing import TypedDict


class CEFRLevelInfo(TypedDict):
    order: int
    label: str
    word_target: int
    description: str

# 尝试导入 cefrpy
try:
    from cefrpy import CEFRAnalyzer
    CEFRPY_AVAILABLE = True
except ImportError:
    CEFRPY_AVAILABLE = False

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'app.db')
ECDICT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'ecdict_full.db')
FALLBACK_DICT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'ecdict.db')

# CEFR 等级定义
CEFR_LEVELS: dict[str, CEFRLevelInfo] = {
    'A1': {'order': 1, 'label': 'A1 入门', 'word_target': 500, 'description': '能理解和使用日常表达和基础短语'},
    'A2': {'order': 2, 'label': 'A2 基础', 'word_target': 1500, 'description': '能理解常见话题的句子和常用表达'},
    'B1': {'order': 3, 'label': 'B1 进阶', 'word_target': 3000, 'description': '能应对旅行和工作中的大部分场景'},
    'B2': {'order': 4, 'label': 'B2 中级', 'word_target': 5000, 'description': '能流利交流，理解复杂文本'},
    'C1': {'order': 5, 'label': 'C1 高级', 'word_target': 8000, 'description': '能灵活有效地使用语言'},
    'C2': {'order': 6, 'label': 'C2 精通', 'word_target': 12000, 'description': '能轻松理解几乎所有听到和读到的内容'},
}


# 基础词汇备用 CEFR 映射（cefrpy 未安装时的降级保障）
FALLBACK_CEFR_LEVELS = {
    'apple': 'A1', 'hello': 'A1', 'world': 'A1', 'book': 'A1', 'water': 'A1',
    'food': 'A1', 'time': 'A1', 'love': 'A1', 'friend': 'A1', 'work': 'A1',
    'study': 'A1', 'school': 'A1', 'family': 'A1', 'happy': 'A1', 'computer': 'A2',
}


class CEFRTagger:
    """CEFR 词汇标注器"""

    def __init__(self) -> None:
        self._analyzer = None
        if CEFRPY_AVAILABLE:
            try:
                self._analyzer = CEFRAnalyzer()
            except Exception:
                self._analyzer = None

    @property
    def available(self) -> bool:
        return self._analyzer is not None

    def _fallback_get_level(self, word: str) -> str | None:
        """cefrpy 不可用时的平滑降级查询"""
        if not word:
            return None
        lower_word = word.lower().strip()
        if lower_word in FALLBACK_CEFR_LEVELS:
            return FALLBACK_CEFR_LEVELS[lower_word]
        if os.path.exists(DB_PATH):
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute('SELECT cefr_level FROM vocab_cefr WHERE word = ? LIMIT 1', (lower_word,))
                row = cursor.fetchone()
                conn.close()
                if row and row[0]:
                    return str(row[0])
            except Exception:
                pass
        return None

    def get_level(self, word: str) -> str | None:
        """获取单词的 CEFR 等级"""
        if self._analyzer:
            try:
                level = self._analyzer.get_average_word_level_CEFR(word)
                if level:
                    return str(level)
            except Exception:
                pass
        return self._fallback_get_level(word)

    def get_level_with_pos(self, word: str, pos: str | None = None) -> str | None:
        """获取单词在特定词性下的 CEFR 等级"""
        if not self._analyzer:
            return None
        try:
            if pos:
                # 转换 POS 为 cefrpy 的 POSTag
                from cefrpy import POSTag
                pos_map = {
                    'n': POSTag.NN, 'v': POSTag.VB, 'adj': POSTag.JJ,
                    'adv': POSTag.RB, 'prep': POSTag.IN, 'conj': POSTag.CC,
                    'pron': POSTag.PRP, 'num': POSTag.CD, 'art': POSTag.DT,
                }
                tag = pos_map.get(pos.lower()[:3])
                if tag:
                    value: object = self._analyzer.get_word_pos_level_CEFR(word, tag)
                    return str(value) if value is not None else None
            value = self._analyzer.get_average_word_level_CEFR(word)
            return str(value) if value is not None else None
        except Exception:
            return None

    def is_known(self, word: str) -> bool:
        """检查单词是否在 cefrpy 数据库中"""
        if not self._analyzer:
            return False
        try:
            return bool(self._analyzer.is_word_in_database(word))
        except Exception:
            return False

    def get_all_vocab_by_level(self, level: str) -> list[dict[str, object]]:
        """获取指定 CEFR 等级的所有单词（从已标注的数据库）"""
        if not os.path.exists(DB_PATH):
            return []
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT word, cefr_level, pos_tag, frequency_score FROM vocab_cefr WHERE cefr_level = ? ORDER BY frequency_score DESC',
                (level,)
            )
            return [dict(r) for r in cursor.fetchall()]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()


def build_cefr_lexicon(
    limit: int = 5000, progress_callback: Callable[[int, int], None] | None = None
) -> tuple[bool, str]:
    """
    从 ECDICT 构建 CEFR 词汇表
    使用 cefrpy 批量标注单词等级，存入 vocab_cefr 表
    """
    if not CEFRPY_AVAILABLE:
        return False, "cefrpy 未安装（pip install cefrpy）"

    # 确定词典路径
    dict_path = ECDICT_PATH if os.path.exists(ECDICT_PATH) else FALLBACK_DICT_PATH
    if not os.path.exists(dict_path):
        return False, "词典数据库不存在"

    # 确保 app.db 有 vocab_cefr 表
    app_conn = sqlite3.connect(DB_PATH)
    app_cursor = app_conn.cursor()
    app_cursor.execute('''
        CREATE TABLE IF NOT EXISTS vocab_cefr (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL,
            cefr_level TEXT,
            pos_tag TEXT,
            frequency_score REAL DEFAULT 0,
            topic TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    app_cursor.execute('CREATE INDEX IF NOT EXISTS idx_vocab_cefr_level ON vocab_cefr(cefr_level)')
    app_cursor.execute('CREATE INDEX IF NOT EXISTS idx_vocab_cefr_word ON vocab_cefr(word)')
    app_conn.commit()

    # 初始化 cefrpy
    try:
        analyzer = CEFRAnalyzer()
    except Exception as e:
        return False, f"cefrpy 初始化失败: {e}"

    # 从 ECDICT 读取单词（优先高频词：collins 星级高的）
    dict_conn = sqlite3.connect(dict_path)
    dict_conn.row_factory = sqlite3.Row
    dict_cursor = dict_conn.cursor()

    try:
        dict_cursor.execute(
            '''SELECT word, sw, pos, tag, collins, bnc, frq
               FROM stardict
               WHERE word IS NOT NULL AND word != ''
               ORDER BY
                   CASE collins WHEN '' THEN 99 ELSE CAST(collins AS INTEGER) END ASC,
                   CASE frq WHEN '' THEN 999999 ELSE CAST(frq AS INTEGER) END ASC
               LIMIT ?''',
            (limit,)
        )
    except Exception:
        dict_cursor.execute(
            'SELECT word, sw, pos, tag, collins, bnc, frq FROM stardict WHERE word IS NOT NULL AND word != "" LIMIT ?',
            (limit,)
        )

    tagged_count = 0
    batch: list[tuple[str, str, str, float, str]] = []
    batch_size = 100

    for row in dict_cursor:
        word = row['word']
        # 跳过太长的词（可能是短语）
        if len(word) > 30 or ' ' in word:
            continue

        # 用 cefrpy 标注
        try:
            raw_level: object = analyzer.get_average_word_level_CEFR(word)
            level = str(raw_level) if raw_level is not None else None
        except Exception:
            level = None

        if level:
            pos_tag = row['pos'] or ''
            tag = row['tag'] or ''
            # 计算频率分数：collins 星数 + bnc/1000
            freq_score = 0.0
            try:
                collins_val = int(row['collins']) if row['collins'] else 0
                freq_score = (6 - collins_val) * 10  # 5星=50分, 1星=10分
            except (ValueError, TypeError):
                pass
            try:
                bnc_val = int(row['bnc']) if row['bnc'] else 0
                freq_score += min(bnc_val / 100, 50)
            except (ValueError, TypeError):
                pass

            batch.append((word, level, pos_tag, freq_score, tag))
            tagged_count += 1

        # 批量写入
        if len(batch) >= batch_size:
            app_cursor.executemany(
                'INSERT OR IGNORE INTO vocab_cefr (word, cefr_level, pos_tag, frequency_score, topic) VALUES (?, ?, ?, ?, ?)',
                batch
            )
            app_conn.commit()
            batch = []

        if progress_callback and tagged_count % 100 == 0:
            progress_callback(tagged_count, limit)

    # 写入剩余
    if batch:
        app_cursor.executemany(
            'INSERT OR IGNORE INTO vocab_cefr (word, cefr_level, pos_tag, frequency_score, topic) VALUES (?, ?, ?, ?, ?)',
            batch
        )
        app_conn.commit()

    dict_conn.close()
    app_conn.close()

    return True, f"已标注 {tagged_count} 个单词的 CEFR 等级"


def get_vocab_count_by_level() -> dict[str, int]:
    """获取各 CEFR 等级的词汇数量"""
    if not os.path.exists(DB_PATH):
        return {}
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'SELECT cefr_level, COUNT(*) as cnt FROM vocab_cefr WHERE cefr_level IS NOT NULL GROUP BY cefr_level ORDER BY cefr_level'
        )
        return {row[0]: row[1] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def get_words_by_level(level: str, limit: int = 100) -> list[dict[str, object]]:
    """获取指定等级的单词列表"""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(
            'SELECT word, cefr_level, pos_tag, frequency_score, topic FROM vocab_cefr WHERE cefr_level = ? ORDER BY frequency_score DESC LIMIT ?',
            (level, limit)
        )
        return [dict(r) for r in cursor.fetchall()]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def get_user_level_progress(db_path: str | None = None) -> dict[str, object] | None:
    """获取用户等级进度"""
    path = db_path or DB_PATH
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM user_level_progress ORDER BY updated_at DESC LIMIT 1')
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
