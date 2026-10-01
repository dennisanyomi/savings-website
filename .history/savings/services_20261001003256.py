from datetime import date, timedelta

from .models import ContributionDay, Round

DAILY_AMOUNT = 20
DAYS_PER_ROUND = 8
TOTAL_DAYS = 80
SEMESTER_END = date(2027, 2, 14)


def reassign_days(ensure_full):
    """Re-sort which round each school day belongs to after a day is skipped or restored.
    If ensure_full is True and skipping left fewer than 80 days, add days at the end."""
    rounds = list(Round.objects.order_by("number"))
    days = list(ContributionDay.objects.filter(is_skipped=False).order_by("date"))

    if ensure_full:
        while len(days) < TOTAL_DAYS:
            last = ContributionDay.objects.order_by("-date").first().date
            nxt = last + timedelta(days=1)
            while nxt.weekday() >= 5:  # jump over Saturday and Sunday
                nxt += timedelta(days=1)
            days.append(ContributionDay.objects.create(date=nxt))

    for i, day in enumerate(days):
        index = i // DAYS_PER_ROUND
        new_round = rounds[index] if i < TOTAL_DAYS and index < len(rounds) else None
        new_id = new_round.id if new_round else None
        if day.round_id != new_id:
            day.round = new_round
            day.save(update_fields=["round"])