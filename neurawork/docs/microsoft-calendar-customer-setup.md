# Microsoft 365 Calendar — Customer Setup Guide

This guide walks your Azure tenant administrator through the one-time setup required to enable Microsoft 365 Calendar integration with Vexa.

## What you need

- Azure AD Global Administrator or Application Administrator role
- ~15 minutes
- Your Azure Tenant ID (found in Azure Portal → Azure Active Directory → Overview)

---

## Step 1: Azure App Registration

1. Open [https://portal.azure.com](https://portal.azure.com) and sign in as admin.
2. Navigate to **Azure Active Directory → App registrations → New registration**.
3. Fill in:
   - **Name**: `Vexa Calendar Integration` (or any name you prefer)
   - **Supported account types**: **Accounts in any organizational directory (Any Azure AD tenant – Multitenant)**
   - **Redirect URI**: Select **Web** and enter:
     ```
     https://vexa-dashboard.neurawork.app/auth/microsoft-calendar/callback
     ```
4. Click **Register**.
5. Note the **Application (client) ID** — you will send this to the Vexa team.
6. Note your **Directory (tenant) ID** — keep this for Step 3.

---

## Step 2: API Permissions

1. In your new app registration, go to **API permissions → Add a permission**.
2. Select **Microsoft Graph → Delegated permissions**.
3. Add the following permissions:
   - `Calendars.ReadWrite`
   - `User.Read`
   - `offline_access`
4. Click **Add permissions**.

The permission list should now show all three under **Microsoft Graph**.

---

## Step 3: Grant Tenant Admin Consent

Delegated `Calendars.ReadWrite` requires explicit admin consent before any user in your tenant can authorize Vexa.

**Option A — Button in Portal (recommended):**
1. Still in **API permissions**, click **Grant admin consent for [Your Tenant]**.
2. Confirm the dialog.
3. All three permissions should show a green checkmark under **Status**.

**Option B — Direct URL:**
Navigate to (replace `{tenant-id}` with your Directory ID from Step 1):
```
https://login.microsoftonline.com/{tenant-id}/adminconsent?client_id={your-client-id}
```
Sign in as admin and accept.

---

## Step 4: Create a Client Secret

1. In your app registration, go to **Certificates & secrets → New client secret**.
2. Set **Expires** to **24 months** (maximum available).
3. Click **Add**.
4. **Copy the secret value immediately** — it is shown only once.

---

## Step 5: Send Credentials to Vexa Team

Send the following to your Vexa contact:

| Item | Where to find it |
|------|-----------------|
| Application (client) ID | App registration → Overview |
| Client Secret (value) | Step 4 above |
| Tenant ID (optional) | Azure AD → Overview |

The Vexa team will configure these as `MICROSOFT_CLIENT_ID` and `MICROSOFT_CLIENT_SECRET` in the deployment. The Microsoft Calendar Connect button will appear in the Vexa Dashboard profile page once configured.

---

## Step 6: Per-User Connect Flow

After the Vexa team confirms the credentials are live:

1. Each user navigates to **Vexa Dashboard → Profile**.
2. Under **Microsoft 365 Calendar**, click **Connect Microsoft 365 Calendar**.
3. Sign in with your Microsoft work account and approve the permission request.
4. Vexa will start syncing upcoming calendar events and automatically join meetings.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `AADSTS65001: The user or administrator has not consented to use the application` | Admin consent not granted | Complete Step 3 |
| `AADSTS50011: The reply URL specified in the request does not match` | Redirect URI mismatch | Verify the redirect URI in Step 1 matches exactly |
| Microsoft Calendar card is not visible in Vexa Dashboard | `MICROSOFT_CLIENT_ID` not configured | Contact Vexa team to confirm deployment |
| Events not syncing after connect | `Calendars.ReadWrite` permission missing or not consented | Re-check Step 2 and Step 3 |
| `admin_consent_required` warning in dashboard | Admin consent was revoked or never granted | Repeat Step 3 |

---

## Security Notes

**Scopes requested:**
- `Calendars.ReadWrite` — reads upcoming events to detect meeting URLs; write access is required by Microsoft to receive refresh tokens for delegated calendar access (Vexa does not create or modify calendar events)
- `User.Read` — reads basic profile (name, email) for display purposes
- `offline_access` — enables long-lived access via refresh token so users do not need to re-authorize on every sync cycle

**Token rotation:** Microsoft rotates refresh tokens on every use. Vexa persists each new token immediately after refresh to avoid loss of access.

**Disconnect:** Users can disconnect at any time via **Vexa Dashboard → Profile → Microsoft 365 Calendar → Disconnect**. This removes all stored tokens from Vexa's database. To fully revoke access, also remove the app consent in **Azure AD → Enterprise Applications → [your app] → Permissions → Revoke admin consent**.
