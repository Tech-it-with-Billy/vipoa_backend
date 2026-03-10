from django.conf import settings
from django.db import models
from django.utils import timezone


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
        default="other"
    )
    image = models.ImageField(
        upload_to="products/",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Capture(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="captures",
    )
    image = models.ImageField(upload_to="review_captures/")
    category = models.CharField(max_length=50)
    size = models.CharField(max_length=100)
    price = models.CharField(max_length=50)
    location = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Capture #{self.id} by {self.user} ({self.category})"


class Review(models.Model):
    # 🔥 Must be nullable because DB already has rows where user_id = NULL
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
        null=True,          # REQUIRED for migrations
        blank=True,         # allows admin form saving
    )

    # 🔥 Must be nullable because DB already has NULL captures
    capture = models.ForeignKey(
        Capture,
        on_delete=models.CASCADE,
        related_name="reviews",
        null=True,          # REQUIRED for migrations
        blank=True,         # allows admin form saving
    )

    # Optional product reference
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviews",
    )

    custom_product_name = models.CharField(
        max_length=255,
        blank=True,
        default=""
    )

    review_text = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        base = f"Review #{self.id}"
        if self.user:
            base += f" by {self.user}"

        if self.product:
            return f"{base} on {self.product}"
        if self.custom_product_name:
            return f"{base} on {self.custom_product_name}"
        return base
