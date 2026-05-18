import { RadioTower, Github, Menu, Settings, FolderOpen, LogOut, User } from "lucide-react";

interface HeaderProps {
  sessionModel: string | null;
  isConnected: boolean;
  onToggleSidebar: () => void;
  onOpenSettings: () => void;
  onOpenWorkspace: () => void;
  userName?: string;
}

export function Header({ sessionModel, isConnected, onToggleSidebar, onOpenSettings, onOpenWorkspace, userName }: HeaderProps) {
  return (
    <header className="flex items-center justify-between px-3 sm:px-6 py-3 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm safe-top">
      <div className="flex items-center gap-2 sm:gap-3">
        <button
          onClick={onToggleSidebar}
          className="p-2 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors min-w-[40px] min-h-[40px] flex items-center justify-center"
          aria-label="Toggle sidebar"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center">
            <RadioTower className="w-4 h-4 text-white" />
          </div>
          <h1 className="text-lg font-semibold tracking-tight">
            Openreach
            <span className="text-brand-400 ml-1">DispatchAI</span>
          </h1>
        </div>
        <span className="text-xs text-zinc-500 hidden sm:inline">
          Field scheduling copilot
        </span>
      </div>

      <div className="flex items-center gap-2 sm:gap-4">
        {sessionModel && (
          <span className="text-xs px-2 py-1 rounded-full bg-zinc-800 text-zinc-300 font-mono hidden sm:inline-block">
            {sessionModel}
          </span>
        )}
        <div className="flex items-center gap-1.5">
          <div
            className={`w-2 h-2 rounded-full ${
              isConnected ? "bg-emerald-500" : "bg-zinc-600"
            }`}
          />
          <span className="text-xs text-zinc-500 hidden sm:inline">
            {isConnected ? "Connected" : "Disconnected"}
          </span>
        </div>

        {userName && userName !== "Anonymous" && (
          <div className="flex items-center gap-1.5 text-xs text-zinc-400 hidden sm:flex">
            <User className="w-3.5 h-3.5" />
            <span className="max-w-[120px] truncate">{userName}</span>
          </div>
        )}

        <button
          onClick={onOpenWorkspace}
          className="p-2 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors min-w-[40px] min-h-[40px] flex items-center justify-center"
          aria-label="Workspace files"
        >
          <FolderOpen className="w-5 h-5" />
        </button>
        <button
          onClick={onOpenSettings}
          className="p-2 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors min-w-[40px] min-h-[40px] flex items-center justify-center"
          aria-label="Settings"
        >
          <Settings className="w-5 h-5" />
        </button>
        {userName && userName !== "Anonymous" ? (
          <a
            href="/.auth/logout"
            className="p-2 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors min-w-[40px] min-h-[40px] flex items-center justify-center"
            title="Sign out"
          >
            <LogOut className="w-5 h-5" />
          </a>
        ) : (
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="p-2 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors min-w-[40px] min-h-[40px] flex items-center justify-center"
          >
            <Github className="w-5 h-5" />
          </a>
        )}
      </div>
    </header>
  );
}
