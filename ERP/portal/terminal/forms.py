from django import forms

DEFECT_LINES = 3


class CompleteForm(forms.Form):
    """Up to three optional defect lines; the completed quantity itself isn't editable."""

    def __init__(self, *args, reasons=(), **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", "No defect")] + [(r["name"], f"{r['name']} ({r['category']})") for r in reasons]
        for i in range(1, DEFECT_LINES + 1):
            self.fields[f"reason_{i}"] = forms.ChoiceField(choices=choices, required=False, label=f"Defect {i}")
            self.fields[f"qty_{i}"] = forms.IntegerField(
                min_value=1, required=False, label="Qty", widget=forms.NumberInput(attrs={"inputmode": "numeric", "aria-label": f"Defect {i} quantity"})
            )

    def clean(self):
        data = super().clean()
        for i in range(1, DEFECT_LINES + 1):
            reason, qty = data.get(f"reason_{i}"), data.get(f"qty_{i}")
            if qty and not reason:
                self.add_error(f"reason_{i}", "Pick a reason for this quantity.")
            if reason and not qty:
                self.add_error(f"qty_{i}", "Enter how many.")
        return data

    def lines(self):
        """(reason field, qty field) pairs for the template."""
        return [(self[f"reason_{i}"], self[f"qty_{i}"]) for i in range(1, DEFECT_LINES + 1)]

    def defects(self):
        return [
            (self.cleaned_data[f"reason_{i}"], self.cleaned_data[f"qty_{i}"])
            for i in range(1, DEFECT_LINES + 1)
            if self.cleaned_data.get(f"reason_{i}") and self.cleaned_data.get(f"qty_{i}")
        ]
