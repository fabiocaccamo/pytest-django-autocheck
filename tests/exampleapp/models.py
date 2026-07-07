from django.db import models


class Author(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self) -> str:
        return self.name


class Book(models.Model):
    title = models.CharField(max_length=255)
    author = models.ForeignKey(
        Author,
        on_delete=models.CASCADE,
        related_name="books",
    )

    def __str__(self) -> str:
        return self.title


class AuthorProxy(Author):
    """Proxy model: must be skipped by the models check (no own table)."""

    class Meta:
        proxy = True


class UnmanagedThing(models.Model):
    """Unmanaged model: must be skipped by the models check (no table)."""

    name = models.CharField(max_length=255)

    class Meta:
        managed = False

    def __str__(self) -> str:
        return self.name
