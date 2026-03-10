def award_survey_points(user, survey):
    """
    Hook into your PoaPoints or gamification system.
    For now we return the survey.reward_points value.
    """

    points = survey.points_reward

    # 🔗 Example integration (uncomment when ready):
    # from gamification.services import PoaPointsService
    # PoaPointsService.add_points(
    #     user=user,
    #     amount=points,
    #     reason=f"Completed survey: {survey.slug}",
    # )

    return points
