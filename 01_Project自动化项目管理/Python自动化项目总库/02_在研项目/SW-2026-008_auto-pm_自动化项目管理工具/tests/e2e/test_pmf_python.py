"""Run the SW-009 dictionary prefix search in a fresh Python process."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class TestDictionaryPrefixSearchPython(unittest.TestCase):
    def test_real_dictionary_search_limit_and_cefr(self) -> None:
        project = Path(__file__).resolve().parents[3] / 'SW-2026-009_英语学习助手'
        source = project / 'src'
        self.assertTrue((source / 'services' / 'dictionary_service.py').is_file())

        script = '''
import json
from typing import Any
from services.dictionary_service import DictionaryService

service = DictionaryService()
try:
    def summarize(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                'word': item.get('word'),
                'cefr_level': item.get('cefr_level'),
                'has_cefr_level': 'cefr_level' in item,
            }
            for item in results
        ]

    result = {
        'low': summarize(service.search('  apple  ', limit=0)),
        'high': summarize(service.search('  a  ', limit=99)),
        'apple': summarize(service.search('apple')),
        'lookup_level': service.lookup('apple')['cefr_level'],
    }
    print('PREFIX_SEARCH_RESULT=' + json.dumps(result))
finally:
    service.close()
'''
        environment = os.environ.copy()
        environment['PYTHONPATH'] = os.pathsep.join(
            filter(None, (str(source), environment.get('PYTHONPATH')))
        )
        completed = subprocess.run(
            [sys.executable, '-c', script],
            cwd=project,
            env=environment,
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=60,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result_lines = [
            line.removeprefix('PREFIX_SEARCH_RESULT=')
            for line in completed.stdout.splitlines()
            if line.startswith('PREFIX_SEARCH_RESULT=')
        ]
        self.assertEqual(len(result_lines), 1, completed.stdout)
        result = json.loads(result_lines[0])

        self.assertEqual(len(result['low']), 1)
        self.assertLessEqual(len(result['high']), 20)
        self.assertTrue(result['high'])
        self.assertTrue(all(item['has_cefr_level'] for item in result['high']))
        apple = next(item for item in result['apple'] if item['word'] == 'apple')
        self.assertTrue(apple['has_cefr_level'])
        self.assertEqual(apple['cefr_level'].upper(), result['lookup_level'])
        self.assertEqual(result['low'][0], result['apple'][0])


if __name__ == '__main__':
    unittest.main()
