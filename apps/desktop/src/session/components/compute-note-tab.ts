import type { EditorView } from "~/store/zustand/tabs/schema";

export function computeCurrentNoteTab(
  tabView: EditorView | null,
  isLiveSessionActive: boolean,
  firstEnhancedNoteId: string | undefined,
  canShowTranscript = false,
): EditorView {
  if (isLiveSessionActive) {
    if (tabView?.type === "raw") {
      return tabView;
    }
    if (tabView?.type === "transcript" && canShowTranscript) {
      return tabView;
    }
    if (tabView?.type === "enhanced" && firstEnhancedNoteId) {
      return tabView;
    }
    // No explicit view chosen during recording: surface the live transcript so
    // the user sees words appear instead of a blank notes page. Switching to the
    // notes ("raw") tab sets an explicit view and is respected above.
    if (!tabView && canShowTranscript) {
      return { type: "transcript" };
    }
    return { type: "raw" };
  }

  if (tabView) {
    if (tabView.type === "raw") {
      return tabView;
    }
    if (tabView.type === "enhanced" && firstEnhancedNoteId) {
      return tabView;
    }
    if (tabView.type === "transcript" && canShowTranscript) {
      return tabView;
    }

    return { type: "raw" };
  }

  if (firstEnhancedNoteId) {
    return { type: "enhanced", id: firstEnhancedNoteId };
  }

  return { type: "raw" };
}
