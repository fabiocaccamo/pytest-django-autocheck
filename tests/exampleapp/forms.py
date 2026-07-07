"""Project ModelForms used to exercise the forms check."""

from django import forms

from tests.exampleapp.models import Author


class AuthorForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ["name"]
