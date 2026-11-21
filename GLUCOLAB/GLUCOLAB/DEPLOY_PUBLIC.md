# Put GLUCOLAB online — public beta instructions

**Prepared for Render; not yet published.** A ZIP file by itself is not a live website. Do not upload real or identifiable patient medical data until the service has had a professional security/privacy review and appropriate public policies. The public beta can be tried using the bundled synthetic test CSVs.

## 1. Put these code files in a GitHub repository

- Create a free GitHub account if needed: https://github.com/
- Create a **new private repository** (e.g. `glucolab-public-beta`).
- On the GitHub repository page choose **Add file → Upload files**, and upload the **CONTENTS OF THIS GLUCOLAB FOLDER** so that `app.py`, `index.html`, `requirements.txt`, and `render.yaml` appear in the repository root.
- Do not upload any real LibreView, CareLink, or other health data files. The sample CSVs here are synthetic.
- Save the changes with **Commit changes**.

## 2. Deploy with Render

- Open https://dashboard.render.com/ and create a Render account.
- Choose **New → Web Service**, connect GitHub and select the repository.
- Use Python runtime and the following settings (or import the included `render.yaml` as a Blueprint):

  **Build command:** `pip install -r requirements.txt`

  **Start command:** `uvicorn app:app --host 0.0.0.0 --port $PORT --no-access-log`

  **Environment variable:** `GLUCOLAB_PUBLIC=1`

  **Health check path:** `/api/health`

- Select the instance size you want; Render's Free tier is useful for a demo but may suspend when idle and has limited memory and request performance. Larger CSV analyses may need a paid instance.
- Click **Deploy Web Service**, wait for a successful deploy, then use the URL assigned in your Render dashboard (typically a `*.onrender.com` address). **The final URL does not exist until Render successfully deploys your app.**
- Confirm both `/` and `/api/health` work, then try **only the bundled synthetic sample data**.

## 3. Custom website name (optional)

In Render, use **Settings → Custom Domains** if you own a domain, then follow the DNS instructions at your domain registrar. Domain names are not guaranteed to be available and are normally purchased separately. Your default Render URL already works on the public internet.

## Privacy and resource limits

- The public version sends uploaded CSV data over HTTPS to your hosted Python service for parsing. They do **not** stay only on the visitor's computer. The current code does not intentionally persist uploads or store them in a database, but temporary disk/RAM and host/service logs should be assessed during a privacy and security review.
- A request-size guard (64 MB total) and per-file check (30 MB) apply in public mode. These checks are basic protections only, not an exhaustive defense against misuse or denial of service. Real user traffic requires an independent security audit, adequate monitoring, operational policies, appropriate consent/privacy documentation and possibly stronger infrastructure.
- The local Anaconda version still uses `python app.py` and remains limited to 127.0.0.1 by default.
- The page is marked as an exploratory public beta and warns not to upload identifiable patient records.
- No authentication or user accounts are implemented. A public website link is accessible to everyone, but that does not imply it is ready to handle sensitive patient files safely.
- Glucose and basal comparison outputs are exploratory. Do not program simulated U/h figures into a pump.

## Official references

- Render FastAPI: https://render.com/docs/deploy-fastapi
- Render web services: https://render.com/docs/web-services
- Render Free: https://render.com/docs/free
- OWASP File Upload Security: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
