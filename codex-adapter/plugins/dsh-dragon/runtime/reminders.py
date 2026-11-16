"""Parse and schedule reminders using the local clock."""
from datetime import datetime, timedelta
import re
import unicodedata

REPEAT_OPTIONS = {'': '不重复', 'daily': '每天', 'weekdays': '工作日（周一至周五）', 'weekly': '每周'}
REMINDER_GRACE = 600


def reminder_due(todo):
    """The next alarm, including any separate snooze of the previous occurrence."""
    snooze = todo.get('snooze_due')
    if todo.get('archived'):
        return snooze
    return min(todo['due'], snooze) if snooze is not None else todo['due']


def next_repeat(due, repeat, after):
    """Return the first scheduled occurrence on or after due and strictly after after."""
    original = datetime.fromtimestamp(due)
    date = max(original.date(), datetime.fromtimestamp(after).date())
    while True:
        if repeat == 'weekly':
            date += timedelta(days=(original.weekday() - date.weekday()) % 7)
        elif repeat == 'weekdays' and date.weekday() >= 5:
            date += timedelta(days=7 - date.weekday())
        wall = datetime.combine(date, original.time()).replace(fold=0)
        timestamp = int(wall.timestamp())
        if timestamp >= due and timestamp > after and datetime.fromtimestamp(timestamp) == wall:
            return timestamp
        date += timedelta(days=1)


def check_reminder(todo, now):
    """Update a reminder in place and return its notification, if any."""
    fired = False
    snooze = todo.get('snooze_due')
    if snooze is not None and snooze <= now:
        fired = snooze >= now - REMINDER_GRACE
        del todo['snooze_due']
    if not todo.get('archived') and todo['due'] <= now:
        due = todo['due']
        repeat = todo.get('repeat')
        if repeat and repeat in REPEAT_OPTIONS:
            recent = next_repeat(due, repeat, now - REMINDER_GRACE - 1)
            fired |= now - REMINDER_GRACE <= recent <= now
            todo['due'] = next_repeat(due, repeat, now)
            todo.pop('warned', None)
        else:
            fired |= due >= now - REMINDER_GRACE
            todo['archived'] = True
    if fired:
        todo['last_fired'] = now
        return todo['text']
    if not todo.get('archived') and not todo.get('warned') and todo['due'] - now <= todo.get('lead', 0) * 60:
        todo['warned'] = True
        return '即将到期：' + todo['text']
    return None


def can_snooze(todo, now):
    fired = todo.get('last_fired')
    return fired is not None and 0 <= now - fired <= REMINDER_GRACE


def snooze_reminder(todo, now):
    if not can_snooze(todo, now):
        return False
    todo['snooze_due'] = now + REMINDER_GRACE
    del todo['last_fired']
    return True


CLOCK = re.compile(
    r'(?P<day>今天|明天|后天|今晚|明晚)?\s*'
    r'(?P<period>凌晨|早上|上午|中午|下午|晚上)?\s*'
    r'(?P<hour>[0-9]{1,2})(?::(?P<minute>[0-9]{2})|点(?:(?P<half>半)|(?P<mins>[0-9]{1,2})分?)?)'
)


def parse_reminder(sentence, now=None):
    now = now if now is not None else datetime.now()
    match = re.fullmatch(r'(.+?)\s*提醒我[\s:：]*(.+)', sentence.strip())
    if not match or not match[2].strip():
        raise ValueError('请用「时间 + 提醒我 + 事项」，例如：10分钟后提醒我休息。')
    when, text = match[1], match[2].strip()
    if len(text) > 100:
        raise ValueError('提醒事项最多 100 个字。')
    when = unicodedata.normalize('NFKC', when.strip())
    relative = re.fullmatch(r'([0-9]{1,6}|半)\s*(分钟|小时)后', when)
    if relative:
        amount, unit = relative.groups()
        if (amount, unit) == ('半', '小时'):
            minutes = 30
        elif amount == '半':
            raise ValueError('相对时间至少为 1 分钟。')
        else:
            minutes = int(amount) * (60 if unit == '小时' else 1)
        if not 1 <= minutes <= 365 * 24 * 60:
            raise ValueError('相对时间须在 1 分钟到 365 天之间。')
        due = int(now.timestamp()) + minutes * 60
    else:
        clock = CLOCK.fullmatch(when)
        if not clock:
            raise ValueError('无法识别时间。试试「半小时后」「今晚8点」或「明天 09:30」。')
        day, period, hour, minute, half, mins = clock.groups()
        hour = int(hour)
        minute = 30 if half else int(minute or mins or '0')
        if hour > 23 or minute > 59:
            raise ValueError('时钟时间须在 00:00 到 23:59 之间。')
        if day in ('今晚', '明晚'):
            if period and period != '晚上':
                raise ValueError('日期和时段不一致，请改用 24 小时制。')
            period = '晚上'
        if period:
            if period in ('下午', '晚上') and 1 <= hour < 12:
                hour += 12
            ranges = {'凌晨': (0, 5), '早上': (5, 12), '上午': (5, 12),
                      '中午': (11, 14), '下午': (12, 19), '晚上': (18, 24)}
            start, end = ranges[period]
            if not start <= hour < end:
                raise ValueError('时段和小时不一致，请改用 24 小时制。')
        days = {'明天': 1, '明晚': 1, '后天': 2}.get(day, 0)
        wall = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days)
        if wall <= now:
            if day:
                raise ValueError('这个时间已经过了，请换一个未来的时间。')
            wall += timedelta(days=1)
        due = int(wall.timestamp())
        if datetime.fromtimestamp(due, now.tzinfo).replace(tzinfo=None) != wall.replace(tzinfo=None):
            raise ValueError('这个本地时间不存在，请换一个时间。')
    return {'text': text, 'due': due, 'lead': 0}
