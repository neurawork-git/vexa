import { NextRequest, NextResponse } from "next/server";
import { findUserByEmail } from "@/lib/vexa-admin-api";

function getCalendarServiceUrl(): string {
  return process.env.CALENDAR_SERVICE_URL || "";
}

export async function GET(req: NextRequest) {
  const calendarUrl = getCalendarServiceUrl();
  if (!calendarUrl) {
    return NextResponse.json({ events: [], configured: false });
  }

  const userEmail = req.nextUrl.searchParams.get("userEmail");
  if (!userEmail) {
    return NextResponse.json({ error: "userEmail is required" }, { status: 400 });
  }

  const userResult = await findUserByEmail(userEmail);
  if (!userResult.success || !userResult.data) {
    return NextResponse.json(
      { error: userResult.error?.message || "Could not resolve user" },
      { status: 400 }
    );
  }

  try {
    const resp = await fetch(
      `${calendarUrl}/calendar/events?user_id=${userResult.data.id}`,
      { next: { revalidate: 0 }, signal: AbortSignal.timeout(5000) }
    );
    const data = await resp.json();
    return NextResponse.json(data, { status: resp.status });
  } catch (error) {
    return NextResponse.json(
      { error: `calendar-service unreachable: ${(error as Error).message}` },
      { status: 503 }
    );
  }
}
