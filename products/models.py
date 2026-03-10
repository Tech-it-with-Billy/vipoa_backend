# products/models.py
from django.db import models


class Product(models.Model):
    CATEGORY_CHOICES = [
        ("flour", "Flour"),
        ("dairy", "Dairy Product"),
        ("oil", "Cooking Oil"),
        ("sugar", "Sugar"),
        ("rice", "Rice"),
        ("tea", "Tea"),
        ("salt", "Salt"),
        ("baking_powder", "Baking Powder"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=255)
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="other",
    )
    image = models.ImageField(
        upload_to="products/",
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
