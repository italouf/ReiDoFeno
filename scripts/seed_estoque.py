"""Semeadura de estoque demo (wrapper do comando transacional)."""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.core.management import call_command  # noqa: E402

call_command("semear_estoque_demo")
