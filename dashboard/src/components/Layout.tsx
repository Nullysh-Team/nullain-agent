import { NavLink, Outlet, useLocation } from "react-router-dom";

const links = [
  { to: "/", label: "Comunicação", end: true },
  { to: "/brain", label: "Cérebro", end: false },
  { to: "/tokens", label: "Tokens", end: false },
  { to: "/integrations", label: "Integrações", end: false },
  { to: "/memory", label: "Memória", end: false },
  { to: "/logs", label: "Logs", end: false },
];

export function Layout() {
  const location = useLocation();
  const isChat = location.pathname === "/";

  return (
    <div className="relative z-10 flex min-h-screen">
      <aside className="flex w-52 shrink-0 flex-col border-r border-[#333] bg-black/80 px-4 py-6">
        <div className="mb-8 border border-white/20 px-3 py-2 text-center shadow-[0_0_20px_rgba(255,255,255,0.08)]">
          <p className="text-xs tracking-[0.35em] text-[#999]">NULLAIN</p>
          <p className="mt-1 font-mono text-sm">JARVIS</p>
        </div>

        <nav className="flex flex-col gap-1">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                [
                  "border px-3 py-2 text-sm transition",
                  isActive
                    ? "border-white bg-white text-black shadow-[0_0_16px_rgba(255,255,255,0.15)]"
                    : "border-transparent text-[#999] hover:border-[#666] hover:text-white",
                ].join(" ")
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main
        className={[
          "flex-1 overflow-auto",
          isChat ? "px-6 py-4" : "px-8 py-8",
        ].join(" ")}
      >
        <Outlet />
      </main>
    </div>
  );
}