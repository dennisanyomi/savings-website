from django.db import models

# Create your models here.
from django.conf import settings
from django.db import models


class Member(models.Model):
    """One of the 10 people in the savings group."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    phone = models.CharField(max_length=15, blank=True)
    payout_position = models.PositiveSmallIntegerField(
        unique=True,
        help_text="Order in which this member receives the pot (1 to 10).",
    )

    class Meta:
        ordering = ["payout_position"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Round(models.Model):
    """One 6-day cycle. One member receives the pot at the end."""
    STATUS_CHOICES = [
        ("upcoming", "Upcoming"),
        ("active", "Active"),
        ("paid_out", "Paid out"),
    ]
    number = models.PositiveSmallIntegerField(unique=True)
    recipient = models.ForeignKey(Member, on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="upcoming")

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"Round {self.number} ({self.recipient})"


class ContributionDay(models.Model):
    """A school day on which members contribute."""
    date = models.DateField(unique=True)
    round = models.ForeignKey(
        Round, on_delete=models.PROTECT, related_name="days", null=True, blank=True
    )
    is_skipped = models.BooleanField(
        default=False,
        help_text="Tick for holidays or days with no school. No contributions are due.",
    )

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return self.date.strftime("%a %d %b %Y")


class Payment(models.Model):
    """A member's 20 cedi contribution for one day."""
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("rejected", "Rejected"),
    ]
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="payments")
    day = models.ForeignKey(ContributionDay, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=20)
    momo_reference = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    method = models.CharField(max_length=10, default="manual")
    submitted_at = models.DateTimeField(auto_now_add=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="confirmed_payments",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(fields=["member", "day"], name="one_payment_per_member_per_day"),
        ]

    def __str__(self):
        return f"{self.member} - {self.day} - {self.status}"


class Payout(models.Model):
    """Record that the pot for a round was sent to the recipient."""
    round = models.OneToOneField(Round, on_delete=models.PROTECT, related_name="payout")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    sent_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    def __str__(self):
        return f"Payout for {self.round}: {self.amount}"