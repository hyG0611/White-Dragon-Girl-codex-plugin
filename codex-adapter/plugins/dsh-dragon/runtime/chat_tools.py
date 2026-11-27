"""Recognize the desktop tools that can be called directly from a chat message."""
from dataclasses import dataclass
import re
import unicodedata

from reminders import looks_like_reminder


POLITE = re.compile(r'^(?:(?:请问|请|麻烦你|麻烦|帮我|给我)\s*)+')
LOOKUP = r'(?:查询(?:一下)?|查看(?:一下)?|查(?:一下|下|查)?|看看|看一下|告诉我)?'
CURRENT = r'(?:今天|今日|现在|当前)?'
TAIL = r'(?:呢|吗|吧|呀)?'
WEATHER = re.compile(
    LOOKUP + CURRENT + r'(?:成都市?)?' + CURRENT + r'的?天气(?:怎么样|如何|怎样)?' + TAIL
)
CHENGDU_TEMPERATURE = re.compile(
    LOOKUP + CURRENT + r'成都市?' + CURRENT + r'的?(?:气温(?:是多少|多少)?|多少度|几度)' + TAIL
)
QUOTA = re.compile(
    LOOKUP + r'(?:我的|我)?(?:当前|现在)?'
    r'(?:(?:codex的?)?(?:剩余)?额度(?:还剩多少|还有多少|剩多少|是多少|多少)?'
    r'|(?:codex)?还(?:剩|有)多少(?:codex的?)?额度'
    r'|codex(?:剩余|使用)?用量(?:是多少|多少)?)' + TAIL
)
ADD_TODO = re.compile(
    r'^(?:添加|新建|新增)(?:一条|一个)?(?:待办(?:事项)?|提醒)'
    r'(?=$|[\s：:，,]|[0-9０-９一二两三四五六七八九十今晚明后工每半周])'
)
REPEAT_PREFIX = re.compile(r'^(每天|每日|工作日|周一(?:至|到)周五|每周)\s*')
WEEKDAY_TIME = re.compile(r'^[一二三四五六日天](?=\s*(?:凌晨|早上|上午|中午|下午|晚上|[0-9零〇一二两三四五六七八九十]))')
REPEATS = {'每天': 'daily', '每日': 'daily', '工作日': 'weekdays',
           '周一至周五': 'weekdays', '周一到周五': 'weekdays', '每周': 'weekly'}


@dataclass(frozen=True)
class ChatTool:
    kind: str
    sentence: str = ''
    repeat: str = ''


def chat_tool(message):
    sentence = POLITE.sub('', message.strip()).rstrip('。？！?!，, ').strip()
    compact = ''.join(unicodedata.normalize('NFKC', sentence).split()).casefold()
    if WEATHER.fullmatch(compact) or CHENGDU_TEMPERATURE.fullmatch(compact):
        return ChatTool('weather')
    if QUOTA.fullmatch(compact):
        return ChatTool('quota')

    explicit = ADD_TODO.match(sentence)
    if explicit:
        sentence = sentence[explicit.end():].lstrip(' ：:，,')
    repeat = REPEAT_PREFIX.match(sentence)
    mode = ''
    if repeat:
        mode = REPEATS[repeat[1]]
        sentence = sentence[repeat.end():]
        if mode == 'weekly' and WEEKDAY_TIME.match(sentence):
            sentence = '周' + sentence
    if explicit or looks_like_reminder(sentence):
        return ChatTool('todo', sentence, mode)
    return None
