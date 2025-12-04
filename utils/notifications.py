def create_notification(user_id: int, message: str, link_url: str | None = None, *, commit: bool = True):
    """
    Create a notification for a specific user.
    Does not send email; only stores in DB.
    """
    if not user_id:
        return None

    from eleva_app import db
    from eleva_app.models import Notification

    notif = Notification(
        user_id=user_id,
        message=(message or "")[:255],
        link_url=link_url or "",
    )
    db.session.add(notif)
    if commit:
        db.session.commit()
    return notif
