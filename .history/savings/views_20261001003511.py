from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .models import Payout

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
def round_total(round_obj):
    return (
        Payment.objects.filter(status="confirmed", day__round=round_obj)
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )


@admin_required
def admin_home(request):
    today = timezone.localdate()
    current_round = Round.objects.filter(status="active").select_related("recipient__user").first()
    target = DAYS_PER_ROUND * Member.objects.count() * DAILY_AMOUNT
    collected = round_total(current_round) if current_round else 0

    context = {
        "pending": Payment.objects.filter(status="pending")
            .select_related("member__user", "day").order_by("submitted_at"),
        "current_round": current_round,
        "collected": collected,
        "target": target,
        "payout_ready": bool(current_round) and target > 0 and collected >= target,
        "upcoming_days": ContributionDay.objects.filter(date__gte=today).order_by("date")[:14],
        "recent": Payment.objects.filter(status="confirmed")
            .select_related("member__user", "day", "confirmed_by").order_by("-confirmed_at")[:10],
    }
    return render(request, "admin_home.html", context)


@admin_required
@require_POST
def confirm_payment(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if payment.status != "pending":
        messages.error(request, "That payment is no longer pending.")
    else:
        payment.status = "confirmed"
        payment.confirmed_by = request.user
        payment.confirmed_at = timezone.now()
        payment.save()
        messages.success(request, f"Confirmed: {payment.member}, {payment.day}.")
    return redirect("admin_home")


@admin_required
@require_POST
def reject_payment(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if payment.status != "pending":
        messages.error(request, "That payment is no longer pending.")
    else:
        payment.status = "rejected"
        payment.save()
        messages.success(request, f"Rejected: {payment.member}, {payment.day}. They can resubmit.")
    return redirect("admin_home")


@admin_required
@require_POST
def toggle_skip(request, pk):
    day = get_object_or_404(ContributionDay, pk=pk)
    if day.date < timezone.localdate():
        messages.error(request, "You can only skip or restore today or future days.")
        return redirect("admin_home")
    if day.payments.exists():
        messages.error(request, "That day already has payments, so it can't be skipped.")
        return redirect("admin_home")

    with transaction.atomic():
        was_full = ContributionDay.objects.filter(is_skipped=False).count() >= TOTAL_DAYS
        day.is_skipped = not day.is_skipped
        day.round = None
        day.save()
        reassign_days(ensure_full=was_full)

    last_day = ContributionDay.objects.filter(round__isnull=False).order_by("-date").first()
    if last_day and last_day.date > SEMESTER_END:
        messages.warning(request, f"The last contribution day is now {last_day.date:%d %b %Y}, after the semester ends.")
    else:
        messages.success(request, f"{day.date:%a %d %b} is now {'skipped' if day.is_skipped else 'a contribution day'}.")
    return redirect("admin_home")


@admin_required
@require_POST
def record_payout(request, pk):
    round_obj = get_object_or_404(Round, pk=pk)
    target = DAYS_PER_ROUND * Member.objects.count() * DAILY_AMOUNT
    collected = round_total(round_obj)

    if round_obj.status != "active" or hasattr(round_obj, "payout"):
        messages.error(request, "This round is not active or was already paid out.")
    elif collected < target:
        messages.error(request, "The full amount has not been confirmed yet.")
    else:
        with transaction.atomic():
            Payout.objects.create(round=round_obj, amount=collected, recorded_by=request.user)
            round_obj.status = "paid_out"
            round_obj.save()
            Round.objects.filter(number=round_obj.number + 1).update(status="active")
        messages.success(request, f"Payout of GH₵ {collected:.0f} recorded for {round_obj.recipient}.")
    return redirect("admin_home")