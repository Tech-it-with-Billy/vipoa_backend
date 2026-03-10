from django.urls import path
from .api import views

urlpatterns = [
    path("wallet/", views.wallet_me, name="rewards-wallet-me"),
    path("transactions/", views.transactions_me, name="rewards-transactions-me"),
    path("claims/", views.claims_me, name="rewards-claims-me"),
    path("redeem/", views.redeem, name="rewards-redeem"),
]

