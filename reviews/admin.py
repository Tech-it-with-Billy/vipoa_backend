# from django.contrib import admin
# from django.utils.html import format_html
# from .models import Product, Capture, Review


# # ==========================================================
# # PRODUCT ADMIN
# # ==========================================================
# @admin.register(Product)
# class ProductAdmin(admin.ModelAdmin):
#     list_display = ("id", "name", "category")
#     search_fields = ("name",)
#     list_filter = ("category",)


# # ==========================================================
# # CAPTURE ADMIN
# # ==========================================================
# @admin.register(Capture)
# class CaptureAdmin(admin.ModelAdmin):
#     list_display = (
#         "id",
#         "user",
#         "category",
#         "size",
#         "price",
#         "location",
#         "image_preview",
#         "created_at",
#     )
#     search_fields = ("user__email", "location", "category")
#     list_filter = ("category", "location")
#     readonly_fields = ("created_at", "image_preview")

#     def image_preview(self, obj):
#         if not obj.image:
#             return "-"
#         return format_html(
#             '<img src="{}" style="height:60px;width:auto;border-radius:4px;" />',
#             obj.image.url,
#         )

#     image_preview.short_description = "Preview"


# # ==========================================================
# # REVIEW ADMIN
# # ==========================================================
# @admin.register(Review)
# class ReviewAdmin(admin.ModelAdmin):
#     list_display = (
#         "id",
#         "user",
#         "capture",
#         "product",
#         "custom_product_name",
#         "review_text",
#         "created_at",
#     )
#     search_fields = (
#         "user__email",
#         "custom_product_name",
#         "product__name",
#         "review_text",
#     )
#     list_filter = ("created_at",)

#     readonly_fields = ("created_at",)
