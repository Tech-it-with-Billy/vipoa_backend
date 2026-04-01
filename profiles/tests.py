from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from profiles.models import Referral, SupabaseUser
from rewards.domain.constants import RewardEventType
from rewards.domain.keys import referral_milestone_key
from rewards.models import PoaPointsTransaction, RewardClaim


@override_settings(SECURE_SSL_REDIRECT=False)
class ReferralApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.referrer = SupabaseUser.objects.create_user(email="referrer@example.com")
        self.referred = SupabaseUser.objects.create_user(email="referred@example.com")
        self.profile_url = reverse("profile-me")
        self.leaderboard_url = reverse("referral-leaderboard")

    def _authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_referral_creation_success(self):
        self._authenticate(self.referred)
        response = self.client.patch(self.profile_url, {"referred_by": self.referrer.profile.referral_code}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Referral.objects.count(), 1)
        self.referred.profile.refresh_from_db()
        self.assertEqual(self.referred.profile.referred_by, self.referrer.profile.referral_code)

    def test_referral_creation_case_insensitive(self):
        self._authenticate(self.referred)
        response = self.client.patch(self.profile_url, {"referred_by": self.referrer.profile.referral_code.lower()}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Referral.objects.count(), 1)

    def test_duplicate_referral_silently_skipped(self):
        self._authenticate(self.referred)
        payload = {"referred_by": self.referrer.profile.referral_code}
        first_response = self.client.patch(self.profile_url, payload, format="json")
        second_response = self.client.patch(self.profile_url, payload, format="json")
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(Referral.objects.count(), 1)

    def test_self_referral_silently_skipped(self):
        self._authenticate(self.referrer)
        response = self.client.patch(self.profile_url, {"referred_by": self.referrer.profile.referral_code}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Referral.objects.count(), 0)

    def test_invalid_referral_code_silently_skipped(self):
        self._authenticate(self.referred)
        response = self.client.patch(self.profile_url, {"referred_by": "INVALIDCODE"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Referral.objects.count(), 0)

    def test_referred_by_only_accepted_once(self):
        other_referrer = SupabaseUser.objects.create_user(email="other@example.com")
        self._authenticate(self.referred)
        self.client.patch(self.profile_url, {"referred_by": self.referrer.profile.referral_code}, format="json")
        self.client.patch(self.profile_url, {"referred_by": other_referrer.profile.referral_code}, format="json")
        self.assertEqual(Referral.objects.filter(referred_user=self.referred).count(), 1)
        self.referred.profile.refresh_from_db()
        self.assertEqual(self.referred.profile.referred_by, self.referrer.profile.referral_code)

    def test_referral_leaderboard_uses_correct_relation(self):
        other_referrer = SupabaseUser.objects.create_user(email="referrer2@example.com")
        user_a = SupabaseUser.objects.create_user(email="a@example.com")
        user_b = SupabaseUser.objects.create_user(email="b@example.com")
        user_c = SupabaseUser.objects.create_user(email="c@example.com")
        Referral.objects.create(referrer=self.referrer, referred_user=user_a)
        Referral.objects.create(referrer=self.referrer, referred_user=user_b)
        Referral.objects.create(referrer=other_referrer, referred_user=user_c)
        self._authenticate(self.referred)
        response = self.client.get(self.leaderboard_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["user"], self.referrer.id)
        self.assertEqual(response.data[0]["referral_count"], 2)


@override_settings(REFERRAL_REWARD_MILESTONES={2: 10}, SECURE_SSL_REDIRECT=False)
class ReferralRewardSignalTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.referrer = SupabaseUser.objects.create_user(email="reward-referrer@example.com")
        self.profile_url = reverse("profile-me")

    def _apply_referral(self, suffix):
        referred_user = SupabaseUser.objects.create_user(email="referred-{}@example.com".format(suffix))
        self.client.force_authenticate(user=referred_user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(self.profile_url, {"referred_by": self.referrer.profile.referral_code}, format="json")
        return response

    def test_reward_not_applied_before_milestone(self):
        response = self._apply_referral("one")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(PoaPointsTransaction.objects.filter(user=self.referrer, type=RewardEventType.REFERRAL_MILESTONE).exists())

    def test_reward_applied_at_milestone(self):
        self._apply_referral("one")
        response = self._apply_referral("two")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        key = referral_milestone_key(self.referrer.id, 2)
        tx = PoaPointsTransaction.objects.get(reference_key=key)
        self.assertEqual(tx.amount, 10)

    def test_reward_not_duplicated_after_milestone(self):
        self._apply_referral("one")
        self._apply_referral("two")
        self._apply_referral("three")
        key = referral_milestone_key(self.referrer.id, 2)
        self.assertEqual(PoaPointsTransaction.objects.filter(reference_key=key).count(), 1)
        self.assertEqual(RewardClaim.objects.filter(user=self.referrer, reference_key=key).count(), 1)

    def test_repeated_request_does_not_duplicate_reward(self):
        repeated_user = SupabaseUser.objects.create_user(email="repeated@example.com")
        self.client.force_authenticate(user=repeated_user)
        payload = {"referred_by": self.referrer.profile.referral_code}
        with self.captureOnCommitCallbacks(execute=True):
            first = self.client.patch(self.profile_url, payload, format="json")
        with self.captureOnCommitCallbacks(execute=True):
            second = self.client.patch(self.profile_url, payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(Referral.objects.filter(referred_user=repeated_user).count(), 1)
