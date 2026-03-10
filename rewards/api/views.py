from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rewards.models import RewardClaim


from rewards.services.wallet import wallet_snapshot
from rewards.api.serializers import RedemptionCreateSerializer
from rewards.services.redemption import create_and_confirm_redemption
from rewards.models import PoaPointsTransaction


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def wallet_me(request):
    return Response(wallet_snapshot(request.user, include_transactions=True))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def transactions_me(request):
    limit = int(request.query_params.get("limit", 20))
    limit = max(1, min(limit, 100))

    qs = PoaPointsTransaction.objects.filter(user=request.user).order_by("-created_at")[:limit]
    return Response([
        {
            "amount": t.amount,
            "type": t.type,
            "reference_key": t.reference_key,
            "created_at": t.created_at,
            "meta": t.meta,
        }
        for t in qs
    ])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def redeem(request):
    serializer = RedemptionCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    data = serializer.validated_data
    result = create_and_confirm_redemption(
        user=request.user,
        reference_key=data["reference_key"],
        cost=data["cost"],
        provider=data.get("provider", ""),
        target=data.get("target", ""),
        meta=data.get("meta", {}),
    )

    payload = {
        "outcome": result.outcome,
        "redemption": {
            "id": result.redemption.id,
            "reference_key": result.redemption.reference_key,
            "status": result.redemption.status,
            "cost": result.redemption.cost,
            "provider": result.redemption.provider,
            "target": result.redemption.target,
            "created_at": result.redemption.created_at,
            "confirmed_at": result.redemption.confirmed_at,
            "meta": result.redemption.meta,
        },
        "wallet": result.wallet,
    }

    http_status = status.HTTP_200_OK
    if result.outcome in {"INSUFFICIENT_FUNDS", "FAILED"}:
        http_status = status.HTTP_400_BAD_REQUEST

    return Response(payload, status=http_status)
    
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def claims_me(request):
    limit = int(request.query_params.get("limit", 20))
    limit = max(1, min(limit, 100))

    status_filter = request.query_params.get("status")
    event_type_filter = request.query_params.get("event_type")

    qs = RewardClaim.objects.filter(user=request.user).order_by("-created_at")

    if status_filter:
        qs = qs.filter(status=status_filter)

    if event_type_filter:
        qs = qs.filter(event_type=event_type_filter)

    qs = qs[:limit]

    return Response([
        {
            "reference_key": c.reference_key,
            "event_type": c.event_type,
            "event_id": c.event_id,
            "status": c.status,
            "created_at": c.created_at,
            "applied_at": c.applied_at,
            "meta": c.meta,
        }
        for c in qs
    ])
