"""
服务层单元测试 - 验证 StudyService, DictionaryService, GrammarService, CourseService, DatabaseManager
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import cefr_tagger
import course_manager
import services.database_manager as database_manager
from services import (
    CourseService,
    DatabaseManager,
    DictionaryService,
    GrammarService,
    StudyService,
    get_db,
)


class TestServiceLayer(unittest.TestCase):
    _temporary_directory: tempfile.TemporaryDirectory[str]
    _database_path: str
    _original_database_path: str
    _original_cefr_database_path: str
    _original_course_database_path: str
    _original_database_manager: DatabaseManager | None

    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary_directory = tempfile.TemporaryDirectory()
        cls._database_path = str(Path(cls._temporary_directory.name) / 'app.db')
        cls._original_database_path = database_manager.DB_PATH
        cls._original_cefr_database_path = cefr_tagger.DB_PATH
        cls._original_course_database_path = course_manager.DB_PATH
        cls._original_database_manager = database_manager._db_manager_instance
        database_manager._db_manager_instance = None
        database_manager.DB_PATH = cls._database_path
        cefr_tagger.DB_PATH = cls._database_path
        course_manager.DB_PATH = cls._database_path

    @classmethod
    def tearDownClass(cls) -> None:
        manager = database_manager._db_manager_instance
        if manager is not None:
            manager.close()
        database_manager._db_manager_instance = cls._original_database_manager
        database_manager.DB_PATH = cls._original_database_path
        cefr_tagger.DB_PATH = cls._original_cefr_database_path
        course_manager.DB_PATH = cls._original_course_database_path
        cls._temporary_directory.cleanup()

    def setUp(self) -> None:
        self.db_manager = get_db()

    def test_database_manager(self) -> None:
        self.assertIsInstance(self.db_manager, DatabaseManager)
        with self.db_manager.session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row['name'] for row in cursor.fetchall()]
            self.assertIn('user_words', tables)
            self.assertIn('study_records', tables)
            self.assertIn('daily_stats', tables)

    def test_dictionary_service(self) -> None:
        service = DictionaryService()
        res = service.lookup("apple")
        self.assertIsInstance(res, dict)
        if not isinstance(res, dict):
            self.fail("apple lookup must return one dictionary entry")
        self.assertIn('cefr_level', res)
        self.assertEqual(res['cefr_level'], 'A1')

        # 边界与入参清洗测试（空格修剪、空字符串、None、非字符串等）
        # 1. 验证前后空格输入清洗 lookup('  apple  ')
        res_spaces = service.lookup("  apple  ")
        self.assertIsInstance(res_spaces, dict)
        if not isinstance(res_spaces, dict):
            self.fail("trimmed apple lookup must return one dictionary entry")
        self.assertEqual(res_spaces['word'], 'apple')
        self.assertEqual(res_spaces['cefr_level'], 'A1')

        # 2. 验证空字符串与仅空格输入安全返回 None，杜绝异常
        self.assertIsNone(service.lookup(""))
        self.assertIsNone(service.lookup("   \t\n  "))
        self.assertIsNone(service.lookup(None))
        self.assertIsNone(service.lookup(12345))

        # 3. 验证 query_word 接口及参数清洗
        q_res = service.query_word("  apple  ")
        self.assertIsInstance(q_res, dict)
        if not isinstance(q_res, dict):
            self.fail("apple query must return one dictionary entry")
        self.assertEqual(q_res['word'], 'apple')
        self.assertIsNone(service.query_word(""))
        self.assertIsNone(service.query_word("   "))
        self.assertIsNone(service.query_word(None))

        # 4. 验证 search 前缀搜索清洗
        search_res = service.search("  app  ")
        self.assertIsInstance(search_res, list)
        self.assertEqual(service.search(""), [])
        self.assertEqual(service.search("   "), [])
        self.assertEqual(service.search(None), [])

        # 5. 验证静态辅助方法 sanitize_word
        self.assertEqual(DictionaryService.sanitize_word("  hello  "), "hello")
        self.assertEqual(DictionaryService.sanitize_word(""), "")
        self.assertEqual(DictionaryService.sanitize_word("   "), "")
        self.assertEqual(DictionaryService.sanitize_word(None), "")
        self.assertEqual(DictionaryService.sanitize_word(123), "")

        service.close()

    def test_study_service(self) -> None:
        import time
        test_word = f"service_test_word_{time.time_ns()}"
        service = StudyService(self.db_manager)
        word_record = service.get_or_create_word(test_word)
        self.assertEqual(word_record['word'], test_word)
        self.assertEqual(word_record['status'], 'new')

        res = service.record_review(test_word, "good", study_minutes=5)
        self.assertEqual(res['word'], test_word)
        self.assertEqual(res['status'], 'review')

        stats = service.get_daily_stats()
        self.assertGreaterEqual(stats['study_minutes'], 5)

    def test_grammar_service(self) -> None:
        service = GrammarService()
        points = service.get_points_by_level("A1")
        self.assertGreater(len(points), 0)

        practice = service.generate_practice(points[0])
        self.assertGreaterEqual(len(practice), 1)

    def test_course_service(self) -> None:
        service = CourseService(self.db_manager)
        progress = service.get_user_progress()
        self.assertIn('current_level', progress)

        plan = service.generate_daily_plan()
        self.assertIn('tasks', plan)
        self.assertIn('estimated_minutes', plan)

        # 1. 正常合法等级设置（如 'B2'，验证返回的 current_level 为 'B2'）
        res_b2 = service.set_user_level("B2")
        self.assertEqual(res_b2.get("current_level"), "B2")
        self.assertEqual(service.get_user_progress().get("current_level"), "B2")

        # 2. 带有空格与小写的等级输入（如 '  b1  '，验证清洗后生效为 'B1'）
        res_b1 = service.set_user_level("  b1  ")
        self.assertEqual(res_b1.get("current_level"), "B1")
        self.assertEqual(service.get_user_progress().get("current_level"), "B1")

        # 3. 非法等级字符串（如 'XYZ'，验证兜底回退为 'A1'）
        res_invalid = service.set_user_level("XYZ")
        self.assertEqual(res_invalid.get("current_level"), "A1")
        self.assertEqual(service.get_user_progress().get("current_level"), "A1")

        # 4. 异常类型与边界输入（如 None, 123, ""，验证不崩溃并安全兜底为 'A1'）
        res_none = service.set_user_level(None)
        self.assertEqual(res_none.get("current_level"), "A1")
        res_num = service.set_user_level(123)
        self.assertEqual(res_num.get("current_level"), "A1")
        res_empty = service.set_user_level("")
        self.assertEqual(res_empty.get("current_level"), "A1")
        res_spaces = service.set_user_level("   \t\n  ")
        self.assertEqual(res_spaces.get("current_level"), "A1")

        # 5. 单元测试 CourseService.sanitize_level 静态方法
        self.assertEqual(CourseService.VALID_CEFR_LEVELS, ("A1", "A2", "B1", "B2", "C1", "C2"))
        self.assertEqual(CourseService.sanitize_level("b2"), "B2")
        self.assertEqual(CourseService.sanitize_level("  c1  "), "C1")
        self.assertEqual(CourseService.sanitize_level("A1"), "A1")
        self.assertEqual(CourseService.sanitize_level("XYZ"), "A1")
        self.assertEqual(CourseService.sanitize_level(""), "A1")
        self.assertEqual(CourseService.sanitize_level("   "), "A1")
        self.assertEqual(CourseService.sanitize_level(None), "A1")
        self.assertEqual(CourseService.sanitize_level(123), "A1")
        self.assertEqual(CourseService.sanitize_level([], default="B1"), "B1")
        self.assertEqual(CourseService.sanitize_level("unknown", default="B2"), "B2")

    def test_course_roadmap_and_progress_wiring(self) -> None:
        service = CourseService(self.db_manager)
        roadmap = service.get_roadmap()
        self.assertIn('phase1', roadmap)
        self.assertIn('phase2', roadmap)
        before = service.get_user_progress()
        service.update_progress(vocab_count=2, grammar_count=1)
        after = service.get_user_progress()
        self.assertEqual(after['vocab_mastered'], before['vocab_mastered'] + 2)
        self.assertEqual(after['grammar_completed'], before['grammar_completed'] + 1)


class TestDictionarySearchLimits(unittest.TestCase):
    def setUp(self) -> None:
        self.service = DictionaryService.__new__(DictionaryService)
        self.dictionary_mock = Mock()
        self.cefr_mock = Mock()
        self.service.dict_engine = self.dictionary_mock
        self.service.cefr_tagger = self.cefr_mock
        self.cefr_mock.get_level.return_value = 'A1'
        self.dictionary_mock.search.side_effect = lambda prefix: [
            {'word': f'{prefix}{index}'} for index in range(25)
        ]

    def test_search_normalizes_limit_to_one_through_twenty(self) -> None:
        cases = (
            (None, 20),
            (0, 1),
            (-5, 1),
            (1, 1),
            (20, 20),
            (21, 20),
            ('3', 3),
            ('invalid', 20),
            (True, 20),
        )
        for limit, expected_count in cases:
            with self.subTest(limit=limit):
                self.cefr_mock.get_level.reset_mock()
                results = self.service.search('  app  ', limit=limit)
                self.dictionary_mock.search.assert_called_with('app')
                self.assertEqual(len(results), expected_count)
                self.assertEqual(
                    [item['word'] for item in results],
                    [f'app{index}' for index in range(expected_count)],
                )
                self.assertTrue(all(item['cefr_level'] == 'A1' for item in results))
                self.assertEqual(
                    self.cefr_mock.get_level.call_count, expected_count
                )

    def test_search_default_limit_and_empty_prefix(self) -> None:
        self.assertEqual(len(self.service.search('app')), 20)
        self.dictionary_mock.search.reset_mock()
        self.assertEqual(self.service.search('  ', limit=0), [])
        self.dictionary_mock.search.assert_not_called()


if __name__ == '__main__':
    unittest.main()
