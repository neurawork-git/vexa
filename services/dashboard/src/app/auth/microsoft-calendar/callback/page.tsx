"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/ui/logo";
import { withBasePath } from "@/lib/base-path";

type CallbackState = "loading" | "success" | "error";

function MicrosoftCalendarCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [state, setState] = useState<CallbackState>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function run() {
      const code = searchParams.get("code");
      const stateParam = searchParams.get("state");
      const oauthError = searchParams.get("error");

      if (oauthError) {
        if (!mounted) return;
        setState("error");
        setError(
          oauthError === "access_denied"
            ? "Microsoft Calendar authorization was cancelled or denied."
            : `Microsoft Calendar authorization failed: ${oauthError}`
        );
        return;
      }

      if (!code || !stateParam) {
        if (!mounted) return;
        setState("error");
        setError("Missing OAuth callback parameters");
        return;
      }

      const completeResp = await fetch(withBasePath("/api/calendar/microsoft/oauth/complete"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, state: stateParam }),
      });

      const completeData = await completeResp.json();
      if (!completeResp.ok) {
        if (!mounted) return;
        setState("error");
        setError(completeData?.error || "Failed to complete Microsoft Calendar OAuth");
        return;
      }

      if (!mounted) return;
      setState("success");
      setTimeout(() => {
        router.replace(completeData?.returnTo || "/meetings");
      }, 900);
    }

    run().catch((err) => {
      if (!mounted) return;
      setState("error");
      setError((err as Error).message || "Unexpected error during callback");
    });

    return () => {
      mounted = false;
    };
  }, [router, searchParams]);

  return (
    <Card className="border-0 shadow-xl">
      <CardHeader className="text-center">
        <div className="flex justify-center mb-4">
          <Logo className="h-8" />
        </div>
        <CardTitle>
          {state === "loading" && "Connecting Microsoft Calendar…"}
          {state === "success" && "Microsoft Calendar Connected"}
          {state === "error" && "Connection Failed"}
        </CardTitle>
        {state !== "loading" && (
          <CardDescription>
            {state === "success"
              ? "Redirecting you back…"
              : "Something went wrong during the Microsoft Calendar connection."}
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-4">
        {state === "loading" && <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />}
        {state === "success" && <CheckCircle2 className="h-8 w-8 text-green-500" />}
        {state === "error" && (
          <>
            <XCircle className="h-8 w-8 text-destructive" />
            {error && <p className="text-sm text-destructive text-center">{error}</p>}
            <Button variant="outline" onClick={() => router.replace("/profile")}>
              Back to Profile
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function MicrosoftCalendarCallbackPage() {
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <Suspense
          fallback={
            <Card className="border-0 shadow-xl">
              <CardContent className="flex justify-center p-8">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </CardContent>
            </Card>
          }
        >
          <MicrosoftCalendarCallbackContent />
        </Suspense>
      </div>
    </div>
  );
}
