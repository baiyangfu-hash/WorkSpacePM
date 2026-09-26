"""
学习服务模块 - 封装单词学习、FSRS-4 间隔复习与统计数据业务逻辑
"""
from datetime import datetime
from typing import TypedDict

from fsrs_engine import FSRSEngine, FSRSState

from .database_manager import DatabaseManager, get_db


class ReviewResult(TypedDict):
    word: str
    status: str
    interval: int
    due_date: datetime


class DailyStats(TypedDict):
    date: str
    new_words: int
    review_words: int
    study_minutes: int
    correct_count: int
    total_count: int


class StudyService:
    def __init__(self, db_manager: DatabaseManager | None = None) -> None:
        self.db = db_manager or get_db()
        self.fsrs = FSRSEngine()

    def get_or_create_word(self, word: str) -> dict[str, object]:
        """获取或创建用户单词记录"""
        with self.db.session() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM user_words WHERE word = ?', (word,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            cursor.execute(
                'INSERT INTO user_words (word, status) VALUES (?, ?)',
                (word, 'new')
            )
            return {'word': word, 'status': 'new', 'fsrs_state': None, 'due_date': None}

    def record_review(self, word: str, rating: str, study_minutes: int = 0) -> ReviewResult:
        """记录一次卡片复习结果并根据 FSRS 算法更新状态"""
        word_record = self.get_or_create_word(word)
        raw_state = word_record.get('fsrs_state')
        current_state = FSRSState.from_json(raw_state) if isinstance(raw_state, str) else FSRSState()

        new_state, due_date = self.fsrs.review(current_state, rating)
        interval = new_state.scheduled_days

        # 映射 rating 到业务操作
        status = 'review' if rating in ['good', 'easy'] else 'learning'

        with self.db.session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE user_words SET status = ?, fsrs_state = ?, due_date = ?, updated_at = CURRENT_TIMESTAMP WHERE word = ?',
                (status, new_state.to_json(), due_date.isoformat(), word)
            )
            cursor.execute(
                'INSERT INTO study_records (word, action, result) VALUES (?, ?, ?)',
                (word, 'review', rating)
            )

            # 更新每日统计
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute('INSERT OR IGNORE INTO daily_stats (date) VALUES (?)', (today,))
            is_correct = 1 if rating in ['good', 'easy'] else 0
            cursor.execute(
                'UPDATE daily_stats SET review_words = review_words + 1, study_minutes = study_minutes + ?, correct_count = correct_count + ?, total_count = total_count + 1 WHERE date = ?',
                (study_minutes, is_correct, today)
            )

        return {
            'word': word,
            'status': status,
            'interval': interval,
            'due_date': due_date
        }

    def get_due_words(self, limit: int = 50) -> list[dict[str, object]]:
        """获取到期待复习单词"""
        now = datetime.now().isoformat()
        with self.db.session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM user_words WHERE due_date IS NULL OR due_date <= ? ORDER BY due_date LIMIT ?',
                (now, limit)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_daily_stats(self, date: str | None = None) -> DailyStats:
        """获取指定日期的学习统计数据"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        with self.db.session() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM daily_stats WHERE date = ?', (date,))
            row = cursor.fetchone()
            if row:
                return {
                    'date': str(row['date']),
                    'new_words': int(row['new_words']),
                    'review_words': int(row['review_words']),
                    'study_minutes': int(row['study_minutes']),
                    'correct_count': int(row['correct_count']),
                    'total_count': int(row['total_count']),
                }
            return {'date': date, 'new_words': 0, 'review_words': 0, 'study_minutes': 0, 'correct_count': 0, 'total_count': 0}
