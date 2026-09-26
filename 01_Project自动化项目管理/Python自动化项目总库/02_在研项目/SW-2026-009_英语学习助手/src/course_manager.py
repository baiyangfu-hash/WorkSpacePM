"""
课程管理模块 - 课程大纲管理、每日学习计划生成、进度追踪
"""
import os
import sqlite3
from datetime import datetime
from typing import TypedDict

import cefr_tagger
from cefr_tagger import (
    CEFR_LEVELS,
    get_user_level_progress,
    get_vocab_count_by_level,
    get_words_by_level,
)

DB_PATH = cefr_tagger.DB_PATH

class UserProgress(TypedDict):
    current_level: str
    target_level: str
    vocab_mastered: int
    grammar_completed: int
    total_days: int
    streak_days: int
    vocab_target: int
    vocab_percent: float
    grammar_total: int
    grammar_percent: float
    start_date: str


def _integer(value: object) -> int:
    return value if isinstance(value, int) else 0


class CourseManager:
    """课程管理器"""

    def __init__(self) -> None:
        self._ensure_db()

    def _ensure_db(self) -> None:
        """确保数据库表存在"""
        if not os.path.exists(DB_PATH):
            return
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # CEFR 等级定义
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cefr_levels (
                level TEXT PRIMARY KEY,
                label TEXT,
                word_target INTEGER,
                description TEXT,
                order_num INTEGER
            )
        ''')

        # 课程大纲
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS course_outline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week INTEGER NOT NULL,
                cefr_level TEXT NOT NULL,
                vocab_target INTEGER DEFAULT 0,
                grammar_topics TEXT,
                dialog_ids TEXT,
                reading_ids TEXT,
                daily_minutes INTEGER DEFAULT 30,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 等级测试
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS level_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_type TEXT NOT NULL,
                cefr_level TEXT NOT NULL,
                questions TEXT,
                passing_score REAL DEFAULT 70,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 用户等级进度
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_level_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                current_level TEXT DEFAULT 'A1',
                target_level TEXT DEFAULT 'B1',
                start_date TEXT,
                vocab_mastered INTEGER DEFAULT 0,
                grammar_completed INTEGER DEFAULT 0,
                total_days INTEGER DEFAULT 0,
                streak_days INTEGER DEFAULT 0,
                last_study_date TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 初始化 CEFR 等级数据
        cursor.execute('SELECT COUNT(*) FROM cefr_levels')
        if cursor.fetchone()[0] == 0:
            for level, info in CEFR_LEVELS.items():
                cursor.execute(
                    'INSERT INTO cefr_levels (level, label, word_target, description, order_num) VALUES (?, ?, ?, ?, ?)',
                    (level, info['label'], info['word_target'], info['description'], info['order'])
                )

        # 初始化用户进度
        cursor.execute('SELECT COUNT(*) FROM user_level_progress')
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                'INSERT INTO user_level_progress (current_level, target_level, start_date, streak_days) VALUES (?, ?, ?, ?)',
                ('A1', 'B1', datetime.now().strftime('%Y-%m-%d'), 0)
            )

        conn.commit()
        conn.close()

    def get_levels(self) -> list[dict[str, object]]:
        """获取所有 CEFR 等级信息"""
        if not os.path.exists(DB_PATH):
            return []
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT * FROM cefr_levels ORDER BY order_num')
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def set_user_level(self, level: str) -> UserProgress:
        """设置当前用户 CEFR 等级 (A1, A2, B1, B2, C1, C2)"""
        level = level.upper().strip()
        if level not in CEFR_LEVELS:
            level = 'A1'
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    UPDATE user_level_progress SET current_level = ?, updated_at = CURRENT_TIMESTAMP
                ''', (level,))
                if cursor.rowcount == 0:
                    cursor.execute('''
                        INSERT INTO user_level_progress (current_level, target_level, start_date, streak_days) VALUES (?, ?, ?, ?)
                    ''', (level, 'B1', datetime.now().strftime('%Y-%m-%d'), 0))
                conn.commit()
            except sqlite3.OperationalError:
                pass
            finally:
                conn.close()
        return self.get_user_progress()

    def get_user_progress(self) -> UserProgress:
        """获取用户等级进度"""
        progress = get_user_level_progress(DB_PATH)
        if not progress:
            return {
                'current_level': 'A1',
                'target_level': 'B1',
                'vocab_mastered': 0,
                'grammar_completed': 0,
                'total_days': 0,
                'streak_days': 0,
                'vocab_target': 500,
                'vocab_percent': 0,
                'grammar_total': 0,
                'grammar_percent': 0,
                'start_date': '',
            }

        # 计算百分比
        raw_level = progress.get('current_level', 'A1')
        level = raw_level if isinstance(raw_level, str) else 'A1'
        level_info = CEFR_LEVELS.get(level, CEFR_LEVELS['A1'])
        vocab_target = level_info['word_target']
        vocab_mastered = _integer(progress.get('vocab_mastered', 0))

        # 语法完成数
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        grammar_total = 0
        try:
            # 统计当前等级及以下所有语法点
            cursor.execute('SELECT COUNT(*) FROM grammar_points WHERE cefr_level = ?', (level,))
            grammar_total = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            pass
        conn.close()

        grammar_completed = _integer(progress.get('grammar_completed', 0))

        return {
            'current_level': level,
            'target_level': str(progress.get('target_level', 'B1')),
            'vocab_mastered': vocab_mastered,
            'grammar_completed': grammar_completed,
            'total_days': _integer(progress.get('total_days', 0)),
            'streak_days': _integer(progress.get('streak_days', 0)),
            'vocab_target': vocab_target,
            'vocab_percent': min(round(vocab_mastered / vocab_target * 100, 1) if vocab_target > 0 else 0, 100),
            'grammar_total': grammar_total,
            'grammar_percent': min(round(grammar_completed / grammar_total * 100, 1) if grammar_total > 0 else 0, 100),
            'start_date': str(progress.get('start_date') or ''),
        }

    def get_daily_plan(self) -> dict[str, object]:
        """生成每日学习计划"""
        progress = self.get_user_progress()
        level = progress['current_level']
        vocab_done = progress['vocab_mastered']
        grammar_done = progress['grammar_completed']

        # 每日词汇目标：根据等级调整
        daily_new_words = 10  # 基础

        # 获取到期复习的单词
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        due_review = 0
        try:
            now = datetime.now().isoformat()
            cursor.execute('SELECT COUNT(*) as cnt FROM user_words WHERE due_date <= ?', (now,))
            row = cursor.fetchone()
            due_review = row['cnt'] if row else 0
        except sqlite3.OperationalError:
            pass
        conn.close()

        # 今日任务
        plan = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'level': level,
            'level_label': CEFR_LEVELS[level]['label'] if level in CEFR_LEVELS else level,
            'tasks': [
                {
                    'type': 'vocab_new',
                    'title': '新词学习',
                    'description': f'学习 {daily_new_words} 个{level}级新单词',
                    'target': daily_new_words,
                    'icon': '📝',
                },
                {
                    'type': 'vocab_review',
                    'title': '单词复习',
                    'description': f'复习 {due_review} 个到期单词',
                    'target': due_review,
                    'icon': '🔄',
                },
                {
                    'type': 'grammar',
                    'title': '语法学习',
                    'description': '学习一个语法知识点',
                    'target': 1,
                    'icon': '📖',
                },
                {
                    'type': 'dialog',
                    'title': '情景对话',
                    'description': '阅读并练习一个场景对话',
                    'target': 1,
                    'icon': '💬',
                },
                {
                    'type': 'dictation',
                    'title': '听写练习',
                    'description': '完成 10 题听写练习',
                    'target': 10,
                    'icon': '🎧',
                },
            ],
            'estimated_minutes': 45,
            'vocab_progress': {
                'mastered': vocab_done,
                'target': CEFR_LEVELS[level]['word_target'] if level in CEFR_LEVELS else 500,
            },
            'grammar_progress': {
                'completed': grammar_done,
                'total': progress['grammar_total'],
            },
        }

        return plan

    def get_6month_roadmap(self) -> dict[str, object]:
        """获取 6 个月学习路线图"""
        roadmap: dict[str, object] = {
            'phase1': {
                'title': '第一阶段：A1 巩固 + A2 冲刺',
                'months': '第 1-3 个月',
                'months_detail': [
                    {
                        'month': 1,
                        'title': 'A1 巩固',
                        'vocab_target': '累计 700 词',
                        'grammar_focus': 'Present Simple, Past Simple, Can/Can\'t, Wh-Questions',
                        'dialogs': '基础场景对话（餐厅/机场/酒店/购物）',
                        'daily_minutes': 30,
                    },
                    {
                        'month': 2,
                        'title': 'A2 起步',
                        'vocab_target': '累计 1000 词',
                        'grammar_focus': 'Present Perfect, Future will/going to, Must/Should',
                        'dialogs': '美国出差场景（超市/交通/问路/日常）',
                        'daily_minutes': 40,
                    },
                    {
                        'month': 3,
                        'title': 'A2 冲刺',
                        'vocab_target': 'A2 达标 1500 词',
                        'grammar_focus': '被动语态, 条件句, 连词, 介词搭配',
                        'dialogs': '复杂场景 + 短文阅读',
                        'daily_minutes': 45,
                    },
                ],
            },
            'phase2': {
                'title': '第二阶段：A2 巩固 + B1 冲刺',
                'months': '第 4-6 个月',
                'months_detail': [
                    {
                        'month': 4,
                        'title': 'B1 起步',
                        'vocab_target': '累计 2000 词',
                        'grammar_focus': 'Present Perfect vs Past Simple, Second Conditional, Reported Speech',
                        'dialogs': '工作场景 + 新闻短文',
                        'daily_minutes': 45,
                    },
                    {
                        'month': 5,
                        'title': 'B1 积累',
                        'vocab_target': '累计 2500 词',
                        'grammar_focus': 'Relative Clauses, Passive 全部时态, 情态动词',
                        'dialogs': '商务场景 + 中等长度文章',
                        'daily_minutes': 50,
                    },
                    {
                        'month': 6,
                        'title': 'B1 冲刺',
                        'vocab_target': 'B1 达标 3000 词',
                        'grammar_focus': '综合复习, 薄弱环节强化',
                        'dialogs': '综合场景 + B1 级阅读',
                        'daily_minutes': 60,
                    },
                ],
            },
        }
        return roadmap

    def update_study_progress(self, vocab_count: int = 0, grammar_count: int = 0) -> None:
        """更新学习进度"""
        if not os.path.exists(DB_PATH):
            return
        today = datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT * FROM user_level_progress ORDER BY id DESC LIMIT 1')
            row = cursor.fetchone()
            if row:
                # 更新进度
                cursor.execute('''
                    UPDATE user_level_progress
                    SET vocab_mastered = vocab_mastered + ?,
                        grammar_completed = grammar_completed + ?,
                        total_days = total_days + 1,
                        last_study_date = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (vocab_count, grammar_count, today, row[0]))
            else:
                cursor.execute('''
                    INSERT INTO user_level_progress (current_level, target_level, vocab_mastered, grammar_completed, total_days, last_study_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', ('A1', 'B1', vocab_count, grammar_count, 1, today))
        except sqlite3.OperationalError:
            pass

        conn.commit()
        conn.close()

    def get_vocab_stats_by_level(self) -> dict[str, int]:
        """获取各等级词汇统计"""
        return get_vocab_count_by_level()

    def get_words_for_study(self, level: str, count: int = 10) -> list[dict[str, object]]:
        """获取指定等级的学习词汇"""
        return get_words_by_level(level, count)


def init_course_system() -> UserProgress:
    """初始化课程系统（首次使用）"""
    mgr = CourseManager()
    return mgr.get_user_progress()
