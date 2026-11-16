from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins' / 'dsh-dragon' / 'runtime'))
from reminders import check_reminder, next_repeat, parse_reminder, reminder_due, snooze_reminder


class ReminderTests(unittest.TestCase):
    now = datetime(2026, 11, 16, 18, 45, 12, tzinfo=timezone(timedelta(hours=8)))

    def test_relative_reminders_keep_seconds(self):
        for sentence, minutes in (('１０分钟后提醒我喝水', 10), ('半小时后提醒我喝水', 30),
                                  ('2小时后提醒我喝水', 120)):
            with self.subTest(sentence=sentence):
                self.assertEqual(parse_reminder(sentence, self.now), {
                    'text': '喝水', 'due': int(self.now.timestamp()) + minutes * 60, 'lead': 0,
                })

    def test_clock_periods_and_next_occurrence(self):
        for sentence, day, hour, minute in (
            ('今晚8点半提醒我开会', 16, 20, 30), ('明天上午9点提醒我开会', 17, 9, 0),
            ('后天 09：30 提醒我开会', 18, 9, 30), ('9点提醒我开会', 17, 9, 0),
            ('晚上8点05分提醒我开会', 16, 20, 5),
        ):
            with self.subTest(sentence=sentence):
                expected = self.now.replace(day=day, hour=hour, minute=minute, second=0)
                self.assertEqual(parse_reminder(sentence, self.now)['due'], int(expected.timestamp()))

    def test_rejects_past_or_ambiguous_input(self):
        for sentence in ('今天9点提醒我开会', '24:00提醒我睡觉', '8点60分提醒我开会',
                         '上午19点提醒我开会', '0分钟后提醒我喝水', '526000分钟后提醒我喝水',
                         '过一会儿提醒我喝水', '10分钟后提醒我', '10分钟后提醒我' + '水' * 101):
            with self.subTest(sentence=sentence), self.assertRaises(ValueError):
                parse_reminder(sentence, self.now)

    def test_workdays_skip_weekend_and_snooze_keeps_next_occurrence(self):
        friday = int(datetime(2026, 11, 20, 9).timestamp())
        monday = int(datetime(2026, 11, 23, 9).timestamp())
        todo = {'text': '喝水', 'due': friday, 'lead': 5, 'repeat': 'weekdays'}
        self.assertIsNotNone(check_reminder(todo, friday - 299))
        self.assertTrue(todo['warned'])
        self.assertEqual(check_reminder(todo, friday), '喝水')
        self.assertEqual(todo['due'], monday)
        self.assertNotIn('warned', todo)
        self.assertTrue(snooze_reminder(todo, friday + 3))
        self.assertEqual(reminder_due(todo), friday + 603)
        self.assertIsNone(check_reminder(todo, friday + 602))
        self.assertEqual(check_reminder(todo, friday + 603), '喝水')
        self.assertEqual(reminder_due(todo), monday)

    def test_resume_delivers_only_recent_occurrence_and_rolls_weekly(self):
        first = int(datetime(2026, 11, 2, 9).timestamp())
        later = int(datetime(2026, 11, 16, 9).timestamp())
        todo = {'text': '例会', 'due': first, 'repeat': 'weekly'}
        self.assertEqual(check_reminder(todo, later + 30), '例会')
        self.assertEqual(todo['due'], int(datetime(2026, 11, 23, 9).timestamp()))
        self.assertIsNone(check_reminder(todo, later + 31))
        missed = {'text': '例会', 'due': first, 'repeat': 'weekly'}
        self.assertIsNone(check_reminder(missed, later + 3600))
        self.assertEqual(missed['due'], todo['due'])

    def test_old_one_time_reminder_archives_and_can_be_snoozed(self):
        due = int(datetime(2026, 11, 21, 9).timestamp())
        self.assertEqual(next_repeat(due, 'weekdays', due - 1), int(datetime(2026, 11, 23, 9).timestamp()))
        todo = {'text': '喝水', 'due': due}
        self.assertEqual(check_reminder(todo, due), '喝水')
        self.assertIsNone(reminder_due(todo))
        self.assertTrue(snooze_reminder(todo, due + 1))
        self.assertFalse(snooze_reminder(todo, due + 2))
        self.assertEqual(check_reminder(todo, due + 601), '喝水')
        self.assertIsNone(reminder_due(todo))
