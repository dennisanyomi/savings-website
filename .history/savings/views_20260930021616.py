from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Member
from .permissions import admin_required


@login_required
def dashboard(request):
    member = Member.objects.filter(user=request.user).first()
    return render(request, "dashboard.html", {"member": member})


@admin_required
def admin_home(request):
    return render(request, "admin_home.html")