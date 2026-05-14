import { type ReactNode } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import {
  Bot,
  Flame,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Users,
  Wallet,
} from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { cn } from '@/lib/utils';
import { Button } from './ui/button';

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
}

const NAV: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/squads', label: 'Squads', icon: Users },
  { to: '/agents', label: 'Agentes', icon: Bot },
  { to: '/cost', label: 'Custos', icon: Wallet },
  { to: '/credentials', label: 'Credenciais', icon: KeyRound },
];

export default function Layout({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const location = useLocation();

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col border-r border-border bg-card md:flex">
        <Link to="/dashboard" className="flex h-14 items-center gap-2 border-b border-border px-4">
          <Flame className="size-5 text-brand-500" />
          <span className="font-semibold tracking-tight">obris</span>
          <span className="text-xs font-mono uppercase text-muted-foreground">client</span>
        </Link>
        <nav className="flex-1 space-y-0.5 p-3">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = location.pathname.startsWith(item.to);
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  active
                    ? 'bg-brand-500/10 text-brand-500'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                )}
              >
                <Icon className="size-4" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
        <div className="border-t border-border p-3">
          <div className="mb-2 px-2 text-xs text-muted-foreground">
            <div className="truncate font-medium text-foreground">{me?.user.full_name}</div>
            <div className="truncate font-mono">{me?.user.email}</div>
          </div>
          <Button variant="ghost" size="sm" className="w-full justify-start" onClick={logout}>
            <LogOut className="size-4" /> Sair
          </Button>
        </div>
      </aside>

      <main className="md:pl-60 min-h-screen">
        <div className="container py-8">{children}</div>
      </main>
    </div>
  );
}
