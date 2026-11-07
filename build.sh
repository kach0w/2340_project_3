#!/usr/bin/env bash
# Build step for the host (Render runs this on every deploy).
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input

# Create the admin account on first deploy if DJANGO_SUPERUSER_USERNAME,
# DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD are set. Ignored if
# the user already exists.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then
  python manage.py createsuperuser --no-input || true
fi
