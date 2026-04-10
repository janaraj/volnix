import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ArrowDownToLine } from 'lucide-react';
import { motion } from 'framer-motion';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { WorldEvent } from '@/types/domain';
import { EmptyState } from '@/components/feedback/empty-state';
import { formatTick } from '@/lib/formatters';
import { outcomeToColorClass } from '@/lib/classifiers';
import { cn } from '@/lib/cn';

// ===========================================================================
// Types
// ===========================================================================

export type ChatSide = 'left' | 'right' | 'center';

interface ChatViewProps {
  events: WorldEvent[];
  onSelectActor?: (actorId: string) => void;
  /**
   * Rendering mode.
   * - `false` (default): self-contained scrollable container with auto-scroll-to-bottom
   *   and jump-to-latest FAB. Used by Live Console (bounded pane height).
   * - `true`: natural document flow — no internal scroll, no auto-scroll, no FAB.
   *   Content grows naturally; the outer page scrollbar handles navigation.
   *   Used by Run Report where users read the full conversation top-to-bottom.
   */
  inline?: boolean;
}

// ===========================================================================
// Predicate + helpers (exported for tests and reuse)
// ===========================================================================

export function isChatEvent(e: WorldEvent): boolean {
  return (
    Boolean(e.event_type?.startsWith('world.')) &&
    (e.action === 'chat.postMessage' || e.action === 'chat_postMessage') &&
    e.service_id === 'slack'
  );
}

/**
 * Generic predicate for ANY structured game move event.
 *
 * All game tools (`negotiate_*`, `auction_*`, `debate_*`, etc.) commit with
 * `service_id='game'` — this is the canonical backend marker set by the game
 * engine, NOT a hardcoded list of action names. Future game types work
 * automatically without any code change in this file.
 *
 * See `volnix/game/evaluators/negotiation.py:NEGOTIATION_TOOLS` where every
 * `ToolDefinition` uses `service="game"`. The state engine sets
 * `event_type = f"world.{action}"` at commit time.
 */
export function isGameMoveEvent(e: WorldEvent): boolean {
  return Boolean(e.event_type?.startsWith('world.')) && e.service_id === 'game';
}

/**
 * Narrow predicate for the game completion event. Used by ChatView to render
 * a full-width conclusion card at the end of the timeline.
 */
export function isGameConclusionEvent(e: WorldEvent): boolean {
  return e.event_type === 'game.completed';
}

/**
 * Broader predicate for ANY game engine lifecycle event
 * (started, round_*, completed, score_updated, etc.). Exported for future
 * extensions (round dividers, score tickers). Not used for rendering in V1 —
 * only `game.completed` is rendered; this is for future use.
 */
export function isGameLifecycleEvent(e: WorldEvent): boolean {
  return Boolean(e.event_type?.startsWith('game.'));
}

/**
 * Combined chat-tab timeline: chat messages (Slack) + game moves (any game) +
 * game conclusion event.
 */
export function isTimelineEvent(e: WorldEvent): boolean {
  return isChatEvent(e) || isGameMoveEvent(e) || isGameConclusionEvent(e);
}

export function isSystemActor(actorId: string): boolean {
  return (
    actorId.startsWith('system-') ||
    actorId.startsWith('world-') ||
    actorId === 'animator' ||
    actorId === 'world_compiler'
  );
}

export function buildSideMap(items: WorldEvent[]): Record<string, ChatSide> {
  const map: Record<string, ChatSide> = {};
  const nonSystem = new Set<string>();
  for (const e of items) {
    // Skip events with no actor (e.g., game.completed has actor_id="").
    // Without this guard, an empty string would be added to nonSystem and
    // corrupt the right/left assignment for 2-party games.
    if (!e.actor_id) continue;
    if (isSystemActor(e.actor_id)) {
      map[e.actor_id] = 'center';
    } else {
      nonSystem.add(e.actor_id);
    }
  }
  const sorted = [...nonSystem].sort();
  if (sorted.length === 2) {
    map[sorted[0]] = 'right';
    map[sorted[1]] = 'left';
  } else {
    sorted.forEach((id) => {
      map[id] = 'left';
    });
  }
  return map;
}

export function getDisplayRole(event: WorldEvent): string {
  if (event.actor_role && event.actor_role.trim()) return event.actor_role;
  const id = event.actor_id || 'unknown';
  const prefix = id.split('-')[0];
  return prefix || id;
}

export function getRoleInitial(event: WorldEvent): string {
  const role = getDisplayRole(event);
  return (role[0] || '?').toUpperCase();
}

const AVATAR_BG_CLASSES = [
  'bg-info text-white',
  'bg-success text-white',
  'bg-warning text-bg-base',
  'bg-accent text-white',
  'bg-error text-white',
  'bg-neutral text-white',
] as const;

export function actorIdToAvatarBg(actorId: string): string {
  let hash = 0;
  for (let i = 0; i < actorId.length; i++) {
    hash = (hash * 31 + actorId.charCodeAt(i)) | 0;
  }
  return AVATAR_BG_CLASSES[Math.abs(hash) % AVATAR_BG_CLASSES.length];
}

export function extractChatText(event: WorldEvent): string {
  const input = event.input_data as { text?: unknown } | undefined;
  const response = event.response_body as { message?: { text?: unknown } } | undefined;
  if (typeof input?.text === 'string') return input.text;
  if (typeof response?.message?.text === 'string') return response.message.text;
  return '(no text)';
}

function extractChannelId(event: WorldEvent): string {
  return (
    (event.input_data?.channel_id as string | undefined) ??
    (event.input_data?.channel as string | undefined) ??
    ''
  );
}

export function isFirstOfGroup(items: WorldEvent[], index: number): boolean {
  if (index === 0) return true;
  return items[index].actor_id !== items[index - 1].actor_id;
}

// ===========================================================================
// Generic game-move formatters (no hardcoded action or field names)
// ===========================================================================

/**
 * Transform a snake_case action name into uppercase spaced words.
 * `negotiate_propose` → `NEGOTIATE PROPOSE`
 * `auction_bid` → `AUCTION BID`
 * Pure transformation, no lookup tables, works for any future game type.
 */
function formatActionName(action: string | undefined | null): string {
  return (action || 'UNKNOWN').replace(/_/g, ' ').toUpperCase();
}

/**
 * Transform a snake_case field key into Title Case.
 * `delivery_weeks` → `Delivery Weeks`
 * `deal_id` → `Deal Id`
 */
function formatFieldKey(key: string): string {
  return key
    .split('_')
    .map((w) => (w.length > 0 ? w[0].toUpperCase() + w.slice(1) : ''))
    .join(' ');
}

export interface ClassifiedFields {
  compact: Array<[string, string]>;
  long: Array<[string, string]>;
  complex: Array<[string, string]>;
}

/**
 * Partition an arbitrary tool input payload into visual buckets based
 * purely on value type and size (no hardcoded field-name special cases):
 *
 * - `compact`: numbers, booleans, short strings (≤40 chars) — rendered inline
 * - `long`: strings > 40 chars (LLM messages usually land here) — rendered as quote
 * - `complex`: objects and arrays — rendered as JSON preview
 *
 * Alphabetical sort within each bucket for stable display regardless of the
 * source JSON key order (LLM emission order is unreliable).
 *
 * `null` and `undefined` values are dropped defensively.
 */
export function classifyFields(input: Record<string, unknown> | undefined): ClassifiedFields {
  const compact: Array<[string, string]> = [];
  const long: Array<[string, string]> = [];
  const complex: Array<[string, string]> = [];
  if (!input) return { compact, long, complex };
  for (const [key, value] of Object.entries(input)) {
    if (value === null || value === undefined) continue;
    if (typeof value === 'number' || typeof value === 'boolean') {
      compact.push([key, String(value)]);
    } else if (typeof value === 'string') {
      if (value.length <= 40) {
        compact.push([key, value]);
      } else {
        long.push([key, value]);
      }
    } else {
      complex.push([key, JSON.stringify(value)]);
    }
  }
  compact.sort(([a], [b]) => a.localeCompare(b));
  long.sort(([a], [b]) => a.localeCompare(b));
  complex.sort(([a], [b]) => a.localeCompare(b));
  return { compact, long, complex };
}

// ===========================================================================
// Game conclusion helpers (generic across game types)
// ===========================================================================

export interface GameStanding {
  actor_id: string;
  total_score: number;
  rank: number;
  metrics?: Record<string, number>;
  eliminated?: boolean;
}

const KNOWN_GAME_REASONS: Record<string, string> = {
  score_threshold: 'Score Threshold',
  rounds_complete: 'Rounds Complete',
  elimination: 'Elimination',
  time_limit: 'Time Limit',
};

/**
 * Prettify a game completion reason. Known reasons map to friendly names;
 * unknown reasons fall back to snake_case → Title Case (generic, non-hardcoded).
 */
export function formatGameReason(reason: string | undefined | null): string {
  if (!reason) return 'Game Complete';
  return (
    KNOWN_GAME_REASONS[reason] ??
    reason.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

/**
 * Heuristic BATNA / no-decisive-winner detection.
 *
 * When all players have the same total_score, no one decisively won — most
 * likely the game engine fell back to BATNA (or equivalent fallback). Works
 * for any game type without per-game special-casing.
 */
export function isBatnaConclusion(standings: GameStanding[]): boolean {
  if (!standings || standings.length < 2) return false;
  const first = standings[0]?.total_score;
  if (first === undefined) return false;
  return standings.every((s) => s.total_score === first);
}

/**
 * Display-friendly name from actor_id (e.g., `buyer-794aad24` → `buyer`).
 */
function actorIdToDisplayName(actorId: string): string {
  const prefix = (actorId || '').split('-')[0];
  return prefix || actorId || 'unknown';
}

// ===========================================================================
// Markdown component overrides — tuned for narrow chat-bubble width
// ===========================================================================

const MARKDOWN_COMPONENTS: Components = {
  p: ({ children }) => <p className="my-0.5 leading-relaxed">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => <ul className="my-1 list-disc space-y-0.5 pl-4">{children}</ul>,
  ol: ({ children }) => <ol className="my-1 list-decimal space-y-0.5 pl-4">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  code: ({ children, className }) =>
    className ? (
      <code className={cn('font-mono text-[11px]', className)}>{children}</code>
    ) : (
      <code className="rounded bg-bg-surface/60 px-1 py-0.5 font-mono text-[11px]">
        {children}
      </code>
    ),
  pre: ({ children }) => (
    <pre className="my-1 overflow-x-auto rounded border border-border/30 bg-bg-surface/60 p-2 font-mono text-[11px] leading-snug">
      {children}
    </pre>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-info hover:underline"
    >
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="my-1 overflow-x-auto">
      <table className="border-collapse border border-border/30 text-[11px]">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-bg-surface/60">{children}</thead>,
  th: ({ children }) => (
    <th className="border border-border/30 px-1.5 py-0.5 text-left font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border border-border/30 px-1.5 py-0.5">{children}</td>,
  hr: () => <hr className="my-2 border-border/30" />,
  blockquote: ({ children }) => (
    <blockquote className="my-1 border-l-2 border-border/40 pl-2 italic text-text-muted">
      {children}
    </blockquote>
  ),
  h1: ({ children }) => <h1 className="my-1 text-sm font-bold">{children}</h1>,
  h2: ({ children }) => <h2 className="my-1 text-sm font-bold">{children}</h2>,
  h3: ({ children }) => <h3 className="my-1 text-xs font-bold">{children}</h3>,
  h4: ({ children }) => <h4 className="my-1 text-xs font-semibold">{children}</h4>,
};

function MarkdownText({ text }: { text: string }) {
  return (
    <div className="text-xs text-text-primary break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
        {text}
      </ReactMarkdown>
    </div>
  );
}

// ===========================================================================
// Avatar circle
// ===========================================================================

interface AvatarProps {
  event: WorldEvent;
  onSelectActor?: (actorId: string) => void;
}

function Avatar({ event, onSelectActor }: AvatarProps) {
  const initial = getRoleInitial(event);
  const bg = actorIdToAvatarBg(event.actor_id);
  const classes = cn(
    'flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-[11px] font-semibold',
    bg,
  );
  if (onSelectActor) {
    return (
      <button
        type="button"
        onClick={() => onSelectActor(event.actor_id)}
        className={cn(classes, 'hover:ring-2 hover:ring-border transition-shadow')}
        title={event.actor_id}
        aria-label={`View ${event.actor_id}`}
      >
        {initial}
      </button>
    );
  }
  return (
    <div className={classes} title={event.actor_id}>
      {initial}
    </div>
  );
}

// ===========================================================================
// Header (name · channel · tick)
// ===========================================================================

interface HeaderProps {
  event: WorldEvent;
  side: ChatSide;
  onSelectActor?: (actorId: string) => void;
}

function Header({ event, side, onSelectActor }: HeaderProps) {
  const displayRole = getDisplayRole(event);
  const channelId = extractChannelId(event);
  const tick = event.timestamp?.tick ?? 0;

  const nameEl = onSelectActor ? (
    <button
      type="button"
      onClick={() => onSelectActor(event.actor_id)}
      className="font-semibold text-text-primary hover:underline"
      title={event.actor_id}
    >
      {displayRole}
    </button>
  ) : (
    <span className="font-semibold text-text-primary" title={event.actor_id}>
      {displayRole}
    </span>
  );

  return (
    <div
      className={cn(
        'mb-1 flex items-baseline gap-2 text-xs',
        side === 'right' && 'flex-row-reverse',
      )}
    >
      {nameEl}
      <span className="font-mono text-[10px] text-text-muted">
        {channelId && `#${channelId}`}
        {channelId && tick > 0 && ' · '}
        {tick > 0 && formatTick(tick)}
      </span>
    </div>
  );
}

// ===========================================================================
// Single chat message (bubble + optional header/avatar)
// ===========================================================================

interface ChatMessageProps {
  event: WorldEvent;
  side: ChatSide;
  showHeader: boolean;
  onSelectActor?: (actorId: string) => void;
}

function ChatMessage({ event, side, showHeader, onSelectActor }: ChatMessageProps) {
  if (side === 'center') {
    return <SystemAnnouncement event={event} />;
  }

  const isFailed = Boolean(event.outcome && event.outcome !== 'success');
  const text = extractChatText(event);

  const bubbleClasses = cn(
    'rounded-2xl border px-4 py-2.5 shadow-sm',
    side === 'left'
      ? 'bg-success/10 border-success/30 rounded-tl-sm'
      : 'bg-info/15 border-info/40 rounded-tr-sm',
    isFailed && 'opacity-60',
  );

  const rowClasses = cn(
    'flex items-start gap-3 max-w-[78%]',
    side === 'right' ? 'ml-auto flex-row-reverse' : 'mr-auto',
    showHeader ? 'mt-4' : 'mt-1.5',
  );

  const avatarCol = showHeader ? (
    <Avatar event={event} onSelectActor={onSelectActor} />
  ) : (
    <div className="h-7 w-7 flex-shrink-0" aria-hidden />
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className={rowClasses}
    >
      {avatarCol}
      <div className="min-w-0 flex-1">
        {showHeader && <Header event={event} side={side} onSelectActor={onSelectActor} />}
        <div className={bubbleClasses}>
          <MarkdownText text={text} />
          {isFailed && (
            <div className="mt-1 border-t border-error/20 pt-1 text-[10px]">
              <span className={cn('uppercase', outcomeToColorClass(event.outcome ?? ''))}>
                {event.outcome}
              </span>
              {event.policy_hit?.policy_name && (
                <span className="ml-1 text-text-muted">· {event.policy_hit.policy_name}</span>
              )}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ===========================================================================
// System announcement (centered, muted)
// ===========================================================================

function SystemAnnouncement({ event }: { event: WorldEvent }) {
  const text = extractChatText(event);
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className="my-3 flex justify-center"
    >
      <div className="max-w-[75%] rounded-lg border border-border/20 bg-bg-surface/60 px-3 py-1.5 text-text-muted">
        <div className="mb-0.5 text-[9px] font-semibold uppercase tracking-wider text-text-muted/70">
          System
        </div>
        <MarkdownText text={text} />
      </div>
    </motion.div>
  );
}

// ===========================================================================
// Game move card (generic — works for any game type)
// ===========================================================================

function GameMoveFields({ fields }: { fields: ClassifiedFields }) {
  const hasAny = fields.compact.length + fields.long.length + fields.complex.length > 0;
  if (!hasAny) {
    return <div className="text-[11px] italic text-text-muted">(no fields)</div>;
  }
  return (
    <div className="space-y-1">
      {fields.compact.length > 0 && (
        <div className="flex flex-wrap gap-x-2 gap-y-0.5 font-mono text-[11px] text-text-secondary">
          {fields.compact.map(([key, value], i) => (
            <span key={key}>
              <span className="text-text-muted">{formatFieldKey(key)}:</span>{' '}
              <span className="text-text-primary">{value}</span>
              {i < fields.compact.length - 1 && <span className="ml-2 text-text-muted">·</span>}
            </span>
          ))}
        </div>
      )}
      {fields.long.map(([key, value]) => (
        <div
          key={key}
          className="border-t border-accent/20 pt-1 text-[11px] italic text-text-muted"
        >
          <span className="font-mono text-[10px] not-italic text-text-muted/70">
            {formatFieldKey(key)}:
          </span>{' '}
          <span className="break-words">"{value}"</span>
        </div>
      ))}
      {fields.complex.map(([key, value]) => (
        <div key={key} className="border-t border-accent/20 pt-1">
          <div className="font-mono text-[10px] text-text-muted/70">{formatFieldKey(key)}:</div>
          <pre className="overflow-x-auto rounded bg-bg-surface/60 p-1.5 font-mono text-[10px] leading-snug text-text-secondary">
            {value}
          </pre>
        </div>
      ))}
    </div>
  );
}

function FailedMoveFooter({ event }: { event: WorldEvent }) {
  return (
    <div className="mt-1 border-t border-error/20 pt-1 text-[10px]">
      <span className={cn('uppercase', outcomeToColorClass(event.outcome ?? ''))}>
        {event.outcome}
      </span>
      {event.policy_hit?.policy_name && (
        <span className="ml-1 text-text-muted">· {event.policy_hit.policy_name}</span>
      )}
    </div>
  );
}

interface GameMoveCardProps {
  event: WorldEvent;
  side: ChatSide;
  showHeader: boolean;
  onSelectActor?: (actorId: string) => void;
}

function GameMoveCard({ event, side, showHeader, onSelectActor }: GameMoveCardProps) {
  const isFailed = Boolean(event.outcome && event.outcome !== 'success');
  const actionLabel = formatActionName(event.action);
  const fields = classifyFields(event.input_data as Record<string, unknown> | undefined);

  const actionBadge = (
    <span className="rounded bg-accent/20 px-1.5 py-0.5 font-mono text-[10px] font-bold tracking-wider text-accent">
      {actionLabel}
    </span>
  );

  // Center variant for system actors
  if (side === 'center') {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18, ease: 'easeOut' }}
        className="my-3 flex justify-center"
      >
        <div
          className={cn(
            'max-w-[80%] rounded-lg border border-accent/30 bg-accent/5 px-3 py-2',
            isFailed && 'opacity-60',
          )}
        >
          <div className="mb-1 flex items-center gap-2">
            <span className="text-[9px] font-semibold uppercase tracking-wider text-text-muted/70">
              System
            </span>
            {actionBadge}
          </div>
          <GameMoveFields fields={fields} />
          {isFailed && <FailedMoveFooter event={event} />}
        </div>
      </motion.div>
    );
  }

  // Left/right variants
  const cardClasses = cn(
    'rounded-lg border border-accent/40 bg-accent/5 px-4 py-2.5 shadow-sm',
    isFailed && 'opacity-60',
  );

  const rowClasses = cn(
    'flex items-start gap-3 max-w-[78%]',
    side === 'right' ? 'ml-auto flex-row-reverse' : 'mr-auto',
    showHeader ? 'mt-4' : 'mt-1.5',
  );

  const avatarCol = showHeader ? (
    <Avatar event={event} onSelectActor={onSelectActor} />
  ) : (
    <div className="h-7 w-7 flex-shrink-0" aria-hidden />
  );

  const displayRole = getDisplayRole(event);
  const tick = event.timestamp?.tick ?? 0;

  const nameEl = onSelectActor ? (
    <button
      type="button"
      onClick={() => onSelectActor(event.actor_id)}
      className="font-semibold text-text-primary hover:underline"
      title={event.actor_id}
    >
      {displayRole}
    </button>
  ) : (
    <span className="font-semibold text-text-primary" title={event.actor_id}>
      {displayRole}
    </span>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className={rowClasses}
    >
      {avatarCol}
      <div className="min-w-0 flex-1">
        {showHeader && (
          <div
            className={cn(
              'mb-1 flex items-baseline gap-2 text-xs',
              side === 'right' && 'flex-row-reverse',
            )}
          >
            {nameEl}
            {tick > 0 && (
              <span className="font-mono text-[10px] text-text-muted">{formatTick(tick)}</span>
            )}
            {actionBadge}
          </div>
        )}
        <div className={cardClasses}>
          {!showHeader && <div className="mb-1">{actionBadge}</div>}
          <GameMoveFields fields={fields} />
          {isFailed && <FailedMoveFooter event={event} />}
        </div>
      </div>
    </motion.div>
  );
}

// ===========================================================================
// Game conclusion card (full-width, shown at the end of the timeline)
// ===========================================================================

interface GameConcludedCardProps {
  event: WorldEvent;
}

function GameConcludedCard({ event }: GameConcludedCardProps) {
  // Pull fields off the raw event. They're top-level per backend spec,
  // not inside input_data.
  const e = event as WorldEvent & {
    winner?: string | null;
    reason?: string | null;
    total_rounds_played?: number;
    final_standings?: GameStanding[];
  };

  const winner = e.winner ?? null;
  const reason = formatGameReason(e.reason);
  const rounds = e.total_rounds_played ?? 0;
  const standings = e.final_standings ?? [];
  const isBatna = isBatnaConclusion(standings);

  const tintClasses = isBatna
    ? 'border-warning/40 bg-warning/5'
    : 'border-success/40 bg-success/5';

  const badgeClasses = isBatna
    ? 'bg-warning/20 text-warning'
    : 'bg-success/20 text-success';

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="my-6 flex justify-center"
    >
      <div
        className={cn(
          'w-full max-w-[92%] rounded-xl border-2 px-5 py-4 shadow-lg',
          tintClasses,
        )}
      >
        {/* Header */}
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <span
            className={cn(
              'rounded-md px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-wider',
              badgeClasses,
            )}
          >
            Game Completed
          </span>
          <span className="text-xs text-text-muted">·</span>
          <span className="text-xs font-semibold text-text-primary">{reason}</span>
          {rounds > 0 && (
            <>
              <span className="text-xs text-text-muted">·</span>
              <span className="text-xs text-text-muted">{rounds} rounds</span>
            </>
          )}
        </div>

        {/* Winner callout — only when decisive */}
        {winner && !isBatna && (
          <div className="mb-3 text-sm">
            <span className="text-text-muted">Winner: </span>
            <span className="font-semibold text-text-primary">
              {actorIdToDisplayName(winner)}
            </span>
          </div>
        )}

        {/* Standings table */}
        {standings.length > 0 && (
          <div className="mb-3 space-y-1">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              Final Standings
            </div>
            <div className="space-y-0.5">
              {standings.map((s) => (
                <div
                  key={s.actor_id}
                  className="flex items-center gap-3 rounded bg-bg-base/40 px-2 py-1 font-mono text-xs"
                >
                  <span className="w-6 text-text-muted">#{s.rank}</span>
                  <span className="flex-1 text-text-primary">
                    {actorIdToDisplayName(s.actor_id)}
                  </span>
                  <span className="text-info">{s.total_score.toFixed(1)}</span>
                  {s.eliminated && (
                    <span className="rounded bg-error/20 px-1.5 py-0.5 text-[9px] uppercase text-error">
                      eliminated
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tied-score fallback footer — generic across game types */}
        {isBatna && (
          <div className="mt-3 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
            <div className="font-semibold">No decisive outcome — fallback applied</div>
            <div className="mt-0.5 text-text-muted">
              All players ended at the same score. The game engine applied its
              fallback scoring rule — no player achieved a decisive advantage
              (e.g., BATNA in negotiation games, reserve price in auctions, tie
              in debate, etc.).
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ===========================================================================
// Main ChatView
// ===========================================================================

export function ChatView({ events, onSelectActor, inline = false }: ChatViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Filter + reverse to chronological order. Timeline = chat messages + game moves.
  const timelineItems = useMemo(() => {
    return events.filter(isTimelineEvent).slice().reverse();
  }, [events]);

  // Deterministic per-actor side assignment based on ALL timeline participants
  const sideMap = useMemo(() => buildSideMap(timelineItems), [timelineItems]);

  // Initial mount — pin to bottom before paint (scrollable mode only)
  useLayoutEffect(() => {
    if (inline) return;
    if (scrollRef.current && timelineItems.length > 0) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // New messages — scroll to bottom if user hasn't manually scrolled up (scrollable mode only)
  useEffect(() => {
    if (inline) return;
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [timelineItems.length, autoScroll, inline]);

  function handleScroll() {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    setAutoScroll(distanceFromBottom < 32);
  }

  function handleJumpToBottom() {
    if (!scrollRef.current) return;
    setAutoScroll(true);
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }

  // Shared message list — same in both modes. Dispatches to ChatMessage
  // (for Slack chat) or GameMoveCard (for any game tool call).
  const messageList =
    timelineItems.length === 0 ? (
      <EmptyState
        title="No chat messages yet"
        description="Agents haven't posted to Slack or made game moves in this run."
      />
    ) : (
      timelineItems.map((event, i) => {
        const key = event.event_id ?? `${event.actor_id}-${i}`;
        // Conclusion card is full-width and doesn't care about side/group —
        // check it FIRST before computing side/showHeader.
        if (isGameConclusionEvent(event)) {
          return <GameConcludedCard key={key} event={event} />;
        }
        const side = sideMap[event.actor_id] ?? 'left';
        const showHeader = isFirstOfGroup(timelineItems, i);
        if (isGameMoveEvent(event)) {
          return (
            <GameMoveCard
              key={key}
              event={event}
              side={side}
              showHeader={showHeader}
              onSelectActor={onSelectActor}
            />
          );
        }
        return (
          <ChatMessage
            key={key}
            event={event}
            side={side}
            showHeader={showHeader}
            onSelectActor={onSelectActor}
          />
        );
      })
    );

  // Inline mode — natural document flow, no internal scroll, no auto-scroll.
  // Used by Run Report's ChatTab. The outer page scrollbar (AppShell <main>)
  // handles navigation. Content starts at the top (natural reading order).
  if (inline) {
    return <div className="px-5 py-5">{messageList}</div>;
  }

  // Scrollable mode — bounded-height container with internal scroll and
  // auto-scroll-to-bottom. Used by Live Console's center Chat pane.
  return (
    <div className="relative flex h-full flex-col">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="min-h-0 flex-1 overflow-auto px-5 py-5"
      >
        {messageList}
      </div>
      {!autoScroll && timelineItems.length > 0 && (
        <button
          type="button"
          onClick={handleJumpToBottom}
          className="absolute bottom-4 right-4 rounded-full bg-info p-2 text-white shadow-lg transition-transform hover:scale-110"
          title="Jump to latest"
          aria-label="Jump to latest"
        >
          <ArrowDownToLine size={16} />
        </button>
      )}
    </div>
  );
}
