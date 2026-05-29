import { withBasePath } from "@/lib/base-path";

type MicrosoftOAuthStartResponse = {
  authUrl: string;
};

type MicrosoftOAuthStartPayload = {
  userEmail: string;
  returnTo?: string;
};

export async function startMicrosoftCalendarOAuth({
  userEmail,
  returnTo = "/meetings",
}: {
  userEmail: string;
  returnTo?: string;
}): Promise<void> {
  const payload: MicrosoftOAuthStartPayload = { userEmail, returnTo };

  const resp = await fetch(withBasePath("/api/calendar/microsoft/oauth/init"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || "Failed to start Microsoft Calendar OAuth");
  }

  const data = (await resp.json()) as MicrosoftOAuthStartResponse;
  if (!data?.authUrl) {
    throw new Error("Microsoft Calendar OAuth URL was not returned");
  }

  window.location.assign(data.authUrl);
}
