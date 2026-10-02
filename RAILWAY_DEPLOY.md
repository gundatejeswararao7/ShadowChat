# Deploying ShadowChat on Railway

## 1. Prepare the project

- Make sure your project is committed and pushed to GitHub.
- Ensure your `.env` values are available in Railway as environment variables.

```bash
git add .
git commit -m "Prepare ShadowChat for Railway"
git push origin main
```

## 2. Create the Railway project

1. Open https://railway.app
2. Sign in with GitHub.
3. Click New Project.
4. Choose Deploy from GitHub Repo.
5. Select this repository.

## 3. Add environment variables

In the Railway project dashboard, go to Variables and add:

```env
HOST=0.0.0.0
PORT=8000
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your_service_role_secret
BREVO_API_KEY=your_brevo_api_key
EMAIL_FROM=your_verified_sender_email
OTP_EXPIRY_MINUTES=5
OTP_MAX_ATTEMPTS=5
OTP_RESEND_COOLDOWN_SECONDS=30
EMAIL_VERIFICATION_TOKEN_TTL_MINUTES=10
INVITATION_EXPIRY_MINUTES=5
RECONNECT_GRACE_SECONDS=30
```

If you prefer Gmail SMTP instead of Brevo, use:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_APP_PASSWORD=your_16_digit_app_password
```

## 4. Deploy the app

Railway will detect the Python project from `requirements.txt` and the config in `railway.json`.

The app will start with:

```bash
uvicorn server.main:app --host 0.0.0.0 --port $PORT
```

## 5. Verify the deployment

After deployment, Railway will provide a public URL such as:

```text
https://your-app.up.railway.app
```

Check:

```text
https://your-app.up.railway.app/health
```

You should get:

```json
{"status": "ok"}
```

## 6. Update client settings

If the desktop CLI or browser clients need to connect to the deployed server, set:

```env
SERVER_HTTP_URL=https://your-app.up.railway.app
SERVER_WS_URL=wss://your-app.up.railway.app/ws
```

## 7. Notes

- Railway automatically injects `PORT`; do not hardcode a different port.
- Keep `HOST=0.0.0.0` for deployed services.
- If email delivery fails, verify your Brevo or Gmail SMTP settings.
- If Supabase fails, confirm the `SUPABASE_URL` and `SUPABASE_KEY` values are valid.
