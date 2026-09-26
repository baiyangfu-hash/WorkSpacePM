"""
语法课程引擎 - 基于 CEFR-J 语法项目表的分级语法课程
"""
import json
import os
import sqlite3
from typing import TypedDict


class GrammarLevel(TypedDict):
    level: str
    name: str
    count: int


class GrammarCategory(TypedDict):
    name: str
    count: int
    points: list[dict[str, object]]

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'app.db')

# A1-B1 语法知识点（共 130 个，来源：CEFR Grammar Dashboard + CEFR-J）
GRAMMAR_POINTS = {
    "A1": [
        # 基础时态
        {"name": "Present Simple - 'be'", "category": "时态", "explanation": "am/is/are 的用法", "examples": ["I am a student.", "She is happy.", "They are at home."], "lesson_order": 1},
        {"name": "Present Simple - 其他动词", "category": "时态", "explanation": "一般现在时第三人称单数加 -s/-es", "examples": ["I work in a bank.", "He works in a bank.", "They go to school."], "lesson_order": 2},
        {"name": "Present Continuous", "category": "时态", "explanation": "am/is/are + doing 表示正在进行的动作", "examples": ["I am reading a book.", "She is cooking dinner.", "They are playing football."], "lesson_order": 3},
        {"name": "Past Simple - 'be'", "category": "时态", "explanation": "was/were 的用法", "examples": ["I was tired.", "They were at the party.", "She was late."], "lesson_order": 4},
        {"name": "Past Simple - 规则动词", "category": "时态", "explanation": "动词过去式加 -ed", "examples": ["I worked yesterday.", "She played tennis.", "They watched a movie."], "lesson_order": 5},
        {"name": "Past Simple - 不规则动词", "category": "时态", "explanation": "常见不规则动词过去式", "examples": ["I went to the store.", "She had a good time.", "They came early."], "lesson_order": 6},
        {"name": "Future with 'will'", "category": "时态", "explanation": "will + 动词原形 表示将来", "examples": ["I will call you later.", "It will rain tomorrow.", "They will arrive at 6."], "lesson_order": 7},
        {"name": "Future with 'going to'", "category": "时态", "explanation": "be going to + 动词原形 表示计划/意图", "examples": ["I am going to visit my parents.", "She is going to buy a car.", "We are going to travel."], "lesson_order": 8},
        # 情态动词
        {"name": "Can / Can't", "category": "情态动词", "explanation": "表示能力、许可", "examples": ["I can swim.", "She can't drive.", "Can you help me?"], "lesson_order": 9},
        {"name": "Must / Mustn't", "category": "情态动词", "explanation": "表示必须/禁止", "examples": ["You must wear a seatbelt.", "You mustn't smoke here.", "I must finish this."], "lesson_order": 10},
        {"name": "Should / Shouldn't", "category": "情态动词", "explanation": "表示建议", "examples": ["You should see a doctor.", "He shouldn't eat so much.", "Should I call her?"], "lesson_order": 11},
        # 疑问句
        {"name": "Yes/No Questions", "category": "疑问句", "explanation": "一般疑问句", "examples": ["Do you like coffee?", "Is she your sister?", "Can you speak English?"], "lesson_order": 12},
        {"name": "Wh- Questions", "category": "疑问句", "explanation": "特殊疑问句 (who/what/where/when/why/how)", "examples": ["Where do you live?", "What time is it?", "Why are you late?"], "lesson_order": 13},
        {"name": "How much / How many", "category": "疑问句", "explanation": "数量提问", "examples": ["How much is this?", "How many people are there?", "How much water do you need?"], "lesson_order": 14},
        # 名词与代词
        {"name": "Articles: a/an/the", "category": "名词", "explanation": "冠词用法", "examples": ["a book / an apple", "the sun", "I need a pen."], "lesson_order": 15},
        {"name": "Plural Nouns", "category": "名词", "explanation": "名词复数形式 -s/-es/-ies", "examples": ["books", "buses", "babies"], "lesson_order": 16},
        {"name": "There is / There are", "category": "名词", "explanation": "存在句", "examples": ["There is a cat on the sofa.", "There are two books on the desk.", "Is there a bank near here?"], "lesson_order": 17},
        {"name": "Subject Pronouns", "category": "代词", "explanation": "主格代词 I/you/he/she/it/we/they", "examples": ["I am happy.", "She is a teacher.", "They are friends."], "lesson_order": 18},
        {"name": "Object Pronouns", "category": "代词", "explanation": "宾格代词 me/you/him/her/it/us/them", "examples": ["Give me the book.", "I like her.", "Can you help us?"], "lesson_order": 19},
        {"name": "Possessive Adjectives", "category": "代词", "explanation": "形容词性物主代词 my/your/his/her/its/our/their", "examples": ["my book", "her car", "our house"], "lesson_order": 20},
        {"name": "Possessive 's", "category": "名词", "explanation": "名词所有格", "examples": ["John's car", "the teacher's desk", "my parents' house"], "lesson_order": 21},
        {"name": "This/That/These/Those", "category": "代词", "explanation": "指示代词", "examples": ["This is my friend.", "That is a nice car.", "These are my books.", "Those are expensive."], "lesson_order": 22},
        # 形容词与副词
        {"name": "Adjectives", "category": "形容词", "explanation": "形容词位置和顺序", "examples": ["a big house", "a beautiful girl", "the weather is nice"], "lesson_order": 23},
        {"name": "Adverbs of Frequency", "category": "副词", "explanation": "频度副词 always/usually/often/sometimes/never", "examples": ["I always get up early.", "She often goes to the gym.", "They never eat fast food."], "lesson_order": 24},
        {"name": "Very / Really / Quite", "category": "副词", "explanation": "程度副词", "examples": ["It's very cold.", "She is really nice.", "It's quite easy."], "lesson_order": 25},
        # 介词
        {"name": "Prepositions of Place", "category": "介词", "explanation": "地点介词 in/on/at/under/next to/between", "examples": ["in the room", "on the table", "at the bus stop"], "lesson_order": 26},
        {"name": "Prepositions of Time", "category": "介词", "explanation": "时间介词 in/on/at", "examples": ["in January", "on Monday", "at 3 o'clock"], "lesson_order": 27},
        # 连词
        {"name": "And / But / Or", "category": "连词", "explanation": "并列连词", "examples": ["I like tea and coffee.", "She is tall but I am short.", "Do you want tea or coffee?"], "lesson_order": 28},
        {"name": "Because", "category": "连词", "explanation": "原因连词", "examples": ["I am tired because I worked late.", "She is happy because she passed the test."], "lesson_order": 29},
        # 祈使句
        {"name": "Imperative", "category": "祈使句", "explanation": "祈使句（命令/请求/建议）", "examples": ["Sit down, please.", "Don't touch that.", "Let's go."], "lesson_order": 30},
        # 比较级
        {"name": "Comparatives", "category": "比较级", "explanation": "比较级 -er than / more ... than", "examples": ["I am taller than my brother.", "This book is more interesting than that one."], "lesson_order": 31},
        {"name": "Superlatives", "category": "比较级", "explanation": "最高级 the -est / the most", "examples": ["She is the tallest in the class.", "This is the most expensive restaurant."], "lesson_order": 32},
        # 其他
        {"name": "Have got", "category": "基础表达", "explanation": "have got 表示拥有", "examples": ["I have got a car.", "She has got two brothers.", "Have you got any money?"], "lesson_order": 33},
        {"name": "Like / Love / Hate + noun/verb-ing", "category": "基础表达", "explanation": "表达喜好", "examples": ["I like swimming.", "She loves music.", "They hate waiting."], "lesson_order": 34},
    ],
    "A2": [
        # 时态进阶
        {"name": "Past Continuous", "category": "时态", "explanation": "was/were + doing 过去进行时", "examples": ["I was watching TV when she called.", "What were you doing at 8?", "They were not listening."], "lesson_order": 1},
        {"name": "Present Perfect", "category": "时态", "explanation": "have/has + done 现在完成时", "examples": ["I have been to London.", "She has finished her homework.", "Have you ever eaten sushi?"], "lesson_order": 2},
        {"name": "Present Perfect with ever/never", "category": "时态", "explanation": "现在完成时 + ever/never", "examples": ["Have you ever been to Paris?", "I have never tried skiing.", "It's the best movie I have ever seen."], "lesson_order": 3},
        {"name": "Going to vs Will", "category": "时态", "explanation": "区分 will 和 going to", "examples": ["I will help you. (即时决定)", "I am going to visit my parents. (计划)"], "lesson_order": 4},
        {"name": "Used to", "category": "时态", "explanation": "used to 表示过去的习惯", "examples": ["I used to live in Tokyo.", "She used to smoke.", "We didn't use to have a car."], "lesson_order": 5},
        {"name": "Present Perfect with for/since", "category": "时态", "explanation": "现在完成时 + for/since", "examples": ["I have lived here for 5 years.", "She has been a teacher since 2010."], "lesson_order": 6},
        {"name": "Present Perfect vs Past Simple", "category": "时态", "explanation": "区分现在完成时和一般过去时", "examples": ["I have lost my key. (结果现在找不到)", "I lost my key yesterday. (过去事件)"], "lesson_order": 7},
        # 情态动词进阶
        {"name": "Have to / Don't have to", "category": "情态动词", "explanation": "表示必须/不必", "examples": ["I have to go now.", "You don't have to come.", "Do you have to work tomorrow?"], "lesson_order": 8},
        {"name": "Might / May", "category": "情态动词", "explanation": "表示可能性", "examples": ["It might rain.", "She may be late.", "I might not come."], "lesson_order": 9},
        {"name": "Could / Couldn't", "category": "情态动词", "explanation": "过去能力/请求", "examples": ["I could swim when I was 5.", "Could you help me?", "I couldn't sleep last night."], "lesson_order": 10},
        # 条件句
        {"name": "First Conditional", "category": "条件句", "explanation": "if + 现在时, will + 动词原形", "examples": ["If it rains, I will stay home.", "If you study hard, you will pass."], "lesson_order": 11},
        {"name": "Zero Conditional", "category": "条件句", "explanation": "if + 现在时, 现在时 (普遍真理)", "examples": ["If you heat water, it boils.", "If it rains, the grass gets wet."], "lesson_order": 12},
        # 被动语态
        {"name": "Passive Voice (Present Simple)", "category": "被动语态", "explanation": "is/are + done 被动语态", "examples": ["English is spoken here.", "Cars are made in Japan."], "lesson_order": 13},
        {"name": "Passive Voice (Past Simple)", "category": "被动语态", "explanation": "was/were + done 被动语态", "examples": ["The bridge was built in 1900.", "They were invited to the party."], "lesson_order": 14},
        # 关系从句
        {"name": "Relative Clauses (who/which/that)", "category": "关系从句", "explanation": "关系代词 who/which/that", "examples": ["The woman who lives next door.", "The book that I bought.", "The car which is parked outside."], "lesson_order": 15},
        {"name": "Relative Clauses (where)", "category": "关系从句", "explanation": "关系副词 where", "examples": ["The restaurant where we met.", "The city where I was born."], "lesson_order": 16},
        # 比较级进阶
        {"name": "As ... as", "category": "比较级", "explanation": "同级比较 as + 形容词/副词 + as", "examples": ["She is as tall as me.", "It's not as expensive as I thought.", "Can you run as fast as him?"], "lesson_order": 17},
        {"name": "Too / Enough", "category": "比较级", "explanation": "too + 形容词 / 形容词 + enough", "examples": ["It's too hot.", "She is not old enough.", "I have enough money."], "lesson_order": 18},
        # 不定式与动名词
        {"name": "Gerunds (-ing form)", "category": "非谓语", "explanation": "动名词做主语/宾语", "examples": ["Swimming is good exercise.", "I enjoy cooking.", "She hates waiting."], "lesson_order": 19},
        {"name": "Infinitives (to + verb)", "category": "非谓语", "explanation": "不定式 to do", "examples": ["I want to go home.", "She needs to study.", "It's important to be on time."], "lesson_order": 20},
        {"name": "Want / Would like + to", "category": "基础表达", "explanation": "表达愿望", "examples": ["I want to travel.", "I would like to order.", "She wants to be a doctor."], "lesson_order": 21},
        # 疑问句进阶
        {"name": "Question Tags", "category": "疑问句", "explanation": "反意疑问句", "examples": ["You are coming, aren't you?", "It's cold, isn't it?", "You don't like coffee, do you?"], "lesson_order": 22},
        # 代词进阶
        {"name": "Reflexive Pronouns", "category": "代词", "explanation": "反身代词 myself/yourself/himself 等", "examples": ["I did it myself.", "She looked at herself in the mirror.", "Help yourself."], "lesson_order": 23},
        {"name": "Some / Any / No", "category": "代词", "explanation": "不定代词", "examples": ["I have some money.", "Do you have any questions?", "There is no milk."], "lesson_order": 24},
        {"name": "Something / Anything / Nothing", "category": "代词", "explanation": "复合不定代词", "examples": ["I saw something strange.", "Do you know anything?", "There is nothing to eat."], "lesson_order": 25},
        # 量词
        {"name": "Quantifiers: much/many/lots of", "category": "量词", "explanation": "数量表达", "examples": ["How much water?", "How many books?", "I have lots of friends."], "lesson_order": 26},
        {"name": "A little / A few", "category": "量词", "explanation": "少量可数/不可数", "examples": ["a little water", "a few friends", "I have a little money."], "lesson_order": 27},
        # 介词进阶
        {"name": "Prepositions of Movement", "category": "介词", "explanation": "方向介词 to/from/into/out of/across/through", "examples": ["Go to the station.", "She came from London.", "Walk across the street."], "lesson_order": 28},
        # 连词进阶
        {"name": "So", "category": "连词", "explanation": "结果连词", "examples": ["I was tired, so I went to bed.", "It was raining, so we stayed home."], "lesson_order": 29},
        {"name": "Although / But", "category": "连词", "explanation": "让步/转折", "examples": ["Although it was cold, we went out.", "She is young but very smart."], "lesson_order": 30},
        # 其他
        {"name": "Adverbs of Manner", "category": "副词", "explanation": "方式副词 -ly", "examples": ["She speaks slowly.", "He drives carefully.", "They worked hard."], "lesson_order": 31},
        {"name": "Make / Do", "category": "基础表达", "explanation": "make 和 do 的区分", "examples": ["make a mistake", "do homework", "make a decision", "do the dishes"], "lesson_order": 32},
        {"name": "Prepositions after Adjectives", "category": "介词", "explanation": "形容词 + 介词搭配", "examples": ["good at", "interested in", "afraid of", "worried about"], "lesson_order": 33},
        {"name": "Both / Either / Neither", "category": "代词", "explanation": "两者都/任一/两者都不", "examples": ["Both are correct.", "Either is fine.", "Neither of them came."], "lesson_order": 34},
        {"name": "Present Perfect with just/already/yet", "category": "时态", "explanation": "现在完成时 + just/already/yet", "examples": ["I have just finished.", "She has already left.", "Have you eaten yet?"], "lesson_order": 35},
        {"name": "So / Such", "category": "副词", "explanation": "so + adj/adv, such + noun", "examples": ["It's so beautiful!", "It's such a beautiful day!"], "lesson_order": 36},
        {"name": "Reported Speech (say/tell)", "category": "间接引语", "explanation": "间接引语基础", "examples": ["She said (that) she was tired.", "He told me (that) he liked it."], "lesson_order": 37},
    ],
    "B1": [
        # 时态进阶
        {"name": "Past Perfect", "category": "时态", "explanation": "had + done 过去完成时", "examples": ["When I arrived, they had already left.", "She had never seen the ocean before.", "I had finished my work by 6pm."], "lesson_order": 1},
        {"name": "Present Perfect Continuous", "category": "时态", "explanation": "have/has + been + doing", "examples": ["I have been waiting for an hour.", "She has been studying all day.", "How long have you been working here?"], "lesson_order": 2},
        {"name": "Future Continuous", "category": "时态", "explanation": "will be + doing", "examples": ["This time tomorrow I will be flying to New York.", "Will you be using the car tonight?"], "lesson_order": 3},
        {"name": "Future Perfect", "category": "时态", "explanation": "will have + done", "examples": ["By next year, I will have finished my degree.", "She will have arrived by now."], "lesson_order": 4},
        # 条件句进阶
        {"name": "Second Conditional", "category": "条件句", "explanation": "if + 过去时, would + 动词原形", "examples": ["If I had more money, I would travel.", "If I were you, I would take the job.", "What would you do if you won the lottery?"], "lesson_order": 5},
        {"name": "Third Conditional", "category": "条件句", "explanation": "if + had done, would have done", "examples": ["If I had known, I would have come.", "If she had studied, she would have passed."], "lesson_order": 6},
        {"name": "Mixed Conditionals", "category": "条件句", "explanation": "混合条件句", "examples": ["If I had studied harder, I would have a better job now.", "If I were you, I would have accepted the offer."], "lesson_order": 7},
        # 被动语态进阶
        {"name": "Passive Voice (all tenses)", "category": "被动语态", "explanation": "各时态被动语态", "examples": ["The house is being painted.", "My car has been repaired.", "The work will be finished tomorrow."], "lesson_order": 8},
        {"name": "Passive with Modals", "category": "被动语态", "explanation": "情态动词被动语态", "examples": ["It must be done.", "The rules should be followed.", "This can be fixed."], "lesson_order": 9},
        # 间接引语
        {"name": "Reported Speech (tense changes)", "category": "间接引语", "explanation": "间接引语时态变化", "examples": ["'I am tired' → He said he was tired.", "'I will call' → She said she would call.", "'I have been' → He said he had been."], "lesson_order": 10},
        {"name": "Reported Questions", "category": "间接引语", "explanation": "间接疑问句", "examples": ["'Where do you live?' → He asked me where I lived.", "'Do you like coffee?' → She asked if I liked coffee."], "lesson_order": 11},
        {"name": "Reported Commands", "category": "间接引语", "explanation": "间接命令/请求", "examples": ["'Sit down' → He told me to sit down.", "'Don't go' → She told me not to go."], "lesson_order": 12},
        # 关系从句进阶
        {"name": "Non-defining Relative Clauses", "category": "关系从句", "explanation": "非限定性关系从句", "examples": ["My sister, who lives in London, is a doctor.", "The Eiffel Tower, which was built in 1889, is famous."], "lesson_order": 13},
        {"name": "Relative Clauses (omission)", "category": "关系从句", "explanation": "关系代词省略", "examples": ["The book (that) I read.", "The person (who) I met."], "lesson_order": 14},
        {"name": "Relative Clauses with Prepositions", "category": "关系从句", "explanation": "介词 + 关系代词", "examples": ["The company for which I work.", "The person to whom I spoke."], "lesson_order": 15},
        # 情态动词进阶
        {"name": "Must have / Can't have / Might have", "category": "情态动词", "explanation": "对过去的推测", "examples": ["He must have been tired.", "She can't have forgotten.", "They might have left early."], "lesson_order": 16},
        {"name": "Should have / Could have / Would have", "category": "情态动词", "explanation": "过去应该/可以/会", "examples": ["I should have called.", "You could have told me.", "I would have helped."], "lesson_order": 17},
        {"name": "Need to / Needn't", "category": "情态动词", "explanation": "need 的用法", "examples": ["You need to finish this.", "You needn't worry.", "Do I need to bring anything?"], "lesson_order": 18},
        # 不定式与动名词
        {"name": "Gerund vs Infinitive", "category": "非谓语", "explanation": "动词后接 doing/to do 的区分", "examples": ["I enjoy swimming. (enjoy + doing)", "I want to swim. (want + to do)", "I stopped smoking. vs I stopped to smoke."], "lesson_order": 19},
        {"name": "Verb + object + infinitive", "category": "非谓语", "explanation": "动词 + 宾语 + to do", "examples": ["I want you to come.", "She told me to wait.", "They asked us to help."], "lesson_order": 20},
        {"name": "Make / Let + object + infinitive", "category": "非谓语", "explanation": "使役动词 + 宾语 + 动词原形", "examples": ["She made me laugh.", "Let me help you.", "They didn't let us in."], "lesson_order": 21},
        # 语序
        {"name": "So / Neither / Nor", "category": "语序", "explanation": "倒装: So do I / Neither do I", "examples": ["I like coffee. So do I.", "I don't like milk. Neither do I.", "I have been there. So have I."], "lesson_order": 22},
        {"name": "Inversion after Negative Adverbials", "category": "语序", "explanation": "否定副词后的倒装", "examples": ["Never have I seen such beauty.", "Rarely do we agree.", "Not only is she smart, but also kind."], "lesson_order": 23},
        # 名词性从句
        {"name": "Noun Clauses (that)", "category": "名词性从句", "explanation": "that 引导的名词性从句", "examples": ["I think (that) it's a good idea.", "She said (that) she would come.", "The fact that he is late doesn't matter."], "lesson_order": 24},
        {"name": "Noun Clauses (wh- words)", "category": "名词性从句", "explanation": "wh-词引导的名词性从句", "examples": ["I don't know where he is.", "Tell me what you want.", "It depends on how much it costs."], "lesson_order": 25},
        # 状语从句
        {"name": "Time Clauses (when/while/after/before)", "category": "状语从句", "explanation": "时间状语从句", "examples": ["I will call you when I arrive.", "While I was cooking, the phone rang.", "After she left, I felt sad."], "lesson_order": 26},
        {"name": "Purpose Clauses (to/in order to/so that)", "category": "状语从句", "explanation": "目的状语从句", "examples": ["I study hard to pass the exam.", "I left early so that I wouldn't miss the train.", "She saves money in order to travel."], "lesson_order": 27},
        {"name": "Result Clauses (so...that/such...that)", "category": "状语从句", "explanation": "结果状语从句", "examples": ["It was so hot that I couldn't sleep.", "She is such a good teacher that everyone loves her."], "lesson_order": 28},
        {"name": "Contrast Clauses (although/even though/while)", "category": "状语从句", "explanation": "让步状语从句", "examples": ["Although it was raining, we went out.", "Even though she was tired, she kept working.", "While I like coffee, I prefer tea."], "lesson_order": 29},
        # 连接词
        {"name": "Linking Words (however/therefore/ moreover)", "category": "连接词", "explanation": "段落连接词", "examples": ["It was late. However, we continued.", "The weather was bad. Therefore, we canceled."], "lesson_order": 30},
        # 语态
        {"name": "Have / Get something done", "category": "语态", "explanation": "使役结构 have/get + 宾语 + done", "examples": ["I had my hair cut.", "She got her car repaired.", "We need to get the house painted."], "lesson_order": 31},
        {"name": "I wish / If only", "category": "虚拟语气", "explanation": "wish/if only 表达愿望", "examples": ["I wish I had more money.", "If only I could fly.", "I wish I had studied harder."], "lesson_order": 32},
        {"name": "It's time / I'd rather", "category": "虚拟语气", "explanation": "it's time + 过去时 / would rather", "examples": ["It's time we left.", "I'd rather you didn't go.", "It's time you started studying."], "lesson_order": 33},
        # 介词进阶
        {"name": "Phrasal Verbs", "category": "短语动词", "explanation": "常见短语动词", "examples": ["give up", "look after", "turn on/off", "put off", "carry on", "find out", "get along with"], "lesson_order": 34},
        {"name": "Phrasal Verbs (separable/inseparable)", "category": "短语动词", "explanation": "可分离/不可分离短语动词", "examples": ["Turn it on. (可分离)", "Look after her. (不可分离)", "I can't put up with it. (三词)"], "lesson_order": 35},
        # 形容词
        {"name": "-ed / -ing Adjectives", "category": "形容词", "explanation": "-ed 和 -ing 形容词的区别", "examples": ["I am interested / It is interesting", "She is bored / The movie is boring", "They are excited / The news is exciting"], "lesson_order": 36},
        {"name": "Order of Adjectives", "category": "形容词", "explanation": "形容词顺序", "examples": ["a beautiful small old French wooden table", "a lovely big red car"], "lesson_order": 37},
        # 冠词
        {"name": "Articles (advanced)", "category": "名词", "explanation": "冠词高级用法：泛指/独指/零冠词", "examples": ["The rich get richer.", "I go to school. (零冠词/机构)", "Life is beautiful. (零冠词/抽象)"], "lesson_order": 38},
        # 数量
        {"name": "All / Every / Whole", "category": "量词", "explanation": "全部/每个/整体", "examples": ["All students must attend.", "Every student has a book.", "I spent the whole day reading."], "lesson_order": 39},
        # 语序
        {"name": "Indirect Questions", "category": "疑问句", "explanation": "间接疑问句", "examples": ["Do you know where the station is?", "Can you tell me what time it is?", "I wonder if she is coming."], "lesson_order": 40},
        # 其他
        {"name": "Be used to / Get used to", "category": "基础表达", "explanation": "习惯于", "examples": ["I am used to getting up early.", "She is getting used to the new job.", "I can't get used to the weather."], "lesson_order": 41},
        {"name": "Question Tags (advanced)", "category": "疑问句", "explanation": "复杂反意疑问句", "examples": ["Let's go, shall we?", "I am right, aren't I?", "Nobody came, did they?"], "lesson_order": 42},
    ],
    "B2": [
        {"name": "Inversion after Negative Adverbials", "category": "倒装句", "explanation": "否定副词(Hardly, Seldom, Never)置于句首时的部分倒装", "examples": ["Hardly had I arrived when it began to rain.", "Never have I seen such dedication.", "Seldom do we witness such remarkable talent."], "lesson_order": 1},
        {"name": "Advanced Subjunctive Mood", "category": "虚拟语气", "explanation": "错综时间条件句与虚拟过去推测", "examples": ["If I had studied harder back then, I would have a better job now.", "I would rather you had told me earlier."], "lesson_order": 2},
        {"name": "Cleft Sentences (It is...that)", "category": "强调句", "explanation": "It is/was + 强调成分 + that/who", "examples": ["It was John who broke the vase yesterday.", "It is through practice that fluency is achieved."], "lesson_order": 3},
        {"name": "Participle Clauses (-ing / -ed)", "category": "分词短语", "explanation": "现在分词与过去分词作状语/定语", "examples": ["Having finished his work, he went home.", "Seen from the hill, the city looks beautiful."], "lesson_order": 4},
        {"name": "Advanced Passive Structures", "category": "被动语态", "explanation": "It is reported/believed that ... 形式主语被动", "examples": ["He is reported to have resigned.", "It is believed that the treaty will be signed tomorrow."], "lesson_order": 5},
        {"name": "Prepositional Relative Clauses", "category": "关系从句", "explanation": "介词 + 关系代词 (whom/which) 的正规文体表达", "examples": ["The project on which we are working is critical.", "The gentleman to whom you spoke is the CEO."], "lesson_order": 6},
    ],
    "C1": [
        {"name": "Formal Subjunctive in Noun Clauses", "category": "虚拟语气", "explanation": "主语/宾语从句中的虚拟语气 (insist/demand/propose that + (should) do)", "examples": ["We demand that the policy be reviewed immediately.", "It is essential that he be informed."], "lesson_order": 1},
        {"name": "Academic Nominalization", "category": "名词化结构", "explanation": "用动名词与抽象名词替代动词增加学术严谨度", "examples": ["The rapid deterioration of the environment requires urgent action.", "Her careful analysis led to groundbreaking results."], "lesson_order": 2},
        {"name": "Complex Double Conjunctions", "category": "并列关联", "explanation": "Not only ... but also ..., Neither ... nor ... 句首倒装", "examples": ["Not only did he complete the project, but he also saved costs.", "Neither does she smoke nor does she drink."], "lesson_order": 3},
        {"name": "Absolute Participle Constructions", "category": "独立主格", "explanation": "名词/代词 + 分词构成独立主格结构", "examples": ["Weather permitting, the plane will take off at 8 AM.", "The meeting being over, everyone left the room."], "lesson_order": 4},
    ],
    "C2": [
        {"name": "Archaic & Formal Subjunctive Inversion", "category": "高端倒装", "explanation": "Be it ... or ..., Were it not for ..., Had it been ...", "examples": ["Be it rain or shine, the event will proceed.", "Were it not for your assistance, I should have failed."], "lesson_order": 1},
        {"name": "Fronting & Stylistic Topicalization", "category": "修辞前置", "explanation": "将表语/状语移至句首营造修辞效果", "examples": ["Patient though he was, he could endure no more.", "Great was our astonishment when we heard the news."], "lesson_order": 2},
        {"name": "Stylistic Ellipsis & Substitution", "category": "省略与替代", "explanation": "母语级复杂平行结构的修辞省略", "examples": ["Some preferred classical music; others, jazz.", "She worked hard, as did her colleagues."], "lesson_order": 3},
    ]
}


class GrammarEngine:
    """语法课程引擎"""

    def __init__(self) -> None:
        self._ensure_db()

    def _ensure_db(self) -> None:
        """确保数据库表和语法数据已初始化"""
        if not os.path.exists(DB_PATH):
            return
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS grammar_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                cefr_level TEXT NOT NULL,
                category TEXT,
                explanation TEXT,
                examples TEXT,
                lesson_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_grammar_level ON grammar_points(cefr_level)')

        # 检查每个等级数据是否就绪
        for lvl in ["A1", "A2", "B1", "B2", "C1", "C2"]:
            cursor.execute('SELECT COUNT(*) FROM grammar_points WHERE cefr_level = ?', (lvl,))
            cnt = cursor.fetchone()[0]
            if cnt == 0 and lvl in GRAMMAR_POINTS:
                for point in GRAMMAR_POINTS[lvl]:
                    examples_json = json.dumps(point['examples'], ensure_ascii=False)
                    cursor.execute(
                        'INSERT INTO grammar_points (name, cefr_level, category, explanation, examples, lesson_order) VALUES (?, ?, ?, ?, ?, ?)',
                        (point['name'], lvl, point['category'], point['explanation'], examples_json, point['lesson_order'])
                    )

        conn.commit()
        conn.close()

    def _seed_grammar_data(self, cursor: sqlite3.Cursor) -> None:
        """播种语法数据"""
        for level, points in GRAMMAR_POINTS.items():
            for point in points:
                examples_json = json.dumps(point['examples'], ensure_ascii=False)
                cursor.execute(
                    'INSERT INTO grammar_points (name, cefr_level, category, explanation, examples, lesson_order) VALUES (?, ?, ?, ?, ?, ?)',
                    (point['name'], level, point['category'], point['explanation'], examples_json, point['lesson_order'])
                )

    def get_all_levels(self) -> list[GrammarLevel]:
        """获取所有 CEFR 等级"""
        return [
            {'level': 'A1', 'name': 'A1 入门', 'count': 34},
            {'level': 'A2', 'name': 'A2 基础', 'count': 37},
            {'level': 'B1', 'name': 'B1 进阶', 'count': 42},
            {'level': 'B2', 'name': 'B2 中级', 'count': 6},
            {'level': 'C1', 'name': 'C1 高级', 'count': 4},
            {'level': 'C2', 'name': 'C2 精通', 'count': 3},
        ]

    def get_points_by_level(self, level: str) -> list[dict[str, object]]:
        """获取指定等级的所有语法点"""
        if not os.path.exists(DB_PATH):
            return []
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT * FROM grammar_points WHERE cefr_level = ? ORDER BY lesson_order',
                (level,)
            )
            rows = cursor.fetchall()
            result: list[dict[str, object]] = []
            for row in rows:
                d = dict(row)
                try:
                    d['examples'] = json.loads(d['examples'])
                except (json.JSONDecodeError, TypeError):
                    d['examples'] = []
                result.append(d)
            return result
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def get_point_by_id(self, point_id: int) -> dict[str, object] | None:
        """获取指定语法点"""
        if not os.path.exists(DB_PATH):
            return None
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT * FROM grammar_points WHERE id = ?', (point_id,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                try:
                    d['examples'] = json.loads(d['examples'])
                except (json.JSONDecodeError, TypeError):
                    d['examples'] = []
                return d
            return None
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()

    def get_categories_by_level(self, level: str) -> list[GrammarCategory]:
        """获取指定等级的语法分类统计"""
        points = self.get_points_by_level(level)
        categories: dict[str, GrammarCategory] = {}
        for p in points:
            raw_category = p['category']
            cat = str(raw_category) if raw_category is not None else ''
            if cat not in categories:
                categories[cat] = {'name': cat, 'count': 0, 'points': []}
            categories[cat]['count'] += 1
            categories[cat]['points'].append({
                'id': p['id'],
                'name': p['name'],
                'lesson_order': p['lesson_order'],
            })
        return sorted(categories.values(), key=lambda x: list(categories.keys()).index(x['name']))


def get_all_grammar_points() -> list[dict[str, object]]:
    """获取所有语法点（便捷函数）"""
    engine = GrammarEngine()
    all_points: list[dict[str, object]] = []
    for level_info in engine.get_all_levels():
        points = engine.get_points_by_level(level_info['level'])
        all_points.extend(points)
    return all_points
