#!/bin/bash
# Ensure application.py exists so gunicorn finds application:application
# (in case the bundle didn't include it)
cd /var/app/current
if [ ! -f application.py ]; then
  echo 'from app import app as application  # noqa: F401' > application.py
  echo "Created application.py in $(pwd)"
fi
