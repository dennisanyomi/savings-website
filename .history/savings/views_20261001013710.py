from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import PaymentForm
from .models import ContributionDay, Member, Payment, Payout, Round
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

@login_required
def submit_payment(request, day_id=None):
    member = Member.objects.filter(user=request.user).first()
    if not member:
        messages.error(request, "Your account is not linked to a group member.")
        return redirect("dashboard")

    today = timezone.localdate()
    days = ContributionDay.objects.select_related("round")
    day = days.filter(pk=day_id).first() if day_id else days.filter(date=today).first()
    back = "calendar" if day_id else "dashboard"

    if not day or day.is_skipped or not day.round_id:
        messages.error(request, "No contributions are due for that day.")
        return redirect(back)
    if day.date > today:
        messages.error(request, "You can't pay for a future day yet.")
        return redirect(back)
    if day.round.status == "paid_out":
        messages.error(request, "That round has already been paid out.")
        return redirect(back)

    existing = Payment.objects.filter(member=member, day=day).first()
    if existing and existing.status != "rejected":
        messages.info(request, f"You already submitted this payment ({existing.get_status_display()}).")
        return redirect(back)

    # If the earlier attempt was rejected, reuse that record so the member can try again
    form = PaymentForm(request.POST or None, instance=existing)
    if request.method == "POST" and form.is_valid():
        payment = form.save(commit=False)
        payment.member = member
        payment.day = day
        payment.amount = DAILY_AMOUNT
        payment.status = "pending"
        payment.confirmed_by = None
        payment.confirmed_at = None
        payment.save()
        messages.success(request, "Payment submitted. Waiting for the admin to confirm it.")
        return redirect(back)

    return render(request, "pay.html", {"form": form, "amount": DAILY_AMOUNT, "day": day})


@login_required
def calendar_view(request):
    member = Member.objects.filter(user=request.user).first()
    today = timezone.localdate()
    days = list(ContributionDay.objects.select_related("round").order_by("date"))
    if not days:
        return render(request, "calendar.html", {"weeks": [], "member": member})

    by_date = {d.date: d for d in days}
    statuses = {}
    if member:
        statuses = {p.day_id: p.status for p in Payment.objects.filter(member=member)}

    # Number the real contribution days 1, 2, 3...
    numbers = {}
    count = 0
    for d in days:
        if not d.is_skipped and d.round_id:
            count += 1
            numbers[d.id] = count

    def state_for(d):
        if d.is_skipped:
            return "holiday", None
        if not d.round_id:
            return "spare", None
        status = statuses.get(d.id)
        if status == "confirmed":
            return "paid", None
        if status == "pending":
            return "pending", None
        if d.date > today:
            return "future", None
        url = None
        if member and d.round.status != "paid_out":
            url = reverse("submit_payment_day", args=[d.id])
        return ("due" if d.date == today else "missed"), url

    weeks = []
    current = days[0].date - timedelta(days=days[0].date.weekday())  # the Monday of week 1
    last = days[-1].date
    while current <= last:
        cells = []
        for i in range(7):
            date = current + timedelta(days=i)
            d = by_date.get(date)
            if d:
                state, url = state_for(d)
                cells.append({"date": date, "state": state, "url": url,
                              "number": numbers.get(d.id), "today": date == today})
            else:
                cells.append({"date": date, "state": "weekend", "url": None,
                              "number": None, "today": date == today})
        weeks.append({"start": current, "cells": cells})
        current += timedelta(days=7)

    paid = sum(1 for d in days if statuses.get(d.id) == "confirmed")
    return render(request, "calendar.html", {
        "weeks": weeks, "member": member, "paid": paid, "total": count,
    })