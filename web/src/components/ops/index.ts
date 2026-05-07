/**
 * Operations Black primitives — barrel export.
 *
 * Use:
 *   import { Panel, OpsButton, Tag, Dot, AgentGlyph } from "@/components/ops";
 *
 * Tokens live in web/src/app/globals.css under the --ops-* namespace.
 */

export { Panel } from "./Panel";
export { OpsButton } from "./OpsButton";
export { Tag } from "./Tag";
export { Dot } from "./Dot";
export { AgentGlyph } from "./AgentGlyph";
export { Bars } from "./Bars";
export { SubH } from "./SubH";
export { Hatch } from "./Hatch";
export { Kbd } from "./Kbd";
export { KV } from "./KV";
export { Clock } from "./Clock";
export { BrandMark } from "./BrandMark";
export { Scanline } from "./Scanline";
export { CornerTicks } from "./CornerTicks";
export { OpsField, OpsInput, OpsTextarea } from "./OpsField";
export { Topbar } from "./Topbar";
export { Statusbar } from "./Statusbar";
export {
  AGENT_IDENTITIES,
  SUBSYSTEM_AGENTS,
  getAgentIdentity,
} from "./agent-identity";
export type { AgentId, AgentIdentity } from "./agent-identity";
