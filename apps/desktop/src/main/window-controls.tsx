import { getCurrentWindow } from "@tauri-apps/api/window";
import { platform } from "@tauri-apps/plugin-os";
import { MinusIcon, SquareIcon, XIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@hypr/utils";

// Total pixel width of the controls (3 buttons × w-11 = 3 × 44px). Top-right app
// chrome reserves this much space on frameless platforms so it doesn't sit under
// the controls.
export const WINDOW_CONTROLS_WIDTH_PX = 132;

// Custom window controls for frameless windows. macOS keeps its native
// traffic-light buttons (the window is created with decorations there), so we
// only render these on platforms where the window is frameless (Windows/Linux).
export function WindowControls() {
  if (platform() === "macos") {
    return null;
  }

  const appWindow = getCurrentWindow();

  return (
    <div
      data-tauri-drag-region="false"
      className="pointer-events-auto flex items-center"
    >
      <WindowControlButton
        ariaLabel="Свернуть"
        onClick={() => void appWindow.minimize()}
      >
        <MinusIcon size={15} />
      </WindowControlButton>
      <WindowControlButton
        ariaLabel="Развернуть"
        onClick={() => void appWindow.toggleMaximize()}
      >
        <SquareIcon size={12} />
      </WindowControlButton>
      <WindowControlButton
        ariaLabel="Закрыть"
        danger
        onClick={() => void appWindow.close()}
      >
        <XIcon size={16} />
      </WindowControlButton>
    </div>
  );
}

function WindowControlButton({
  ariaLabel,
  children,
  danger = false,
  onClick,
}: {
  ariaLabel: string;
  children: ReactNode;
  danger?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      data-tauri-drag-region="false"
      className={cn([
        "flex h-8 w-11 items-center justify-center transition-colors",
        "text-muted-foreground focus-visible:outline-hidden",
        danger
          ? "hover:bg-red-500 hover:text-white"
          : "hover:bg-accent hover:text-foreground",
      ])}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
