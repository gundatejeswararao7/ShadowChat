-- ShadowChat Supabase Schema
-- Run this in your Supabase Project: Dashboard -> SQL Editor -> New query -> Run

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Users Table
CREATE TABLE IF NOT EXISTS public.users (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. OTP Records Table
CREATE TABLE IF NOT EXISTS public.otp_records (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    email TEXT NOT NULL,
    otp_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts INTEGER DEFAULT 0 NOT NULL,
    used BOOLEAN DEFAULT FALSE NOT NULL
);

-- 3. Chat Invitations Table
CREATE TABLE IF NOT EXISTS public.chat_invitations (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    sender_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    receiver_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'PENDING' NOT NULL, -- PENDING, ACCEPTED, REJECTED, EXPIRED, CANCELLED
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

-- 4. Rooms Table
CREATE TABLE IF NOT EXISTS public.rooms (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_a_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    user_b_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'ACTIVE' NOT NULL, -- ACTIVE, TERMINATING, DELETED
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Indexes for optimal lookup performance
CREATE INDEX IF NOT EXISTS idx_users_username ON public.users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON public.users(email);
CREATE INDEX IF NOT EXISTS idx_otp_email ON public.otp_records(email);
CREATE INDEX IF NOT EXISTS idx_invitations_receiver ON public.chat_invitations(receiver_id);
CREATE INDEX IF NOT EXISTS idx_invitations_status ON public.chat_invitations(status);
CREATE INDEX IF NOT EXISTS idx_rooms_status ON public.rooms(status);

-- Optional Row Level Security (RLS)
-- If accessing via backend using Supabase 'service_role' key, RLS is automatically bypassed.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.otp_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rooms ENABLE ROW LEVEL SECURITY;

-- Allow service_role full access policy (for safety if anon key is ever used)
CREATE POLICY "Service role full access on users" ON public.users FOR ALL USING (true);
CREATE POLICY "Service role full access on otp_records" ON public.otp_records FOR ALL USING (true);
CREATE POLICY "Service role full access on chat_invitations" ON public.chat_invitations FOR ALL USING (true);
CREATE POLICY "Service role full access on rooms" ON public.rooms FOR ALL USING (true);
