"""
app/routes/pages.py
HTML page routes (non-API).
"""

from flask import Blueprint, render_template, redirect, session
from app.decorators import login_required

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def index():
    if "user_id" not in session:
        return redirect("/login")
    return redirect("/home")


@pages_bp.route("/home")
@login_required
def home():
    return render_template(
        "main.html",
        user_name=session.get("nombre"),
        user_rol=session.get("rol"),
    )
