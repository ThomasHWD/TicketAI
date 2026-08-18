import { ChevronLeft, ChevronRight } from "lucide-react";

interface SidebarToggleProps {
  collapsed: boolean;
  onToggle: () => void;
}

export default function SidebarToggle({ collapsed, onToggle }: SidebarToggleProps) {
  return (
    <button
      onClick={onToggle}
      className={`absolute top-7 -translate-x-1/2 z-30
        flex items-center justify-center w-5 h-5 rounded-full
        bg-white dark:bg-[#1c1c1e]
        border border-gray-200 dark:border-[#2a2a2d]
        text-gray-400 dark:text-gray-500
        hover:text-gray-700 dark:hover:text-gray-300
        hover:border-gray-300 dark:hover:border-[#3a3a3d]
        shadow-sm
        transition-[left,border-color,color] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500
        ${collapsed ? "left-14" : "left-56"}`}
      title={collapsed ? "Déplier le menu" : "Replier le menu"}
      aria-label={collapsed ? "Déplier le menu latéral" : "Replier le menu latéral"}
    >
      {collapsed ? <ChevronRight size={11} strokeWidth={2.5} /> : <ChevronLeft size={11} strokeWidth={2.5} />}
    </button>
  );
}
