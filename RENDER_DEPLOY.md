# Deploying ShadowChat on Render

## 1. Prepare your repo

```bash
git add .
git commit -m "Prepare ShadowChat for Render"
git push origin main
```

## 2. Create a Render Web Service

1. Sign in to https://render.com
2. Click New + > Web Service
3. Connect your GitHub repository
4. Select the project root
5. Use the following settings:
   - Runtime: Python
   - Build command:
     ```bash
     pip install --upgrade pip && pip install -r requirements.txt
     ```
   - Start command:
     ```bash
     uvicorn server.main:app --host 0.0.0.0 --port $PORT
     ```

## 3. Add environment variables

Set these in Render > Environment:

```env
HOST=0.0.0.0
PORT=10000
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your_service_role_secret
EMAIL_PROVIDER=resend
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxx
EMAIL_FROM=your_verified_sender@example.com
OTP_EXPIRY_MINUTES=5
OTP_MAX_ATTEMPTS=5
OTP_RESEND_COOLDOWN_SECONDS=30
EMAIL_VERIFICATION_TOKEN_TTL_MINUTES=10
INVITATION_EXPIRY_MINUTES=5
RECONNECT_GRACE_SECONDS=30
```

Alternative provider options:

```env
EMAIL_PROVIDER=brevo
BREVO_API_KEY=xkeysib-xxxxxxxxxxxxxxxx
EMAIL_FROM=your_verified_sender@example.com
```

Or Gmail OAuth REST:

```env
EMAIL_PROVIDER=gmail_rest
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REFRESH_TOKEN=...
GMAIL_FROM_EMAIL=your-account@gmail.com
```

## 4. Deploy

Render automatically builds and starts the app. After deployment, open the generated public URL and test:

```text
https://your-service.onrender.com/health
```

Expected response:

```json
{"status": "ok"}
```

## 5. Important notes

- Render injects `PORT` automatically; do not hardcode a port other than `10000` in the platform.
- Always bind to `0.0.0.0` for public web services.
- Avoid SMTP on Render; prefer HTTPS-based APIs like Resend, Brevo, or Gmail REST.
- If sending email fails, validate the API key and sender address first.
