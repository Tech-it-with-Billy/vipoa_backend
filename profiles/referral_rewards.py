import logging
from typing import Iterable

from django.conf import settings

from rewards.services.events import award_referral_milestone

logger = logging.getLogger(__name__)


DEFAULT_REFERRAL_REWARD_MILESTONES = (
    (1, 10),
    (2, 10),
    (3, 10),
    (4, 10),
    (5, 10),
    (6, 10),
    (7, 10),
    (8, 10),
    (9, 10),
    (30, 300),
)


def _coerce_milestones(raw_milestones) -> tuple[tuple[int, int], ...]:
    normalized: dict[int, int] = {}

    if isinstance(raw_milestones, dict):
        iterable: Iterable = raw_milestones.items()
    else:
        iterable = raw_milestones or []

    for item in iterable:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            milestone, amount = item
        else:
            continue

        try:
            milestone = int(milestone)
            amount = int(amount)
        except (TypeError, ValueError):
            continue

        if milestone <= 0 or amount <= 0:
            continue

        normalized[milestone] = amount

    if not normalized:
        return DEFAULT_REFERRAL_REWARD_MILESTONES

    return tuple(sorted(normalized.items(), key=lambda item: item[0]))


def get_referral_reward_milestones() -> tuple[tuple[int, int], ...]:
    raw = getattr(settings, "REFERRAL_REWARD_MILESTONES", DEFAULT_REFERRAL_REWARD_MILESTONES)
    milestones = _coerce_milestones(raw)
    return milestones


def process_referral_rewards(*, referrer_user, referral_count: int):
    milestones = get_referral_reward_milestones()
    logger.info(
        "referral.milestone_check user_id=%s referral_count=%s milestones=%s",
        referrer_user.id,
        referral_count,
        milestones,
    )

    results = []
    for milestone, amount in milestones:
        if referral_count < milestone:
            continue

        result = award_referral_milestone(
            user=referrer_user,
            milestone=milestone,
            count=referral_count,
            amount=amount,
        )
        logger.info(
            "referral.reward_attempt user_id=%s referral_count=%s milestone=%s outcome=%s amount=%s",
            referrer_user.id,
            referral_count,
            milestone,
            result.outcome,
            amount,
        )
        results.append((milestone, result))

    return results