from django import forms

from .models import Payment


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["momo_reference"]
        labels = {"momo_reference": "MoMo transaction ID"}

    def clean_momo_reference(self):
        # Store references in one format so "abc123" and "ABC123" count as the same
        return self.cleaned_data["momo_reference"].strip().upper()