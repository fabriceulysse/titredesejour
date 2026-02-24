#!/usr/bin/env python3
"""
Titre de Séjour Appointment Monitor
=====================================
Monitors rdv-prefecture.interieur.gouv.fr for available appointment slots
and sends email notifications when slots open up.

API Discovery Notes (from Playwright network interception):
----------------------------------------------------------
The rdv-prefecture.interieur.gouv.fr site is a server-rendered Django application.
The booking flow proceeds through these URLs in order:

  1. /rdvpref/reservation/demarche/{DEMARCHE_ID}/
     Landing page — shows the demarche name and a "Start" button.

  2. /rdvpref/reservation/demarche/{DEMARCHE_ID}/creneau/
     Slot availability page — the key endpoint we monitor.
     - When NO slots exist, the page contains:
         "Aucun créneau disponible" OR "pas de plage horaire disponible"
     - When slots EXIST, the page contains a date-picker or a list of
         available <div class="creneau"> elements with data-date attributes.
     - The server returns full HTML (SSR); no separate JSON API is needed.
     - A CSRF token cookie ("csrftoken") is required (standard Django behaviour).
       The session does NOT need to be authenticated for this read-only check.

  3. /rdvpref/reservation/demarche/{DEMARCHE_ID}/cgu/
     CGU acceptance — only relevant if the user is actually booking.

  4. /rdvpref/reservation/demarche/{DEMARCHE_ID}/coordonnees/
     Personal-details form — only relevant for actual booking.

Monitoring strategy (no browser required):
  - Open an HTTP session (to receive cookies automatically).
  - GET the landing page once to receive the csrftoken cookie.
  - GET the /creneau/ endpoint and inspect the response body.
  - Parse HTML for slot availability markers.
  - If slots are found, send email to all configured recipients.

Rate-limiting / politeness:
  - The GitHub Actions cron is set to every 5 minutes — well within
    reasonable limits for a single-demarche check.
  - We set a realistic User-Agent and a Referer header.
  - On HTTP errors (429, 503 …) we log a warning and exit cleanly
    so the workflow does not show a red cross for transient failures.
"""

import json
import logging
import os
import re
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL = "https://www.rdv-prefecture.interieur.gouv.fr"

# Phrases that appear in the HTML when NO slots are available.
# We check for them case-insensitively.
NO_SLOT_MARKERS = [
    "aucun créneau disponible",
    "aucun creneau disponible",
    "pas de plage horaire disponible",
    "il n'existe plus de plage horaire",
    "il n'existe pas de plage horaire",
    "nous ne sommes pas en mesure",
    "no available",
]

# CSS selectors / patterns that indicate slots ARE available.
# If the page contains a slot element, we consider there to be availability.
SLOT_SELECTORS = [
    "div.creneau",          # slot card
    "button.creneau",       # slot button
    "input[type='radio']",  # slot radio button (older layout)
    "a.creneau",
    "[data-date]",          # generic date attribute
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------
def load_config(path: str = "config.json") -> dict:
    """Load and validate config.json."""
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except FileNotFoundError:
        log.error("config.json not found. Please create it from the example in README.md.")
        sys.exit(1)
    except json.JSONDecodeError as exc:
        log.error("config.json is not valid JSON: %s", exc)
        sys.exit(1)

    required = ["departement", "demarche_id", "subscribers"]
    for key in required:
        if key not in cfg:
            log.error("config.json is missing required key: '%s'", key)
            sys.exit(1)

    if not cfg["subscribers"]:
        log.error("config.json 'subscribers' list is empty — no one to notify.")
        sys.exit(1)

    return cfg


# ---------------------------------------------------------------------------
# Availability checker
# ---------------------------------------------------------------------------
def build_urls(demarche_id: str) -> dict[str, str]:
    """Return the relevant URLs for a given demarche ID."""
    base = f"{BASE_URL}/rdvpref/reservation/demarche/{demarche_id}"
    return {
        "landing": f"{base}/",
        "creneau": f"{base}/creneau/",
        "book": f"{base}/cgu/",
    }


def get_available_slots(demarche_id: str, departement: str) -> list[dict]:
    """
    Query the rdv-prefecture creneau page and return a list of available slots.

    Each slot dict contains at least:
        {"date": "...", "time": "...", "label": "..."}

    Returns an empty list when no slots are found.
    Raises RuntimeError on unrecoverable errors so the caller can log and exit.
    """
    urls = build_urls(demarche_id)
    session = requests.Session()
    session.headers.update(HEADERS)

    # ── Step 1: hit the landing page to receive session + CSRF cookies ──────
    log.info("Fetching landing page: %s", urls["landing"])
    try:
        landing = session.get(urls["landing"], timeout=REQUEST_TIMEOUT)
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(f"Cannot reach rdv-prefecture.interieur.gouv.fr: {exc}") from exc
    except requests.exceptions.Timeout:
        raise RuntimeError("Timeout while connecting to rdv-prefecture.interieur.gouv.fr")

    if landing.status_code == 404:
        raise RuntimeError(
            f"Demarche {demarche_id} not found (HTTP 404). "
            "Check the demarche_id in config.json."
        )
    if landing.status_code == 429:
        raise RuntimeError("Rate-limited (HTTP 429). Will retry at next scheduled run.")
    if landing.status_code not in (200, 302):
        raise RuntimeError(
            f"Unexpected HTTP {landing.status_code} on landing page. "
            "The site may be under maintenance."
        )

    # ── Step 2: fetch the creneau page ──────────────────────────────────────
    log.info("Fetching creneau page: %s", urls["creneau"])
    try:
        resp = session.get(
            urls["creneau"],
            headers={"Referer": urls["landing"]},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Error fetching creneau page: {exc}") from exc

    if resp.status_code == 429:
        raise RuntimeError("Rate-limited (HTTP 429). Will retry at next scheduled run.")
    if resp.status_code not in (200, 302):
        raise RuntimeError(
            f"Unexpected HTTP {resp.status_code} on creneau page. "
            "The site may be temporarily unavailable."
        )

    # ── Step 3: parse the response ──────────────────────────────────────────
    html = resp.text
    return _parse_slots(html, urls["book"])


def _parse_slots(html: str, booking_url: str) -> list[dict]:
    """
    Parse the creneau page HTML and return a list of available slot dicts.

    Strategy:
      1. If any NO_SLOT_MARKER phrase is found → return [].
      2. Otherwise, look for slot elements with known CSS selectors.
      3. If no slot elements are found but the page looks like a slot-picker
         (e.g. contains a date input), treat it as "slots may be available".
      4. Return structured slot info where parseable, else a generic sentinel.
    """
    text_lower = html.lower()

    # Fast-path: explicit "no slots" message
    for marker in NO_SLOT_MARKERS:
        if marker in text_lower:
            log.info("No-slot marker found: '%s'", marker)
            return []

    soup = BeautifulSoup(html, "html.parser")

    slots = []

    # Try each known slot selector
    for selector in SLOT_SELECTORS:
        elements = soup.select(selector)
        if elements:
            log.info("Found %d slot element(s) with selector '%s'", len(elements), selector)
            for el in elements:
                slot = _extract_slot_info(el)
                if slot:
                    slots.append(slot)
            break

    # If no structured slots found via CSS, check for date-picker patterns
    if not slots:
        slots = _extract_from_datepicker(soup)

    # If we still found nothing but there's also no "no-slot" marker,
    # check whether the page looks like the slot step at all.
    if not slots:
        if _page_looks_like_creneau_step(soup):
            # The page is the slot step but we can't parse individual slots.
            # Treat as "slots available — please check manually."
            log.info(
                "Creneau page loaded but slot structure not recognised; "
                "flagging as potentially available."
            )
            slots = [
                {
                    "date": "Unknown",
                    "time": "Unknown",
                    "label": "Slots may be available — please check manually.",
                    "booking_url": booking_url,
                }
            ]
        else:
            log.info("No slot indicators found on creneau page.")

    return slots


def _extract_slot_info(element) -> dict | None:
    """Extract date/time info from a slot element."""
    date = (
        element.get("data-date")
        or element.get("data-value")
        or element.get("value")
        or ""
    )
    time_str = element.get("data-time") or element.get("data-heure") or ""
    label = element.get_text(strip=True) or element.get("aria-label") or ""

    if not (date or label):
        return None

    return {"date": date, "time": time_str, "label": label}


def _extract_from_datepicker(soup) -> list[dict]:
    """Try to extract slot info from a date-picker widget."""
    slots = []

    # Look for <option> tags inside a select element that look like dates
    for option in soup.select("select option"):
        val = option.get("value", "").strip()
        text = option.get_text(strip=True)
        if val and val != "" and re.search(r"\d{4}-\d{2}-\d{2}", val):
            slots.append({"date": val, "time": "", "label": text})

    # Look for <td> or <li> elements with a date attribute (calendar widgets)
    for cell in soup.select("td[data-date], li[data-date]"):
        if "disabled" in cell.get("class", []):
            continue
        date = cell.get("data-date", "")
        if date:
            slots.append({"date": date, "time": "", "label": cell.get_text(strip=True)})

    return slots


def _page_looks_like_creneau_step(soup) -> bool:
    """
    Return True if the page appears to be the appointment slot selection step
    (as opposed to an error page, CGU page, or personal-details form).
    """
    page_text = soup.get_text(separator=" ", strip=True).lower()
    creneau_keywords = [
        "créneau",
        "creneau",
        "horaire",
        "date",
        "rendez-vous",
    ]
    return any(kw in page_text for kw in creneau_keywords)


# ---------------------------------------------------------------------------
# Email notifications
# ---------------------------------------------------------------------------
def send_notification(
    slots: list[dict],
    demarche_id: str,
    departement: str,
    subscribers: list[str],
    smtp_cfg: dict,
) -> None:
    """Send an email alert with the available slots to all subscribers."""
    booking_url = build_urls(demarche_id)["book"]
    subject = (
        f"🟢 Rendez-vous disponible — titre de séjour (demarche {demarche_id}, "
        f"dép. {departement})"
    )

    # Build slot table for the email body
    slot_lines_html = ""
    slot_lines_text = ""
    for s in slots[:20]:  # cap at 20 to keep email readable
        label = s.get("label") or f"{s.get('date', '')} {s.get('time', '')}".strip()
        slot_lines_html += f"<li>{label}</li>\n"
        slot_lines_text += f"  • {label}\n"

    html_body = f"""
<html><body>
<p>Bonjour,</p>
<p>Des créneaux de rendez-vous sont disponibles pour votre demarche
   (<strong>demarche {demarche_id}</strong>, département <strong>{departement}</strong>).</p>

<h3>Créneaux disponibles</h3>
<ul>
{slot_lines_html}
</ul>

<p><strong><a href="{booking_url}">👉 Cliquez ici pour prendre rendez-vous</a></strong></p>

<p>⚠️ <em>Agissez vite — les créneaux sont souvent pris en quelques minutes.</em></p>

<hr>
<p style="font-size:0.85em;color:#666;">
Ce message a été envoyé par le moniteur automatique de rendez-vous titre de séjour.
Le moniteur vérifie la disponibilité toutes les 5 minutes et vous prévient dès qu'un
créneau apparaît. Il ne prend pas rendez-vous à votre place — vous devez agir manuellement.
</p>
</body></html>
"""

    text_body = (
        f"Des créneaux de rendez-vous sont disponibles !\n\n"
        f"Demarche : {demarche_id}  |  Département : {departement}\n\n"
        f"Créneaux :\n{slot_lines_text}\n"
        f"Lien pour prendre rendez-vous :\n{booking_url}\n\n"
        "Agissez vite — les créneaux sont souvent pris en quelques minutes.\n"
    )

    smtp_host = smtp_cfg.get("host", "smtp.gmail.com")
    smtp_port = int(smtp_cfg.get("port", 587))
    smtp_user = smtp_cfg["user"]
    smtp_password = smtp_cfg["password"]

    for recipient in subscribers:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = recipient
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_user, recipient, msg.as_string())
            log.info("Email sent to %s", recipient)
        except smtplib.SMTPAuthenticationError:
            log.error(
                "SMTP authentication failed. Check SMTP_USER / SMTP_PASSWORD secrets."
            )
        except smtplib.SMTPException as exc:
            log.error("Failed to send email to %s: %s", recipient, exc)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main() -> None:
    log.info("=" * 60)
    log.info("Titre de Séjour Appointment Monitor — %s", datetime.now().isoformat())
    log.info("=" * 60)

    # Load config
    config = load_config()
    departement = str(config["departement"])
    demarche_id = str(config["demarche_id"])
    subscribers = config["subscribers"]
    log.info(
        "Config: département=%s  demarche_id=%s  subscribers=%d",
        departement,
        demarche_id,
        len(subscribers),
    )

    # Read SMTP credentials from environment (GitHub Secrets)
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    if not smtp_user or not smtp_password:
        log.warning(
            "SMTP_USER or SMTP_PASSWORD environment variables are not set. "
            "Slot availability will be logged but no email will be sent."
        )

    smtp_cfg = {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": smtp_user,
        "password": smtp_password,
    }

    # Check availability
    try:
        slots = get_available_slots(demarche_id, departement)
    except RuntimeError as exc:
        log.warning("Check skipped: %s", exc)
        log.info("Will retry at the next scheduled run.")
        sys.exit(0)  # exit 0 so GitHub Actions shows a green tick

    if not slots:
        log.info("No slots available. Will check again at the next scheduled run.")
        return

    # Slots found!
    log.info("*** %d slot(s) found! Sending notifications. ***", len(slots))
    for s in slots:
        log.info("  Slot: %s", s)

    if smtp_user and smtp_password:
        send_notification(slots, demarche_id, departement, subscribers, smtp_cfg)
    else:
        log.warning("No SMTP credentials — skipping email.")


if __name__ == "__main__":
    main()
