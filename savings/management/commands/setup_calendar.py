from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from savings.models import ContributionDay, Member, Round

START = date(2026, 10, 19)
END = date(2027, 2, 14)
HOLIDAYS = {date(2026, 12, 4), date(2026, 12, 25), date(2027, 1, 1), date(2027, 1, 7)}
TOTAL_DAYS = 80
DAYS_PER_ROUND = 8


class Command(BaseCommand):
    help = "Creates the 80 contribution days, the holidays, and the 10 rounds."

    @transaction.atomic
    def handle(self, *args, **options):
        members = list(Member.objects.order_by("payout_position"))
        if len(members) != 10:
            raise CommandError(
                f"Need exactly 10 members, found {len(members)}. Add the rest in /admin/ first."
            )
        if ContributionDay.objects.exists() or Round.objects.exists():
            raise CommandError("Days or rounds already exist. Delete the test data in /admin/ first.")

        # One round per member, in payout order
        rounds = [
            Round.objects.create(
                number=i + 1,
                recipient=m,
                status="active" if i == 0 else "upcoming",
            )
            for i, m in enumerate(members)
        ]

        school_days = 0
        holidays_added = 0
        current = START
        while school_days < TOTAL_DAYS:
            if current > END:
                raise CommandError(
                    f"Only {school_days} school days fit before {END}. Nothing was saved."
                )
            if current.weekday() < 5:  # Monday to Friday
                if current in HOLIDAYS:
                    ContributionDay.objects.create(date=current, is_skipped=True)
                    holidays_added += 1
                else:
                    ContributionDay.objects.create(
                        date=current, round=rounds[school_days // DAYS_PER_ROUND]
                    )
                    school_days += 1
                    last_day = current
            current += timedelta(days=1)

        self.stdout.write(self.style.SUCCESS(
            f"Created {school_days} contribution days, {holidays_added} holidays, "
            f"{len(rounds)} rounds. Last contribution day: {last_day:%a %d %b %Y}."
        ))