"""
词典服务模块 - 封装离线 ECDICT 查询、模糊搜索与 CEFR 等级标注
"""
from cefr_tagger import CEFRTagger
from dictionary import Dictionary, DictionaryEntry, DictionaryLookup


class DictionaryService:
    def __init__(self) -> None:
        self.dict_engine = Dictionary()
        self.cefr_tagger = CEFRTagger()

    @staticmethod
    def sanitize_word(query: object) -> str:
        """入参清洗防御：去除首尾空白字符，若为空或非字符串则安全返回空字符串"""
        if not query or not isinstance(query, str):
            return ""
        return query.strip()

    def lookup(self, word: object) -> DictionaryLookup:
        """精准查询单词信息，附带入参清洗防御与 CEFR 等级标注"""
        cleaned = self.sanitize_word(word)
        if not cleaned:
            return None
        result = self.dict_engine.lookup(cleaned)
        if result:
            if isinstance(result, dict):
                lvl = self.cefr_tagger.get_level(cleaned)
                result['cefr_level'] = lvl.upper() if lvl else None
            elif isinstance(result, list):
                for item in result:
                    item_word = item.get('word')
                    if isinstance(item_word, str):
                        lvl = self.cefr_tagger.get_level(item_word)
                        item['cefr_level'] = lvl.upper() if lvl else None
        return result

    def query_word(self, query: object) -> DictionaryLookup:
        """查询单词信息，附带入参清洗防御与 CEFR 标注"""
        cleaned = self.sanitize_word(query)
        if not cleaned:
            return None
        return self.lookup(cleaned)

    @staticmethod
    def normalize_search_limit(limit: object) -> int:
        """将搜索结果上限限制在 1 到 20，无法解析时使用默认值 20。"""
        if isinstance(limit, bool) or not isinstance(limit, (int, float, str)):
            return 20
        try:
            normalized = int(limit)
        except (TypeError, ValueError, OverflowError):
            return 20
        return max(1, min(normalized, 20))

    def search(self, prefix: object, limit: object = 20) -> list[DictionaryEntry]:
        """前缀模糊搜索，限制结果数量并标注 CEFR 等级。"""
        cleaned = self.sanitize_word(prefix)
        if not cleaned:
            return []
        results = self.dict_engine.search(cleaned)
        results = results[:self.normalize_search_limit(limit)]
        for item in results:
            item_word = item.get('word')
            if isinstance(item_word, str):
                item['cefr_level'] = self.cefr_tagger.get_level(item_word)
        return results

    def get_random_words(
        self, count: int = 5, level: object | None = None
    ) -> list[DictionaryEntry]:
        """获取随机单词列表"""
        del level
        words = self.dict_engine.get_random_words(count)
        for w in words:
            item_word = w.get('word')
            if isinstance(item_word, str):
                w['cefr_level'] = self.cefr_tagger.get_level(item_word)
        return words

    def close(self) -> None:
        self.dict_engine.close()
