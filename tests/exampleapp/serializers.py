"""Project DRF serializers used to exercise the serializers check."""

from rest_framework import serializers

from tests.exampleapp.models import Author


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "name"]
