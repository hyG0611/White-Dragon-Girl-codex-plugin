"""Choose existing animations for work states and quota results."""

ACTIVITY_REACTIONS = {
    'thinking': ('工作状态-思考冒泡', '深度思考碎碎念', '鲸鱼吐泡泡特效'),
    'working': ('工作状态-忙碌点按', '写代码', '轻快记录'),
    'attention': ('工作状态-原地踱步张望', '东张西望'),
}

QUOTA_REACTIONS = (
    (0, ('余额-分文不剩', '被吓一跳')),
    (10, ('余额-袋空如洗', '点击回应-害羞惊讶')),
    (25, ('余额-数金皱眉', '深度思考碎碎念')),
    (50, ('余额-钱袋如常', '轻快记录')),
    (75, ('余额-金袋叮当', '点击回应-开心跃动')),
    (100, ('余额-钱袋满溢', '轻快摇摆舞')),
)


def quota_reaction(windows):
    if not windows:
        return ()
    remaining = 100 - max(window['used_percent'] for window in windows)
    return next((actions for limit, actions in QUOTA_REACTIONS if remaining <= limit), ())
