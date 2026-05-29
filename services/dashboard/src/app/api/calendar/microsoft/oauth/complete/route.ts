import { NextRequest, NextResponse } from "next/server";
import { createHmac } from "crypto";
import { getUserById, updateUser, createUserToken } from "@/lib/vexa-admin-api";

type MicrosoftOAuthStatePayload = {
  userId: string;
  email: string;
  returnTo: string;
  redirectUri?: string;
  iat: number;
  exp: number;
};

function getMicrosoftClientId(): string {
  return process.env.MICROSOFT_CLIENT_ID || "";
}

function getMicrosoftClientSecret(): string {
  return process.env.MICROSOFT_CLIENT_SECRET || "";
}

function getStateSecret(): string {
  return (
    process.env.MICROSOFT_OAUTH_STATE_SECRET ||
    process.env.NEXTAUTH_SECRET ||
    process.env.VEXA_ADMIN_API_KEY ||
    ""
  );
}

function resolveRedirectUri(req: NextRequest): string {
  if (process.env.MICROSOFT_CALENDAR_REDIRECT_URI) {
    return process.env.MICROSOFT_CALENDAR_REDIRECT_URI;
  }
  return `${req.nextUrl.origin}/auth/microsoft-calendar/callback`;
}

function parseAndVerifyState(state: string, secret: string): MicrosoftOAuthStatePayload {
  const [data, signature] = state.split(".");
  if (!data || !signature) {
    throw new Error("Invalid state format");
  }

  const expectedSig = createHmac("sha256", secret).update(data).digest("base64url");
  if (signature !== expectedSig) {
    throw new Error("Invalid state signature");
  }

  const raw = Buffer.from(
    data.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((data.length + 3) % 4),
    "base64"
  ).toString("utf8");

  const payload = JSON.parse(raw) as MicrosoftOAuthStatePayload;
  const now = Math.floor(Date.now() / 1000);
  if (!payload.exp || payload.exp < now) {
    throw new Error("OAuth state expired");
  }
  if (!payload.userId || !payload.email) {
    throw new Error("OAuth state is missing user data");
  }
  return payload;
}

async function exchangeCodeForMicrosoftTokens({
  code,
  redirectUri,
  clientId,
  clientSecret,
}: {
  code: string;
  redirectUri: string;
  clientId: string;
  clientSecret: string;
}): Promise<{
  access_token: string;
  refresh_token: string;
  expires_in: number;
  scope?: string;
}> {
  const SCOPES = ["Calendars.ReadWrite", "User.Read", "offline_access"];
  const params = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: redirectUri,
    client_id: clientId,
    client_secret: clientSecret,
    scope: SCOPES.join(" "),
  });

  const resp = await fetch("https://login.microsoftonline.com/common/oauth2/v2.0/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: params.toString(),
    cache: "no-store",
  });

  const text = await resp.text();
  if (!resp.ok) {
    throw new Error(`Microsoft token exchange failed (${resp.status}): ${text}`);
  }

  const payload = JSON.parse(text) as {
    access_token?: string;
    refresh_token?: string;
    expires_in?: number;
    scope?: string;
  };

  if (!payload.access_token || !payload.refresh_token) {
    throw new Error("Microsoft token response missing access_token or refresh_token");
  }

  return {
    access_token: payload.access_token,
    refresh_token: payload.refresh_token,
    expires_in: Number(payload.expires_in || 3600),
    scope: payload.scope,
  };
}

export async function POST(req: NextRequest) {
  try {
    const clientId = getMicrosoftClientId();
    const clientSecret = getMicrosoftClientSecret();
    if (!clientId || !clientSecret) {
      return NextResponse.json(
        { error: "Microsoft Calendar not configured" },
        { status: 503 }
      );
    }

    const { code, state } = (await req.json()) as {
      code?: string;
      state?: string;
    };

    if (!code || !state) {
      return NextResponse.json({ error: "code and state are required" }, { status: 400 });
    }

    const stateSecret = getStateSecret();
    if (!stateSecret) {
      return NextResponse.json(
        { error: "Microsoft Calendar OAuth state secret is not configured" },
        { status: 500 }
      );
    }

    const parsedState = parseAndVerifyState(state, stateSecret);
    const redirectUri =
      typeof parsedState.redirectUri === "string" && parsedState.redirectUri
        ? parsedState.redirectUri
        : resolveRedirectUri(req);

    const tokens = await exchangeCodeForMicrosoftTokens({
      code,
      redirectUri,
      clientId,
      clientSecret,
    });

    const userResult = await getUserById(parsedState.userId);
    if (!userResult.success || !userResult.data) {
      return NextResponse.json(
        { error: userResult.error?.message || "Failed to load user" },
        { status: 500 }
      );
    }

    const now = Math.floor(Date.now() / 1000);
    const existingData =
      userResult.data.data && typeof userResult.data.data === "object"
        ? (userResult.data.data as Record<string, unknown>)
        : {};

    // Mint a per-user Vexa API token so the calendar-service launches bots under
    // THIS user's identity (per-user concurrency limits + transcript ownership),
    // not a shared service account. Without it, auto-join cannot act for this user.
    const tokenResult = await createUserToken(parsedState.userId);
    if (!tokenResult.success || !tokenResult.data?.token) {
      return NextResponse.json(
        {
          error:
            tokenResult.error?.message ||
            "Failed to mint Vexa API token for calendar bot launches",
        },
        { status: 500 }
      );
    }

    // Preserve other microsoft_calendar sub-fields (e.g. preferences) on reconnect.
    const existingMs =
      existingData.microsoft_calendar && typeof existingData.microsoft_calendar === "object"
        ? (existingData.microsoft_calendar as Record<string, unknown>)
        : {};

    const updatedData: Record<string, unknown> = {
      ...existingData,
      microsoft_calendar: {
        ...existingMs,
        oauth: {
          access_token: tokens.access_token,
          refresh_token: tokens.refresh_token,
          expires_at: now + tokens.expires_in,
          scope: tokens.scope || "",
        },
        bot_token: tokenResult.data.token,
        // Clear any previous errors on successful reconnect
        last_error: null,
      },
    };

    const patchResult = await updateUser(parsedState.userId, { data: updatedData });
    if (!patchResult.success) {
      return NextResponse.json(
        { error: patchResult.error?.message || "Failed to persist Microsoft Calendar tokens" },
        { status: 500 }
      );
    }

    return NextResponse.json({
      success: true,
      returnTo: parsedState.returnTo || "/meetings",
    });
  } catch (error) {
    return NextResponse.json(
      { error: `Failed to complete Microsoft Calendar OAuth: ${(error as Error).message}` },
      { status: 500 }
    );
  }
}
