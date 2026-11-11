import { NextResponse, type NextRequest } from "next/server";
import { LOGIN_PATH, PORTAL_PATH } from "@/constants/app";
import { refreshSession } from "@/lib/supabase/proxy-session";

export async function proxy(request: NextRequest): Promise<NextResponse> {
  const { response, user } = await refreshSession(request);
  const { pathname, search } = request.nextUrl;

  if (pathname.startsWith(PORTAL_PATH) && !user) {
    const loginUrl = new URL(LOGIN_PATH, request.url);
    loginUrl.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(loginUrl);
  }

  if (pathname === LOGIN_PATH && user) {
    return NextResponse.redirect(new URL(PORTAL_PATH, request.url));
  }

  return response;
}

export const config = {
  matcher: ["/portal/:path*", "/login", "/api/calls/:path*"],
};
