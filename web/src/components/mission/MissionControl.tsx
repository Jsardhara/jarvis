"use client";

import { useMissionBus } from "@/hooks/useMissionBus";
import { AgentFleet } from "./AgentFleet";
import { DispatchGraph } from "./DispatchGraph";
import { AtlasSubFlowRail } from "./AtlasSubFlowRail";
import { ConfirmationDeck } from "./ConfirmationDeck";
import { ActivitySwimlanes } from "./ActivitySwimlanes";
import { VoicePanel } from "./VoicePanel";
import { ChatDialog } from "./ChatDialog";
import { ConversationPanel } from "./ConversationPanel";

/**
 * Mission Control — top-level layout.
 *
 * Reads from the single useMissionBus aggregator so every panel
 * shares one WebSocket session.
 */
export function MissionControl() {
  const bus = useMissionBus();

  return (
    <div className="flex flex-col gap-3 p-3">
      {/* Status bar handled globally by layout-shell.tsx topbar */}

      <div className="flex flex-col gap-3 lg:flex-row">
        <AgentFleet events={bus.events} />

        <div className="flex flex-1 flex-col gap-3">
          <DispatchGraph events={bus.events} />
          <AtlasSubFlowRail events={bus.events} />
        </div>

        <div className="lg:w-[300px]">
          <ConfirmationDeck />
        </div>
      </div>

      <ActivitySwimlanes events={bus.events} />

      <ConversationPanel />

      <VoicePanel voice={bus.voice} samples={bus.voiceSamples} />

      <ChatDialog />
    </div>
  );
}
