import { ChevronLeft, ChevronRight } from "lucide-react";

interface SidebarToggleProps {
  collapsed: boolean;
  onToggle: () => void;
}

export default function SidebarToggle({ collapsed, onToggle }: SidebarToggleProps) {
  return (
    <button
      onClick={onToggle}
      className={`absolute top-7 -translate-x-1/2 z-30 group
        w-11 h-11 flex items-center justify-center
        transition-[left] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:rounded-full
        ${collapsed ? "left-14" : "left-56"}`}
      title={collapsed ? "Déplier le menu" : "Replier le menu"}
      aria-label={collapsed ? "Déplier le menu latéral" : "Replier le menu latéral"}
    >
      <span className="flex items-center justify-center w-5 h-5 rounded-full
        bg-white dark:bg-[#1c1c1e]
        border border-gray-200 dark:border-[#2a2a2d]
        text-gray-500 dark:text-gray-400
        group-hover:border-gray-300 dark:group-hover:border-[#3a3a3d]
        group-hover:text-gray-700 dark:group-hover:text-gray-300
        shadow-sm
        transition-[border-color,color] duration-150">
        {collapsed ? <ChevronRight size={11} strokeWidth={2.5} /> : <ChevronLeft size={11} strokeWidth={2.5} />}
      </span>
    </button>
  );
}
