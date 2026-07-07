"""Project-style factory_boy factories used to exercise factory discovery.

The presence of these factories makes the models and admin checks prefer them
over model_bakery for ``Author`` and ``Book``.
"""

import factory

from tests.exampleapp.models import Author, Book


class AbstractFactory(factory.django.DjangoModelFactory):
    """Abstract factory: has no model and must be ignored by discovery."""

    class Meta:
        abstract = True


class AuthorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Author

    name = factory.Sequence(lambda n: f"Author {n}")


class AuthorAltFactory(factory.django.DjangoModelFactory):
    """Second factory for the same model: first one wins, this is ignored."""

    class Meta:
        model = Author

    name = factory.Sequence(lambda n: f"Alt author {n}")


class BookFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Book

    title = factory.Sequence(lambda n: f"Book {n}")
    author = factory.SubFactory(AuthorFactory)
