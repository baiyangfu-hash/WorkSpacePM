"""
语法练习生成引擎 - 基于语法知识点自动生成练习题
高内聚低耦合：仅依赖 grammar_engine 的数据，不依赖 UI
"""
import random
from typing import TypedDict

from grammar_engine import GrammarCategory, GrammarEngine, GrammarLevel


class GrammarExercise(TypedDict):
    type: str
    question: str
    options: list[str]
    answer: str
    hint: str


class GrammarPracticeEngine:
    """语法练习生成引擎"""

    def __init__(self) -> None:
        self.grammar_engine = GrammarEngine()

    def get_levels(self) -> list[GrammarLevel]:
        """获取可用等级"""
        return self.grammar_engine.get_all_levels()

    def get_categories(self, level: str) -> list[GrammarCategory]:
        """获取指定等级的语法分类"""
        return self.grammar_engine.get_categories_by_level(level)

    def get_points(self, level: str) -> list[dict[str, object]]:
        """获取指定等级的所有语法点"""
        return self.grammar_engine.get_points_by_level(level)

    def get_point(self, point_id: int) -> dict[str, object] | None:
        """获取指定语法点"""
        return self.grammar_engine.get_point_by_id(point_id)

    def generate_exercises(self, point: dict[str, object]) -> list[GrammarExercise]:
        """
        为语法点生成练习题
        返回列表，每项为 dict: {type, question, options, answer, hint}
        练习类型：fill(填空), choice(选择), correct(改错), order(排序)
        """
        exercises: list[GrammarExercise] = []
        name = point.get('name', '')
        raw_examples = point.get('examples', [])
        examples = [item for item in raw_examples if isinstance(item, str)] if isinstance(raw_examples, list) else []
        explanation = point.get('explanation', '')
        category = point.get('category', '')
        name = name if isinstance(name, str) else ''
        explanation = explanation if isinstance(explanation, str) else ''
        category = category if isinstance(category, str) else ''

        # 根据语法点特征生成不同类型练习
        generated: set[str] = set()

        # 1. 填空题（从例句生成）
        for ex in examples:
            if len(ex) < 10:
                continue
            exs = self._make_fill_blank(ex, name, explanation)
            if exs and exs['answer'] not in generated:
                exercises.append(exs)
                generated.add(exs['answer'])

        # 2. 选择题（语法概念）
        choice = self._make_choice_question(name, explanation, category)
        if choice:
            exercises.append(choice)

        # 3. 改错题
        for ex in examples:
            if len(ex) > 15:
                wrong = self._make_correct_question(ex, name)
                if wrong and wrong['answer'] not in generated:
                    exercises.append(wrong)
                    generated.add(wrong['answer'])
                    break  # 每个语法点最多一个改错题

        # 4. 排序题
        for ex in examples:
            if len(ex.split()) >= 4:
                order = self._make_order_question(ex)
                if order and order['answer'] not in generated:
                    exercises.append(order)
                    generated.add(order['answer'])
                    break

        return exercises[:5]  # 最多 5 题

    def _make_fill_blank(self, sentence: str, grammar_name: str, explanation: str) -> GrammarExercise | None:
        """生成填空题"""
        words = sentence.split()
        if len(words) < 4:
            return None

        # 策略：根据语法名称确定要挖空的词
        blank_word = None
        blank_idx = None

        grammar_lower = grammar_name.lower()

        # 时态相关：挖动词
        if any(kw in grammar_lower for kw in ['present', 'past', 'future', 'perfect', 'continuous', 'going to', 'will', 'used to']):
            for i, w in enumerate(words):
                wl = w.strip('.,!?;:')
                # 跳过主语位置
                if i <= 1:
                    continue
                if wl in ['is', 'am', 'are', 'was', 'were', 'have', 'has', 'had', 'will', 'been', 'being', 'going', 'to', 'do', 'does', 'did']:
                    blank_word = wl
                    blank_idx = i
                    break
            if blank_word is None:
                # 找第一个动词形态
                for i, w in enumerate(words[2:], 2):
                    wl = w.strip('.,!?;:')
                    if len(wl) > 2 and wl not in ['the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'with', 'and', 'but', 'or']:
                        blank_word = wl
                        blank_idx = i
                        break

        # 情态动词：挖情态动词
        elif any(kw in grammar_lower for kw in ['can', 'must', 'should', 'would', 'could', 'might', 'may', 'have to']):
            modals = ['can', "can't", 'must', "mustn't", 'should', "shouldn't", 'would', 'could', "couldn't", 'might', 'may', 'have', 'need']
            for i, w in enumerate(words):
                wl = w.strip('.,!?;:')
                if wl.lower() in modals or wl.lower() in ["don't", "doesn't", "didn't"]:
                    blank_word = wl
                    blank_idx = i
                    break

        # 疑问句：挖疑问词
        elif any(kw in grammar_lower for kw in ['question', 'wh-', 'how much', 'how many']):
            wh_words = ['what', 'where', 'when', 'why', 'who', 'how', 'which', 'whose']
            for i, w in enumerate(words):
                wl = w.strip('.,!?;:')
                if wl.lower() in wh_words or wl.lower().startswith('how'):
                    blank_word = wl
                    blank_idx = i
                    break

        # 冠词/介词/代词
        elif any(kw in grammar_lower for kw in ['article', 'a/an', 'pronoun', 'possessive', 'this', 'preposition']):
            targets = ['a', 'an', 'the', 'my', 'your', 'his', 'her', 'its', 'our', 'their', 'this', 'that', 'these', 'those', 'in', 'on', 'at', 'to', 'for', 'with']
            for i, w in enumerate(words):
                wl = w.strip('.,!?;:')
                if wl.lower() in targets:
                    blank_word = wl
                    blank_idx = i
                    break

        # 比较级
        elif any(kw in grammar_lower for kw in ['comparative', 'superlative']):
            for i, w in enumerate(words):
                wl = w.strip('.,!?;:')
                if wl.endswith('er') or wl.endswith('est') or wl == 'than' or wl == 'the':
                    blank_word = wl
                    blank_idx = i
                    break

        # 兜底：挖第 3 个词
        if blank_word is None and len(words) >= 4:
            blank_idx = min(2, len(words) - 2)
            blank_word = words[blank_idx].strip('.,!?;:')

        if blank_word is None or blank_idx is None:
            return None

        # 生成干扰项
        options = self._generate_fill_options(blank_word, grammar_name)
        blanked = ' '.join(words[:blank_idx]) + ' ______ ' + ' '.join(words[blank_idx + 1:])

        return {
            'type': 'fill',
            'question': blanked,
            'options': options,
            'answer': blank_word,
            'hint': explanation,
        }

    def _generate_fill_options(self, correct: str, grammar_name: str) -> list[str]:
        """生成填空题选项"""
        options = [correct]
        grammar_lower = grammar_name.lower()

        # 根据语法类型生成针对性干扰项
        if any(kw in grammar_lower for kw in ['present simple']):
            pool = ['is', 'am', 'are', 'was', 'were', 'do', 'does']
        elif any(kw in grammar_lower for kw in ['past simple']):
            pool = ['was', 'were', 'is', 'are', 'did', 'does']
        elif any(kw in grammar_lower for kw in ['present perfect']):
            pool = ['have', 'has', 'had', 'was', 'were']
        elif any(kw in grammar_lower for kw in ['present continuous']):
            pool = ['am', 'is', 'are', 'was', 'were']
        elif any(kw in grammar_lower for kw in ['can', 'must', 'should']):
            pool = ['can', "can't", 'must', 'should', 'would', 'could']
        elif any(kw in grammar_lower for kw in ['article']):
            pool = ['a', 'an', 'the', 'some', 'any']
        elif any(kw in grammar_lower for kw in ['preposition']):
            pool = ['in', 'on', 'at', 'to', 'for', 'with', 'by']
        elif any(kw in grammar_lower for kw in ['comparative']):
            pool = ['bigger', 'more big', 'biggest', 'most big']
        elif any(kw in grammar_lower for kw in ['superlative']):
            pool = ['the biggest', 'the most big', 'bigger', 'the big']
        else:
            pool = ['is', 'are', 'was', 'were', 'have', 'has', 'do', 'does', 'will', 'can']

        for w in pool:
            if w.lower() != correct.lower() and w not in options:
                options.append(w)
                if len(options) >= 4:
                    break

        while len(options) < 4:
            options.append('---')

        random.shuffle(options)
        return options[:4]

    def _make_choice_question(self, grammar_name: str, explanation: str, category: str) -> GrammarExercise:
        """生成语法概念选择题"""
        question = f"关于「{grammar_name}」，以下哪个说法是正确的？"

        correct = explanation
        # 生成干扰项
        wrong_options = [
            f"这个语法点属于{category}类别（但描述错误）",
            "这个语法点只在口语中使用",
            "这个语法点没有固定规则",
            "这个语法点已经过时，不再使用",
        ]

        options = [correct] + [w for w in wrong_options if w != correct][:3]
        while len(options) < 4:
            options.append("以上都不对")

        random.shuffle(options)

        return {
            'type': 'choice',
            'question': question,
            'options': options,
            'answer': correct,
            'hint': '',
        }

    def _make_correct_question(self, sentence: str, grammar_name: str) -> GrammarExercise | None:
        """生成改错题"""
        words = sentence.split()
        if len(words) < 5:
            return None

        grammar_lower = grammar_name.lower()

        # 制造一个常见错误
        wrong_sentence = sentence
        correct_word = None
        wrong_word = None

        if any(kw in grammar_lower for kw in ['present simple']):
            # he/she 后面用 is 而不是 are
            for i, w in enumerate(words):
                if w.strip('.,!?;:') == 'are' and i > 0:
                    prev = words[i - 1].strip('.,!?;:').lower()
                    if prev in ['he', 'she', 'it']:
                        wrong_word = 'are'
                        correct_word = 'is'
                        break
            if not wrong_word:
                # I 后面用 am 而不是 is
                for i, w in enumerate(words):
                    if w.strip('.,!?;:') == 'is' and i > 0 and words[i - 1].strip('.,!?;:').lower() == 'i':
                        wrong_word = 'is'
                        correct_word = 'am'
                        break

        elif any(kw in grammar_lower for kw in ['past simple']):
            # yesterday + present tense -> past tense
            for w in words:
                wl = w.strip('.,!?;:')
                if wl in ['go', 'play', 'watch', 'work', 'come']:
                    for ww in words:
                        if ww.strip('.,!?;:').lower() == 'yesterday':
                            wrong_word = wl
                            correct_word = wl + 'ed'
                            break
                    if wrong_word:
                        break

        elif any(kw in grammar_lower for kw in ['article']):
            # 元音前用 a -> an
            vowels = 'aeiou'
            for i, w in enumerate(words):
                wl = w.strip('.,!?;:')
                if wl == 'a' and i + 1 < len(words):
                    next_w = words[i + 1].strip('.,!?;:').lower()
                    if next_w and next_w[0] in vowels:
                        wrong_word = 'a'
                        correct_word = 'an'
                        break

        elif any(kw in grammar_lower for kw in ['preposition']):
            # in Monday -> on Monday
            for i, w in enumerate(words):
                wl = w.strip('.,!?;:')
                if wl == 'in' and i + 1 < len(words):
                    next_w = words[i + 1].strip('.,!?;:').lower()
                    if next_w in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                        wrong_word = 'in'
                        correct_word = 'on'
                        break

        if not wrong_word or not correct_word:
            return None

        wrong_sentence = sentence.replace(wrong_word, '【' + wrong_word + '】', 1)

        return {
            'type': 'correct',
            'question': f"找出并改正句子中的错误：\n{wrong_sentence}",
            'options': [correct_word, wrong_word, '不修改', '删除该词'],
            'answer': correct_word,
            'hint': grammar_name,
        }

    def _make_order_question(self, sentence: str) -> GrammarExercise | None:
        """生成排序题"""
        words = sentence.split()
        if len(words) < 4 or len(words) > 10:
            return None

        shuffled = words.copy()
        # 确保打乱
        for _ in range(3):
            random.shuffle(shuffled)
        if shuffled == words:
            if len(shuffled) >= 2:
                shuffled[0], shuffled[1] = shuffled[1], shuffled[0]

        return {
            'type': 'order',
            'question': '将以下单词排列成正确的句子：',
            'options': shuffled,
            'answer': ' '.join(words),
            'hint': '',
        }


def get_practice_engine() -> GrammarPracticeEngine:
    """获取练习引擎实例"""
    return GrammarPracticeEngine()
