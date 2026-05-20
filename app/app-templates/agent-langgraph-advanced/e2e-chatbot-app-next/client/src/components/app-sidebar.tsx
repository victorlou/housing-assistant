import { useNavigate } from 'react-router-dom';
import { Link } from 'react-router-dom';
import { Bookmark, LayoutDashboard, Map } from 'lucide-react';

import { SidebarHistory } from '@/components/sidebar-history';
import { SidebarUserNav } from '@/components/sidebar-user-nav';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { DbIcon } from '@/components/ui/db-icon';
import { NewChatIcon, SidebarCollapseIcon, SidebarExpandIcon } from '@/components/icons';
import { cn } from '@/lib/utils';
import type { ClientSession } from '@chat-template/auth';
import { Button } from './ui/button';
import { Action } from './elements/actions';

export function AppSidebar({
  user,
  preferredUsername,
}: {
  user: ClientSession['user'] | undefined;
  preferredUsername: string | null;
}) {
  const navigate = useNavigate();
  const { setOpenMobile, open, openMobile, isMobile, toggleSidebar } = useSidebar();

  const effectiveOpen = open || (isMobile && openMobile);

  return (
    <Sidebar
      collapsible="icon"
      className="group-data-[side=left]:border-r-0"
    >
      {/* ── Header: Kāinga brand + collapse toggle ───────────────────── */}
      <SidebarHeader
        className={cn(
          'h-[44px] flex-row items-center gap-2 px-2 py-0',
          effectiveOpen ? 'justify-between' : 'justify-center',
        )}
      >
        {effectiveOpen && (
          <Link
            to="/"
            onClick={() => setOpenMobile(false)}
            className="flex items-center gap-2 overflow-hidden px-1"
          >
            {/* Inline mark — no runtime path dependency */}
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 32 32"
              fill="none"
              className="size-5 rounded shrink-0"
              aria-hidden="true"
            >
              <rect width="32" height="32" rx="5.5" fill="#2C2C2C"/>
              <g transform="translate(20.1,14.2) scale(0.113)">
                <path d="M -100,120 L -100,10 L 0,-100 Q 8,-108 16,-100 L 80,-30 Q 110,0 110,40 Q 110,90 70,100 Q 30,110 20,75 Q 12,48 38,42 Q 58,38 62,56 Q 66,72 52,76 Q 42,78 40,66" fill="none" stroke="#F5ECD7" strokeWidth="10.6" strokeLinecap="round" strokeLinejoin="round"/>
                <line x1="-100" y1="120" x2="-100" y2="140" stroke="#F5ECD7" strokeWidth="10.6" strokeLinecap="round"/>
                <line x1="-116" y1="140" x2="20" y2="140" stroke="#F5ECD7" strokeWidth="10.6" strokeLinecap="round"/>
                <path d="M -72,140 L -72,90 Q -72,60 -48,60 Q -24,60 -24,90 L -24,140" fill="none" stroke="#2D6A4F" strokeWidth="7.5" strokeLinecap="round" strokeLinejoin="round"/>
                <circle cx="40" cy="66" r="5.5" fill="#F5ECD7"/>
                <path d="M 20,140 Q 40,128 52,140" fill="none" stroke="#2D6A4F" strokeWidth="4.0" strokeLinecap="round" opacity="0.7"/>
                <rect x="-80" y="-48" width="14" height="34" rx="3" fill="#2D6A4F" opacity="0.85" transform="rotate(-5,-73,-31)"/>
              </g>
            </svg>
            <span className="font-semibold text-foreground tracking-tight">
              Kāinga
            </span>
          </Link>
        )}

        <Action
          onClick={toggleSidebar}
          tooltip={effectiveOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          <DbIcon
            icon={effectiveOpen ? SidebarCollapseIcon : SidebarExpandIcon}
            size={16}
            color="muted"
          />
        </Action>
      </SidebarHeader>

      {/* ── Nav: New Chat + quick links ──────────────────────────────── */}
      <div className="px-2 pt-2 flex flex-col gap-1">
        <SidebarMenu>
          <SidebarMenuItem>
            <Tooltip>
              <TooltipTrigger asChild>
                <SidebarMenuButton
                  type="button"
                  className="h-8 p-1 md:p-2 cursor-pointer"
                  onClick={() => {
                    setOpenMobile(false);
                    navigate('/');
                  }}
                >
                  <DbIcon icon={NewChatIcon} size={16} color="default" />
                  <span className="group-data-[collapsible=icon]:hidden">
                    New chat
                  </span>
                </SidebarMenuButton>
              </TooltipTrigger>
              <TooltipContent side="right" style={{ display: open ? 'none' : 'block' }}>New chat</TooltipContent>
            </Tooltip>
          </SidebarMenuItem>
        </SidebarMenu>

        <SidebarMenu>
          <SidebarMenuItem>
            <Tooltip>
              <TooltipTrigger asChild>
                <SidebarMenuButton
                  type="button"
                  className="h-8 p-1 md:p-2 cursor-pointer"
                  onClick={() => {
                    setOpenMobile(false);
                    navigate('/map');
                  }}
                >
                  <Map className="size-4 shrink-0 text-primary" />
                  <span className="group-data-[collapsible=icon]:hidden">
                    Map Mode
                  </span>
                </SidebarMenuButton>
              </TooltipTrigger>
              <TooltipContent side="right" style={{ display: open ? 'none' : 'block' }}>Map Mode</TooltipContent>
            </Tooltip>
          </SidebarMenuItem>
        </SidebarMenu>

        <SidebarMenu>
          <SidebarMenuItem>
            <Tooltip>
              <TooltipTrigger asChild>
                <SidebarMenuButton
                  type="button"
                  className="h-8 p-1 md:p-2 cursor-pointer"
                  onClick={() => {
                    setOpenMobile(false);
                    navigate('/saved');
                  }}
                >
                  <Bookmark className="size-4 shrink-0 text-muted-foreground" />
                  <span className="group-data-[collapsible=icon]:hidden">
                    Saved Searches
                  </span>
                </SidebarMenuButton>
              </TooltipTrigger>
              <TooltipContent side="right" style={{ display: open ? 'none' : 'block' }}>Saved Searches</TooltipContent>
            </Tooltip>
          </SidebarMenuItem>

        </SidebarMenu>
      </div>

      {/* ── Chat history ────────────────────────────────────────────── */}
      <SidebarContent>
        {effectiveOpen && <SidebarHistory user={user} />}
      </SidebarContent>

      {/* ── User nav ────────────────────────────────────────────────── */}
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <Tooltip>
              <TooltipTrigger asChild>
                <SidebarMenuButton
                  type="button"
                  className="h-8 p-1 md:p-2 cursor-pointer"
                  onClick={() => {
                    setOpenMobile(false);
                    navigate('/dashboard');
                  }}
                >
                  <LayoutDashboard className="size-4 shrink-0 text-muted-foreground" />
                  <span className="group-data-[collapsible=icon]:hidden">
                    Dashboard
                  </span>
                </SidebarMenuButton>
              </TooltipTrigger>
              <TooltipContent side="right" style={{ display: open ? 'none' : 'block' }}>Dashboard</TooltipContent>
            </Tooltip>
          </SidebarMenuItem>
        </SidebarMenu>
        {user && (
          <SidebarUserNav user={user} preferredUsername={preferredUsername} />
        )}
      </SidebarFooter>
    </Sidebar>
  );
}
