from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from .models import ContributionDay, Member, Payment, Round
from .permissions import admin_required

from .services import DAILY_AMOUNT, DAYS_PER_ROUND, SEMESTER_END, TOTAL_DAYS, reassign_days


@login_required
def dashboard(request):
    member = Member.objects.filter(user=request.user).first()
    members = Member.objects.select_related("user")
    today = timezone.localdate()

    today_day = ContributionDay.objects.filter(date=today).first()
    current_round = (
        Round.objects.filter(status="active").select_related("recipient__user").first()
    )

    # Progress of the active round
    collected = 0
    days_done = 0
    if current_round:
        collected = (
            Payment.objects.filter(status="confirmed", day__round=current_round)
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )
        days_done = current_round.days.filter(is_skipped=False, date__lte=today).count()

    target = DAYS_PER_ROUND * members.count() * DAILY_AMOUNT
    percent = int(collected * 100 / target) if target else 0

    # Who has paid today
    today_status = []
    if today_day and not today_day.is_skipped:
        payments = {p.member_id: p.status for p in today_day.payments.all()}
        for m in members:
            today_status.append({"member": m, "status": payments.get(m.id, "unpaid")})

    all_rounds = Round.objects.select_related("recipient__user")

    context = {
        "member": member,
        "current_round": current_round,
        "collected": collected,
        "target": target,
        "percent": percent,
        "days_done": days_done,
        "days_per_round": DAYS_PER_ROUND,
        "today_status": today_status,
        "all_rounds": all_rounds,
    }
    return render(request, "dashboard.html", context)


@admin_required
def admin_home(request):
    return render(request, "admin_home.html")