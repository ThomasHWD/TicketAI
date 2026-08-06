import { ChevronLeft, ChevronRight } from "lucide-react";

interface SidebarToggleProps {
  collapsed: boolean;
  onToggle: () => void;
}

export default function SidebarToggle({ collapsed, onToggle }: SidebarToggleProps) {
  return (
    <button
      onClick={onToggle}
      className={`absolute top-[30px] -translate-x-1/2 z-30
        flex items-center justify-center w-5 h-5 rounded-full
        bg-white/70 dark:bg-gray-200/70
        backdrop-blur-md
        border border-gray-200 dark:border-white/15
        shadow-md text-gray-400 dark:text-gray-500
        hover:text-gray-700 dark:hover:text-green-200 hover:shadow-lg
        transition-[left,color,box-shadow] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]
        ${collapsed ? "left-16" : "left-60"}`}
      title={collapsed ? "Déplier le menu" : "Replier le menu"}
      aria-label={collapsed ? "Déplier le menu latéral" : "Replier le menu latéral"}
    >
      {collapsed ? <ChevronRight size={11} /> : <ChevronLeft size={11} />}
    </button>
  );
}
