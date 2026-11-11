"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PORTAL_NAVIGATION } from "@/constants/portal";

function isActive(pathname: string, href: string): boolean {
  return href === "/portal" ? pathname === href : pathname.startsWith(href);
}

export function PortalNavigation() {
  const pathname = usePathname();
  return (
    <nav aria-label="Portal" className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
      {PORTAL_NAVIGATION.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition ${
              active ? "bg-enamel/12 text-white" : "text-enamel/65 hover:bg-enamel/6 hover:text-white"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
