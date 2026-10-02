# Supabase Setup Guide for ShadowChat

Follow these steps to set up Supabase for ShadowChat:

## 1. Create a Supabase Project
1. Log in to [Supabase](https://supabase.com/).
2. Click **New Project**.
3. Choose an organization, enter a name (e.g. `ShadowChat`), set a database password, and select your nearest region.
4. Click **Create new project**.

## 2. Run the SQL Schema
1. In your project dashboard, navigate to the **SQL Editor** tab (left sidebar icon with `>_`).
2. Click **+ New Query**.
3. Copy the entire contents of [`supabase/schema.sql`](./schema.sql) and paste it into the editor.
4. Click **Run** (or `Ctrl+Enter` / `Cmd+Enter`).
5. You should see `"Success. No rows returned"`.
6. Open the **Table Editor** on the left to verify your 4 tables are created:
   - `users`
   - `otp_records`
   - `chat_invitations`
   - `rooms`

## 3. Get API Credentials
1. Go to **Project Settings** (gear icon) -> **API**.
2. Copy:
   - **Project URL** (e.g. `https://xyzprojectref.supabase.co`)
   - **service_role secret** key (Click *Reveal* on `service_role`).
     > **Note**: For backend servers like ShadowChat, use the `service_role` secret key so the server can safely query and manage accounts.

## 4. Add to your `.env`
Add these two variables to your `.env` file:
```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your_service_role_secret_key_here
```
