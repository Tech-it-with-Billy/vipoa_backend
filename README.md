# VIPOA Backend

This repository contains the Django backend for the VIPOA application.  It is
configured for deployment on Railway using a PostgreSQL database provisioned by
the platform.  The configuration is intentionally minimal and reads
sensitive data from environment variables, which is the deployment model used by
Railway.

---

## Deployment Preparation ✅

1. **Environment Variables** – Railway sets a `DATABASE_URL` when you attach a
   PostgreSQL plugin.  At a minimum you should also configure:

   - `SECRET_KEY` – a secure random string for Django.
   - `DEBUG` – `False` in production.
   - `ALLOWED_HOSTS` – comma-separated list of allowed domains.

   See `.env.example` for a template.

2. **Dependencies** – all Python requirements are listed in
   `requirements.txt`.  Make sure to install with:

   ```bash
   pip install -r requirements.txt
   ```

3. **Python Version** – the runtime is pinned in `runtime.txt` (currently
   `python-3.13.5`).  Railway will install that version when building the
   project.

4. **Static Files** – the project uses `whitenoise` to serve static assets.
   The `STATIC_ROOT` is configured in `settings.py`.  During the build step,
   run `python manage.py collectstatic --noinput` to populate the `staticfiles`
   directory.

5. **Process File** – a `Procfile` is included to tell Railway how to start the
   web server:

   ```text
   web: gunicorn vipoa_backend.wsgi --log-file -
   ```

6. **.gitignore** – root-level `.gitignore` now excludes local artifacts, the
   `.env` file, database files, and static/media folders.

---

## Local Development 🛠

- Copy `.env.example` to `.env` and fill in values.
- Activate your virtual environment and run `python manage.py migrate`.
- Use `python manage.py runserver` to start a development server.
- Run tests with `python manage.py test` or `python run_tests.py`.

---

## Notes for Railway

When you create a new Railway project, attach the PostgreSQL plugin and set the
environment variables mentioned above.  You can configure build and start
commands in the Railway dashboard or supply a `railway.json` file if you prefer
using infrastructure-as-code; a simple build command is:

```bash
pip install -r requirements.txt
python manage.py collectstatic --noinput
```

The app will be started by the `Procfile` entry, so no custom start command is
needed unless you want extra options.

---

Feel free to expand this README with service-specific notes as the project
evolves.
