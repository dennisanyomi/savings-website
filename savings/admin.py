from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Member, Round, ContributionDay, Payment, Payout

admin.site.register(Member)
admin.site.register(Round)
admin.site.register(ContributionDay)
admin.site.register(Payment)
admin.site.register(Payout)