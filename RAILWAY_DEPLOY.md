# Deploying ShadowChat on Railway ($5 Monthly Free Credit)

Railway is one of the best platforms for ShadowChat because:
- **No Port Blocking**: Railway allows outbound connections on **port 587**, so your **Gmail SMTP + App Password works directly**!
- **Persistent WebSockets**: Full native `wss://` WebSocket support for live encrypted chat.
- **Never Sleeps**: Your service stays awake 24/7 as long as you have your monthly credit.
- **Automatic HTTPS/TLS**: You get a free public `https://...up.railway.app` domain.

---

## 1. Push Latest Code to GitHub

Ensure all your latest files are pushed:
```bash
git add .
git commit -m "Configure ShadowChat for Railway deployment"
git push origin main
```

---

## 2. Deploy on Railway

1. Go to **[railway.app](https://railway.app)** and log in with **GitHub**.
2. Click **+ New Project** (top right) ➔ Select **Deploy from GitHub repo**.
3. Select your **`ShadowChat`** repository.
4. Click **Deploy Now**.

---

## 3. Generate a Public Domain

By default, Railway deploys the service privately. To make it accessible via the internet:
1. In your project dashboard, click on your **`ShadowChat` service box**.
2. Go to the **Settings** tab.
3. Scroll down to the **Networking** section.
4. Under **Public Networking**, click **Generate Domain**.
5. Railway will give you an official HTTPS URL, for example:
   `https://shadowchat-production-xxxx.up.railway.app`

---

## 4. Add Environment Variables

In your Railway service dashboard, click on the **Variables** tab and click **+ New Variable** (or **RAW Editor**):

```ini
HOST=0.0.0.0

# --- Supabase Database ---
SUPABASE_URL=https://pqewaarnadwcwtrlpccz.supabase.co
SUPABASE_KEY=your-supabase-service-role-secret-key

# --- Gmail SMTP (Works directly on Railway!) ---
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=gtejeswararao4@gmail.com
SMTP_APP_PASSWORD=rxtryvwreqnnooxf

# --- OTP / Security Policy ---
OTP_EXPIRY_MINUTES=5
OTP_MAX_ATTEMPTS=5
OTP_RESEND_COOLDOWN_SECONDS=30
EMAIL_VERIFICATION_TOKEN_TTL_MINUTES=10

# --- Invitations / Rooms ---
INVITATION_EXPIRY_MINUTES=5
RECONNECT_GRACE_SECONDS=30
```

> **Note**: Railway automatically injects the `PORT` variable, so you do **not** need to set `PORT` manually.

---

## 5. Open Your Live Web App

Once the deployment finishes (takes ~1 minute):
1. Click your generated Railway domain:
   `https://shadowchat-production-xxxx.up.railway.app`
2. The **ShadowChat Web Terminal UI** will open in any browser on any PC, laptop, or phone!
3. Users can register, receive their Gmail OTP code, log in, and chat in dedicated encrypted pop-up windows.
