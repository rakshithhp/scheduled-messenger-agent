"""
Elastic Beanstalk looks for application:application by default.
This exposes our Flask app so EB works with or without a custom Procfile.
"""
from app import app as application  # noqa: F401
