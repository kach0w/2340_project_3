"""Where the current user is, for filtering alerts (custom story 2).

Users type an address or a ZIP code; the ZIP is what alerts are filtered on,
and the text they typed is shown back to them. Logged-in users keep it on
their Profile so it follows them across devices/sessions; guests keep it in
the session.
"""
from accounts.models import Profile

SESSION_ZIP = 'zip_code'
SESSION_LOCATION = 'location'


def get_location(request):
    """(zip_code, label) for the current user; (None, None) if not set."""
    if request.user.is_authenticated:
        profile = Profile.objects.filter(user=request.user).first()
        if profile and profile.zip_code:
            return profile.zip_code, profile.location or profile.zip_code
    zip_code = request.session.get(SESSION_ZIP)
    if not zip_code:
        return None, None
    return zip_code, request.session.get(SESSION_LOCATION) or zip_code


def get_zip(request):
    return get_location(request)[0]


def set_location(request, zip_code, label=''):
    """Save the user's location, or clear it when zip_code is empty."""
    zip_code = zip_code or ''
    label = (label or zip_code).strip()[:255] if zip_code else ''
    if zip_code:
        request.session[SESSION_ZIP] = zip_code
        request.session[SESSION_LOCATION] = label
    else:
        request.session.pop(SESSION_ZIP, None)
        request.session.pop(SESSION_LOCATION, None)
    if request.user.is_authenticated:
        Profile.objects.update_or_create(
            user=request.user, defaults={'zip_code': zip_code, 'location': label},
        )
