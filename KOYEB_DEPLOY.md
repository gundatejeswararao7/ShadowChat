# Deploying ShadowChat on Koyeb (Always-On & Free)

Koyeb is the recommended cloud platform for ShadowChat because:
- **No Sleep / No Cold Starts**: Runs 24/7 on the free Eco/Nano instance.
- **Full WebSocket Support**: Native `wss://` protocol support for real-time encrypted messaging.
- **Automatic HTTPS/TLS**: Free SSL certificates out of the box.

---

## 1. Commit and Push to GitHub

Ensure all your latest files are committed and pushed to your GitHub repository:
```bash
git add .
git commit -m "Configure ShadowChat for Koyeb and Supabase"
git push origin main
```

---

## 2. Deploy on Koyeb

1. Go to **[koyeb.com](https://www.koyeb.com/)** and log in (or sign up with GitHub).
2. Click **Create App** (or **Create Service**).
3. Select **GitHub** as the deployment method.
4. Select your **ShadowChat** repository.
5. In the service configuration:
   - **Service Name**: `shadowchat` (or any name you prefer)
   - **Instance Type**: Select **Eco (Nano)** (Free tier, 512MB RAM)
   - **Region**: Choose the region closest to you (e.g., Frankfurt `fra` or Washington `was`)
   - **Builder**: **Buildpack** (Koyeb will automatically detect Python and your `Procfile`)
   - **Port**: Koyeb will automatically detect port `8000` with protocol `HTTP`
6. Under **Environment Variables**, add the following:

| Key | Value | Description |
| :--- | :--- | :--- |
| `SUPABASE_URL` | `https://pqewaarnadwcwtrlpccz.supabase.co` | Your Supabase Project URL |
| `SUPABASE_KEY` | *(your service_role secret key)* | Supabase service_role key |
| `BREVO_API_KEY` | `xkeysib-...` | Your free Brevo API key (for OTP emails over Port 443) |
| `EMAIL_FROM` | `gtejeswararao4@gmail.com` | Verified sender email in Brevo |
| `OTP_EXPIRY_MINUTES` | `5` | OTP timeout in minutes |
| `OTP_MAX_ATTEMPTS` | `5` | Max OTP attempts |
| `OTP_RESEND_COOLDOWN_SECONDS` | `30` | Resend cooldown in seconds |

7. Click **Deploy**.

---

## 3. Connect Clients to your Koyeb Server

Once deployed, Koyeb will display your live public domain, for example:
`https://shadowchat-xxxx.koyeb.app`

Now, you and anyone running the client simply update their local `.env`:
```ini
SERVER_HTTP_URL=https://shadowchat-xxxx.koyeb.app
SERVER_WS_URL=wss://shadowchat-xxxx.koyeb.app/ws
```

Run the client:
```bash
python client/cli.py
```
*(Or double-click `ShadowChat.bat`)*

You now have a 24/7 always-on, real-time encrypted chat system!
