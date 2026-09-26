"""
词典模块 - 离线词典查询
基于 ECDICT 数据库
"""
import os
import sqlite3

ECDICT_URL = "https://github.com/skywind3000/ECDICT/raw/master/ecdict.db"
DICT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'ecdict.db')
FULL_DICT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'ecdict_full.db')

DictionaryEntry = dict[str, object]
DictionaryLookup = DictionaryEntry | list[DictionaryEntry] | None

class Dictionary:
    def __init__(self) -> None:
        self.conn: sqlite3.Connection | None = None
        self._ensure_dict()
        self._connect()

    def _ensure_dict(self) -> None:
        """确保词典数据库存在，优先使用完整版"""
        os.makedirs(os.path.dirname(DICT_PATH), exist_ok=True)
        # 完整版或简化版存在即可
        if os.path.exists(FULL_DICT_PATH) or os.path.exists(DICT_PATH):
            return
        self._create_simple_dict()

    def _create_simple_dict(self) -> None:
        """创建简化版词典（用于演示）"""
        conn = sqlite3.connect(DICT_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stardict (
                id INTEGER PRIMARY KEY,
                word TEXT UNIQUE,
                sw TEXT,
                phonetic TEXT,
                definition TEXT,
                translation TEXT,
                pos TEXT,
                collins TEXT,
                oxford TEXT,
                tag TEXT,
                bnc TEXT,
                frq TEXT,
                exchange TEXT,
                detail TEXT,
                audio TEXT
            )
        ''')
        # 插入一些常用单词作为示例
        sample_words = [
            ("hello", "hello", "həˈloʊ", "used as a greeting", "你好；喂", "int.", "1", "3000", "zk gk", "100", "100", "", "", ""),
            ("world", "world", "wɜːrld", "the earth and all the people and things on it", "世界；地球", "n.", "1", "3000", "zk gk", "100", "100", "worlds", "", ""),
            ("apple", "apple", "ˈæpl", "a round fruit with red or green skin", "苹果", "n.", "1", "3000", "gk", "100", "100", "apples", "", ""),
            ("book", "book", "bʊk", "a set of printed pages", "书；书籍", "n.", "1", "3000", "zk gk", "100", "100", "books/booked/booking", "", ""),
            ("computer", "computer", "kəmˈpjuːtər", "an electronic machine", "计算机；电脑", "n.", "2", "3000", "gk", "100", "100", "computers", "", ""),
            ("water", "water", "ˈwɔːtər", "the clear liquid", "水", "n.", "1", "3000", "zk gk", "100", "100", "waters/watered/watering", "", ""),
            ("food", "food", "fuːd", "things that people eat", "食物", "n.", "1", "3000", "zk gk", "100", "100", "foods", "", ""),
            ("time", "time", "taɪm", "the thing that is measured in minutes, hours, days", "时间", "n.", "1", "3000", "zk gk", "100", "100", "times/timed/timing", "", ""),
            ("love", "love", "lʌv", "a strong feeling of affection", "爱；热爱", "n.", "1", "3000", "zk gk", "100", "100", "loves/loved/loving", "", ""),
            ("friend", "friend", "frend", "a person you know well", "朋友", "n.", "1", "3000", "zk gk", "100", "100", "friends", "", ""),
            ("work", "work", "wɜːrk", "activity involving mental or physical effort", "工作", "n.", "1", "3000", "zk gk", "100", "100", "works/worked/working", "", ""),
            ("study", "study", "ˈstʌdi", "the activity of learning", "学习；研究", "n.", "1", "3000", "zk gk", "100", "100", "studies/studied/studying", "", ""),
            ("school", "school", "skuːl", "a place where children go to learn", "学校", "n.", "1", "3000", "zk gk", "100", "100", "schools", "", ""),
            ("family", "family", "ˈfæməli", "a group of people related to each other", "家庭；家人", "n.", "1", "3000", "zk gk", "100", "100", "families", "", ""),
            ("happy", "happy", "ˈhæpi", "feeling pleasure and enjoyment", "快乐的；幸福的", "adj.", "1", "3000", "zk gk", "100", "100", "happier/happiest", "", ""),
        ]
        cursor.executemany('''
            INSERT OR IGNORE INTO stardict
            (word, sw, phonetic, definition, translation, pos, collins, oxford, tag, bnc, frq, exchange, detail, audio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_words)
        conn.commit()
        conn.close()
        print("已创建简化版词典（示例数据）")

    def _connect(self) -> None:
        """连接词典数据库，优先完整版"""
        dict_path = FULL_DICT_PATH if os.path.exists(FULL_DICT_PATH) else DICT_PATH
        if os.path.exists(dict_path):
            self.conn = sqlite3.connect(dict_path)
            self.conn.row_factory = sqlite3.Row

    def lookup(self, word: str) -> DictionaryLookup:
        """查询单词"""
        if not self.conn:
            return None
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM stardict WHERE word = ? COLLATE NOCASE', (word,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        # 尝试模糊匹配
        cursor.execute('SELECT * FROM stardict WHERE word LIKE ? LIMIT 5', (word + '%',))
        rows = cursor.fetchall()
        return [dict(r) for r in rows] if rows else None

    def search(self, keyword: str) -> list[DictionaryEntry]:
        """搜索单词"""
        if not self.conn:
            return []
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT word, phonetic, translation FROM stardict WHERE word LIKE ? LIMIT 20',
            ('%' + keyword + '%',)
        )
        return [dict(r) for r in cursor.fetchall()]

    def get_random_words(self, count: int = 10) -> list[DictionaryEntry]:
        """获取随机单词"""
        if not self.conn:
            return []
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT word, phonetic, translation, definition FROM stardict ORDER BY RANDOM() LIMIT ?',
            (count,)
        )
        return [dict(r) for r in cursor.fetchall()]

    def close(self) -> None:
        if self.conn:
            self.conn.close()
