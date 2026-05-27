import { withBasePath } from "@/lib/base-path";

type CalendarOAuthStartResponse = {
  authUrl: string;
};

type CalendarOAuthStartPayload = {
  userEmail: string;
  returnTo?: string;
};

export async function startGoogleCalendarOAuth({
  userEmail,
  returnTo = "/meetings",
}: {
  userEmail: string;
  returnTo?: string;
}): Promise<void> {
  const payload: CalendarOAuthStartPayload = { userEmail, returnTo };

  const resp = await fetch(withBasePath("/api/calendar/oauth/start"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || "Failed to start Google Calendar OAuth");
  }

  const data = (await resp.json()) as CalendarOAuthStartResponse;
  if (!data?.authUrl) {
    throw new Error("Google Calendar OAuth URL was not returned");
  }

  window.location.assign(data.authUrl);
}
