from django.test import TestCase

from jema.models import ChatMessage, ChatSession
from profiles.models import SupabaseUser
from rewards.domain.constants import RewardEventType
from rewards.domain.keys import jema_first_interaction_key
from rewards.models import PoaPointsTransaction


class JemaRewardSignalTests(TestCase):
    def setUp(self):
        self.user = SupabaseUser.objects.create_user(email="jema-user@example.com")

    def test_first_user_message_awards_once(self):
        session = ChatSession.objects.create(user_id=str(self.user.id))

        ChatMessage.objects.create(session=session, role="user", content="Hello Jema")
        ChatMessage.objects.create(session=session, role="user", content="Second message")

        key = jema_first_interaction_key(self.user.id)
        tx_qs = PoaPointsTransaction.objects.filter(
            user=self.user,
            type=RewardEventType.JEMA_FIRST_INTERACTION,
            reference_key=key,
        )
        self.assertEqual(tx_qs.count(), 1)

    def test_assistant_message_does_not_award(self):
        session = ChatSession.objects.create(user_id=str(self.user.id))

        ChatMessage.objects.create(session=session, role="assistant", content="System response")

        self.assertFalse(
            PoaPointsTransaction.objects.filter(
                user=self.user,
                type=RewardEventType.JEMA_FIRST_INTERACTION,
            ).exists()
        )

    def test_missing_user_mapping_does_not_crash_or_award(self):
        session = ChatSession.objects.create(user_id="missing-user-id")

        ChatMessage.objects.create(session=session, role="user", content="Hello")

        self.assertEqual(
            PoaPointsTransaction.objects.filter(type=RewardEventType.JEMA_FIRST_INTERACTION).count(),
            0,
        )
