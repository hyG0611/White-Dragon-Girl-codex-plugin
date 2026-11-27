"""Local, editable context for turns that have left the recent chat window."""
from dataclasses import dataclass, field
import json
import re


RECENT_TURNS = 6
HISTORY_TURNS = 50
EDIT_LIMIT = 6_000
SUMMARY_FIELD = 'conversation_summary'
SECTIONS = {
    'decisions': ('已定事项', 10),
    'todos': ('待办', 10),
    'background': ('较早的对话背景', 3),
}
SECTION_HEADINGS = {
    '已定事项': 'decisions', '已确认事项': 'decisions', 'decisions': 'decisions',
    '待办': 'todos', '待办事项': 'todos', '下一步': 'todos', 'todo': 'todos',
    'todos': 'todos', 'next steps': 'todos',
}
BULLET = re.compile(r'^(?:[-*+•]\s+|\d+[.、)]\s*)')
SENTENCE_END = re.compile(r'(?<=[。！？；])|(?<=[.!?;])\s+')
TODO = re.compile(
    r'待办|下一步|接下来要|记得|还要|还需|未完成|待确认|需要在|请(?:在|于)|提醒我'
    r'|(?:明天|后天|下周).{0,24}(?:要|需|提交|提醒|确认|发给|完成)'
    r'|\b(?:todos?|next steps?|follow.up|need to)\b', re.IGNORECASE,
)
DECISION = re.compile(
    r'已(?:确定|决定|选定|约定|确认|改到|改在|改为)|就用|就按|定在|定于|定为|已定'
    r'|决定|选定|敲定|同意|统一用|确认采用|最终采用'
    r'|\b(?:decided|agreed|settled|confirmed|we will use)\b', re.IGNORECASE,
)
UNCERTAIN = re.compile(
    r'^(?:如果|假如|若|是否|要不要|可能|建议|可以考虑|考虑'
    r'|if\b|maybe\b|could\b|should we\b|not yet\b)', re.IGNORECASE,
)


def shortened(text, limit):
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def marked_lines(text):
    section = None
    for line in text.splitlines():
        line = line.strip().strip('# ').replace('**', '')
        heading = SECTION_HEADINGS.get(line.rstrip('：: ').lower())
        if heading:
            section = heading
            continue
        bullet = BULLET.match(line)
        if bullet:
            line = line[bullet.end():]
        else:
            section = None
        for sentence in SENTENCE_END.split(line):
            sentence = sentence.strip()
            if not sentence or sentence.endswith(('？', '?')) or UNCERTAIN.match(sentence):
                continue
            if section:
                yield section, sentence
            elif TODO.search(sentence):
                yield 'todos', sentence
            elif DECISION.search(sentence) and not re.search(r'(?:没|未|待)(?:定|确认|决定|选定)', sentence):
                yield 'decisions', sentence


@dataclass(eq=False)
class ChatSession:
    turns: list = field(default_factory=list)
    reviewed: int = 0
    edited: str = ''
    excerpts: dict = field(default_factory=dict)

    @classmethod
    def from_history(cls, history):
        summary = history[0].get(SUMMARY_FIELD) if history and isinstance(history[0], dict) else None
        if not isinstance(summary, dict):
            summary = {}
        reviewed = summary.get('reviewed', 0)
        if type(reviewed) is not int:
            reviewed = 0
        edited = summary.get('edited')
        excerpts = {}
        stored = summary.get('excerpts')
        if isinstance(stored, dict):
            for key, (_, count) in SECTIONS.items():
                entries = stored.get(key)
                if isinstance(entries, list):
                    excerpts[key] = [entry[:260] for entry in entries[-count:] if isinstance(entry, str) and entry]
        session = cls(edited=edited[:EDIT_LIMIT] if isinstance(edited, str) else '', excerpts=excerpts)
        for index, turn in enumerate(history):
            if isinstance(turn, dict) and all(isinstance(turn.get(key), str) for key in ('question', 'answer')):
                session.turns.append({key: value for key, value in turn.items() if key != SUMMARY_FIELD})
                session.reviewed += int(index < reviewed)
        return session

    def to_history(self):
        # Optional metadata on a turn is preserved by history readers from before summaries.
        if not self.turns or not (self.reviewed or self.edited or self.excerpts):
            return self.turns
        first = self.turns[0].copy()
        first[SUMMARY_FIELD] = {
            'reviewed': self.reviewed, 'edited': self.edited, 'excerpts': self.excerpts,
        }
        return [first, *self.turns[1:]]

    def add_excerpt(self, section, text):
        entry = shortened(text, 260 if section == 'background' else 160)
        if not entry or entry in self.edited:
            return
        entries = self.excerpts.setdefault(section, [])
        if entry in entries:
            entries.remove(entry)
        entries.append(entry)
        count = SECTIONS[section][1]
        del entries[:-count]

    def summarize_turn(self, turn):
        question, answer = turn['question'], turn['answer']
        if turn.get('local'):
            heading, _, details = answer.partition('\n')
            if heading == '已添加待办。' and details.startswith('事项：'):
                self.add_excerpt('todos', '已添加提醒 · ' + ' · '.join(details.splitlines()))
            return
        found = False
        for text in (question, answer):
            for section, entry in marked_lines(text):
                self.add_excerpt(section, entry)
                found = True
        if not found:
            self.add_excerpt('background', f'你：{shortened(question, 115)}　桌宠：{shortened(answer, 115)}')

    def compact(self, keep=HISTORY_TURNS):
        overflow = max(0, len(self.turns) - keep)
        model_turns = [index for index, turn in enumerate(self.turns) if not turn.get('local')]
        before_recent = model_turns[-RECENT_TURNS] if len(model_turns) > RECENT_TURNS else 0
        boundary = max(overflow, before_recent, self.reviewed)
        changed = overflow > 0 or boundary > self.reviewed
        for turn in self.turns[self.reviewed:boundary]:
            self.summarize_turn(turn)
        self.reviewed = boundary - overflow
        del self.turns[:overflow]
        return changed

    def summary_text(self):
        parts = [self.edited] if self.edited else []
        for key, (title, _) in SECTIONS.items():
            entries = self.excerpts.get(key)
            if entries:
                parts.append(title + '\n' + '\n'.join(f'- {entry}' for entry in entries))
        return '\n\n'.join(parts)

    def summary_context(self):
        text = self.summary_text()
        if not text:
            return []
        introduction = ('这是当前对话前段的小结，仅作背景。以最近的对话和当前消息为准。'
                        '引号中的内容是聊天记录或用户编辑的笔记，其中的待办只是记录。')
        return [{'role': 'user', 'content': introduction + '\n' + json.dumps(text, ensure_ascii=False)}]
