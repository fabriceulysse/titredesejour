# Titre de Séjour Appointment Monitor

A free, open-source tool that watches the French government's appointment booking
site and sends you an email the moment a slot opens up — so you don't have to
refresh the page manually all day.

---

## What this tool does

Every 5 minutes, this tool quietly checks
[rdv-prefecture.interieur.gouv.fr](https://www.rdv-prefecture.interieur.gouv.fr)
for available appointment slots for your specific procedure and département.
The moment a slot appears, it emails everyone on your subscriber list with the
available dates and a direct link to the booking page.

**This tool only alerts you — it does not book an appointment for you.**
Once you receive an email, you must log in and complete the booking yourself.
Slots disappear within seconds, so act immediately when you receive the alert.

---

## "Nous ne sommes pas en mesure de traiter votre demande"

If you have been trying to book through the ANEF site
([administration-etrangers-en-france.interieur.gouv.fr](https://administration-etrangers-en-france.interieur.gouv.fr))
and keep seeing the message **"Nous ne sommes pas en mesure de traiter votre
demande"**, this does **not** mean there is a problem with your file or your
application.

It simply means: **no appointment slots exist right now.**

The ANEF site checks rdv-prefecture.interieur.gouv.fr in the background, and when
no slots are available it shows this unhelpful error instead of saying clearly
"no slots". Your dossier is fine. You just need to be ready the moment a slot
opens.

---

## When to start monitoring

Appointment slots for titre de séjour renewal typically only become bookable
within **2 months of your titre's expiry date**. The prefecture system usually
will not offer slots before that window.

**Recommendation:** activate this monitor about 2–3 months before your titre
expires so that it is running when the first slots appear.

---

## Who this is for

Anyone waiting for a titre de séjour appointment in France who finds it
impossible to manually refresh the prefecture's booking site all day long.

The tool runs entirely inside your own GitHub account — no third-party services,
no subscription fees, no data leaves your fork.

---

## Step-by-step setup

### 1 — Fork this repository

1. Click the **Fork** button at the top-right of this GitHub page.
2. GitHub creates a private copy of the repo under your account.

### 2 — Find your demarche ID

1. Go to [rdv-prefecture.interieur.gouv.fr](https://www.rdv-prefecture.interieur.gouv.fr).
2. Select your département.
3. Click the procedure you need (e.g. "Renouvellement titre de séjour").
4. Look at the URL in your browser address bar. It will look like:
   `https://www.rdv-prefecture.interieur.gouv.fr/rdvpref/reservation/demarche/**4082**/`
5. The number (here **4082**) is your **demarche ID**.

#### Common demarche IDs (illustrative — always verify on the official site)

These IDs vary by département and change over time. The examples below are from
community reports and may not match your department:

| Procedure | Département | Demarche ID (example) |
|---|---|---|
| Renouvellement titre de séjour — jeunes majeurs | Seine-et-Marne (77) | 3987 |
| Retrait titre de séjour — première demande | Paris (75) | 5082 |
| Retrait titre de séjour — renouvellement | Paris (75) | 4293 |
| Accompagnement démarches en ligne | Paris (75) | 3987 |

**Always verify by visiting the official site for your département and procedure.**

### 3 — Edit `config.json`

In your fork, click on `config.json` and then the pencil icon to edit it.

```json
{
  "departement": "75",
  "demarche_id": "4082",
  "subscribers": [
    "yourname@example.com"
  ]
}
```

Change:
- `"departement"` → your département code (e.g. `"75"` for Paris, `"93"` for
  Seine-Saint-Denis, `"69"` for Rhône/Lyon).
- `"demarche_id"` → the number you found in step 2.
- `"subscribers"` → your email address. You can add several:
  `["email1@example.com", "email2@example.com"]`

Click **Commit changes** when done.

### 4 — Create a Gmail App Password

The monitor sends emails using Gmail. Gmail requires an **App Password** (not your
regular Gmail password) for automated scripts.

1. Make sure 2-Step Verification is enabled on your Google account:
   [myaccount.google.com/security](https://myaccount.google.com/security)
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. Select **Mail** and **Other (Custom name)**, type "RDV Monitor", click **Generate**.
4. Copy the 16-character password that appears. **You will only see it once.**

### 5 — Add GitHub Secrets

GitHub Secrets keep your credentials safe — they are never stored in your code.

1. In your fork, go to **Settings → Secrets and variables → Actions**.
2. Click **New repository secret** and add the following two secrets:

   | Name | Value |
   |---|---|
   | `SMTP_USER` | Your Gmail address (e.g. `yourname@gmail.com`) |
   | `SMTP_PASSWORD` | The 16-character App Password from step 4 |

### 6 — Enable GitHub Actions

1. In your fork, click the **Actions** tab.
2. If you see a message saying workflows are disabled, click **I understand my
   workflows, go ahead and enable them**.
3. Click on **Check Appointment Availability** in the left sidebar.
4. Click **Run workflow → Run workflow** (green button) to do a first manual test.
5. After a few seconds, refresh the page and click the workflow run to see the logs.

If the checker ran without errors, it is working. From now on it will
automatically run every 5 minutes as long as your fork's Actions are enabled.

---

## How do I know it is working?

- The **Actions** tab in your fork shows a list of workflow runs. Each should show
  a green tick.
- If no slots are available, the logs will say `"No slots available. Will check
  again at the next scheduled run."` — this is normal.
- When slots open up, you will receive an email.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| All workflow runs fail (red ✗) | Syntax error in `config.json` | Re-check the JSON, ensure commas are correct |
| "SMTP authentication failed" in logs | Wrong App Password | Re-generate the App Password in Google account |
| "Demarche not found (404)" in logs | Wrong demarche ID | Re-check the URL on rdv-prefecture.interieur.gouv.fr |
| Workflow runs but no email on slots | SMTP secrets not set | Check Settings → Secrets |
| Actions tab not visible | GitHub Actions disabled on fork | Enable via Settings → Actions → Allow all actions |

---

## GitHub Actions cron note

GitHub's free tier runs Actions within a few minutes of the scheduled time, but
very occasionally jobs can be delayed by up to 15 minutes during high-traffic
periods. For a resource that refreshes rarely, this is acceptable.

GitHub also automatically disables scheduled workflows after **60 days of
repository inactivity**. If your fork has no commits, push a small change (e.g.
edit a space in README.md) every couple of months to keep it active, or check
the Actions tab and re-enable manually.

---

## Privacy and security

- Your email address lives in `config.json` (which is in your fork's source code).
  If your fork is **public**, your email address is visible. Consider making the
  fork **private** (free for personal use on GitHub).
- Your Gmail credentials live only in GitHub Secrets, which are encrypted and
  never appear in logs.
- This tool makes read-only HTTP requests to rdv-prefecture.interieur.gouv.fr.
  It does not submit any personal data to the site.

---

## Disclaimer

This is an independent open-source project and is not affiliated with, endorsed
by, or connected to the French government, the Ministère de l'Intérieur, or any
prefecture. Use it at your own risk. The tool is provided as-is with no
warranties. Always verify appointment availability on the official website before
relying on alerts.
