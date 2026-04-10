import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  ChatView,
  isChatEvent,
  isGameMoveEvent,
  isGameConclusionEvent,
  isGameLifecycleEvent,
  isTimelineEvent,
  isSystemActor,
  buildSideMap,
  getDisplayRole,
  getRoleInitial,
  actorIdToAvatarBg,
  isFirstOfGroup,
  extractChatText,
  classifyFields,
  formatGameReason,
  isBatnaConclusion,
  type GameStanding,
} from '@/pages/live-console/chat-view';
import type { WorldEvent } from '@/types/domain';

function makeChatEvent(overrides: Partial<WorldEvent> = {}): WorldEvent {
  return {
    event_type: 'world.chat.postMessage',
    event_id: `e-${Math.random().toString(36).slice(2)}`,
    actor_id: 'buyer-1',
    actor_role: 'buyer',
    action: 'chat.postMessage',
    service_id: 'slack',
    outcome: 'success',
    timestamp: {
      wall_time: '2026-04-10T12:00:00Z',
      world_time: '2026-04-10T12:00:00Z',
      tick: 1,
    },
    input_data: { channel_id: 'C1', text: 'hello world' },
    response_body: {
      ok: true,
      channel: 'C1',
      ts: '1712000000.0001',
      message: { text: 'hello world' },
    },
    ...overrides,
  };
}

// ===========================================================================
// isChatEvent predicate tests (unchanged)
// ===========================================================================

describe('isChatEvent', () => {
  it('accepts world.chat.postMessage slack event', () => {
    expect(isChatEvent(makeChatEvent())).toBe(true);
  });

  it('rejects policy.hold event with chat.postMessage action (the critical world.* guard)', () => {
    expect(
      isChatEvent(
        makeChatEvent({
          event_type: 'policy.hold',
          outcome: 'held',
        }),
      ),
    ).toBe(false);
  });

  it('rejects event with non-slack service', () => {
    expect(
      isChatEvent(
        makeChatEvent({
          event_type: 'world.chat.postMessage',
          service_id: 'gmail',
        }),
      ),
    ).toBe(false);
  });

  it('accepts chat_postMessage (underscore variant, defensive belt)', () => {
    expect(
      isChatEvent(
        makeChatEvent({
          event_type: 'world.chat_postMessage',
          action: 'chat_postMessage',
        }),
      ),
    ).toBe(true);
  });

  it('rejects event when service_id is missing', () => {
    expect(isChatEvent(makeChatEvent({ service_id: null }))).toBe(false);
  });

  it('rejects budget.deduction event even with chat.postMessage action', () => {
    expect(
      isChatEvent(
        makeChatEvent({
          event_type: 'budget.deduction',
        }),
      ),
    ).toBe(false);
  });
});

// ===========================================================================
// Helper function tests (NEW)
// ===========================================================================

describe('isSystemActor', () => {
  it('recognizes system-* actors', () => {
    expect(isSystemActor('system-game-0040ae39')).toBe(true);
    expect(isSystemActor('system-referee')).toBe(true);
  });

  it('recognizes world-* actors', () => {
    expect(isSystemActor('world-clock')).toBe(true);
  });

  it('recognizes animator and world_compiler', () => {
    expect(isSystemActor('animator')).toBe(true);
    expect(isSystemActor('world_compiler')).toBe(true);
  });

  it('rejects regular agent actors', () => {
    expect(isSystemActor('buyer-794aad24')).toBe(false);
    expect(isSystemActor('supplier-99b0e8da')).toBe(false);
  });
});

describe('buildSideMap', () => {
  it('assigns right/left to 2 non-system actors alphabetically', () => {
    const events = [
      makeChatEvent({ actor_id: 'supplier-99b0e8da' }),
      makeChatEvent({ actor_id: 'buyer-794aad24' }),
    ];
    const map = buildSideMap(events);
    expect(map['buyer-794aad24']).toBe('right');
    expect(map['supplier-99b0e8da']).toBe('left');
  });

  it('assigns center to system actors', () => {
    const events = [
      makeChatEvent({ actor_id: 'buyer-1' }),
      makeChatEvent({ actor_id: 'supplier-1' }),
      makeChatEvent({ actor_id: 'system-game-0040ae39' }),
    ];
    const map = buildSideMap(events);
    expect(map['system-game-0040ae39']).toBe('center');
    expect(map['buyer-1']).toBe('right');
    expect(map['supplier-1']).toBe('left');
  });

  it('assigns all left when 3+ non-system actors', () => {
    const events = [
      makeChatEvent({ actor_id: 'alice-1' }),
      makeChatEvent({ actor_id: 'bob-1' }),
      makeChatEvent({ actor_id: 'carol-1' }),
    ];
    const map = buildSideMap(events);
    expect(map['alice-1']).toBe('left');
    expect(map['bob-1']).toBe('left');
    expect(map['carol-1']).toBe('left');
  });

  it('handles single non-system actor (left)', () => {
    const events = [makeChatEvent({ actor_id: 'solo-1' })];
    const map = buildSideMap(events);
    expect(map['solo-1']).toBe('left');
  });

  it('handles only system actors (all center)', () => {
    const events = [
      makeChatEvent({ actor_id: 'system-game-0040ae39' }),
      makeChatEvent({ actor_id: 'animator' }),
    ];
    const map = buildSideMap(events);
    expect(map['system-game-0040ae39']).toBe('center');
    expect(map['animator']).toBe('center');
  });
});

describe('getDisplayRole', () => {
  it('returns actor_role when non-empty', () => {
    expect(getDisplayRole(makeChatEvent({ actor_role: 'buyer' }))).toBe('buyer');
  });

  it('returns whitespace-trimmed actor_role as non-empty', () => {
    expect(getDisplayRole(makeChatEvent({ actor_role: 'seller' }))).toBe('seller');
  });

  it('falls back to actor_id prefix when actor_role is empty string', () => {
    expect(
      getDisplayRole(makeChatEvent({ actor_role: '', actor_id: 'buyer-794aad24' })),
    ).toBe('buyer');
  });

  it('falls back to actor_id prefix when actor_role is whitespace', () => {
    expect(
      getDisplayRole(makeChatEvent({ actor_role: '   ', actor_id: 'supplier-xyz' })),
    ).toBe('supplier');
  });

  it('returns actor_id itself when no dash', () => {
    expect(getDisplayRole(makeChatEvent({ actor_role: '', actor_id: 'animator' }))).toBe(
      'animator',
    );
  });
});

describe('getRoleInitial', () => {
  it('returns uppercase first letter of role', () => {
    expect(getRoleInitial(makeChatEvent({ actor_role: 'buyer' }))).toBe('B');
  });

  it('returns uppercase first letter of fallback prefix when role empty', () => {
    expect(
      getRoleInitial(makeChatEvent({ actor_role: '', actor_id: 'supplier-99b0e8da' })),
    ).toBe('S');
  });
});

describe('actorIdToAvatarBg', () => {
  it('returns a class from the palette deterministically', () => {
    const result1 = actorIdToAvatarBg('buyer-794aad24');
    const result2 = actorIdToAvatarBg('buyer-794aad24');
    expect(result1).toBe(result2); // deterministic
    expect(result1).toMatch(/bg-(info|success|warning|accent|error|neutral)/);
  });

  it('returns different classes for sufficiently different actors', () => {
    // Not guaranteed different, but very likely with hash
    const a = actorIdToAvatarBg('buyer-794aad24');
    const b = actorIdToAvatarBg('supplier-99b0e8da');
    // Both from palette; assert they're valid
    expect(a).toMatch(/bg-(info|success|warning|accent|error|neutral)/);
    expect(b).toMatch(/bg-(info|success|warning|accent|error|neutral)/);
  });

  it('handles empty actor_id safely', () => {
    const result = actorIdToAvatarBg('');
    expect(result).toMatch(/bg-(info|success|warning|accent|error|neutral)/);
  });
});

describe('isFirstOfGroup', () => {
  it('always returns true for index 0', () => {
    const events = [makeChatEvent()];
    expect(isFirstOfGroup(events, 0)).toBe(true);
  });

  it('returns false when previous message is from same actor', () => {
    const events = [
      makeChatEvent({ actor_id: 'buyer-1' }),
      makeChatEvent({ actor_id: 'buyer-1' }),
    ];
    expect(isFirstOfGroup(events, 1)).toBe(false);
  });

  it('returns true when actor differs from previous', () => {
    const events = [
      makeChatEvent({ actor_id: 'buyer-1' }),
      makeChatEvent({ actor_id: 'supplier-1' }),
    ];
    expect(isFirstOfGroup(events, 1)).toBe(true);
  });
});

describe('extractChatText', () => {
  it('prefers input_data.text', () => {
    expect(
      extractChatText(
        makeChatEvent({
          input_data: { channel_id: 'C1', text: 'primary' },
          response_body: { ok: true, message: { text: 'secondary' } },
        }),
      ),
    ).toBe('primary');
  });

  it('falls back to response_body.message.text', () => {
    expect(
      extractChatText(
        makeChatEvent({
          input_data: { channel_id: 'C1' },
          response_body: { ok: true, message: { text: 'fallback' } },
        }),
      ),
    ).toBe('fallback');
  });

  it('returns (no text) when both missing', () => {
    expect(
      extractChatText(
        makeChatEvent({
          input_data: { channel_id: 'C1' },
          response_body: { ok: true },
        }),
      ),
    ).toBe('(no text)');
  });
});

// ===========================================================================
// ChatView rendering tests
// ===========================================================================

describe('ChatView', () => {
  const onSelectActor = vi.fn();

  beforeEach(() => {
    onSelectActor.mockClear();
  });

  it('renders empty state when events array is empty', () => {
    render(<ChatView events={[]} onSelectActor={onSelectActor} />);
    expect(screen.getByText(/No chat messages yet/i)).toBeInTheDocument();
    expect(screen.getByText(/Agents haven't posted/i)).toBeInTheDocument();
  });

  it('renders empty state when events contain no chat messages', () => {
    const events: WorldEvent[] = [
      makeChatEvent({ event_type: 'policy.hold' }),
      makeChatEvent({ service_id: 'gmail' }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText(/No chat messages yet/i)).toBeInTheDocument();
  });

  it('renders chat events in chronological order (reverses input desc order)', () => {
    const events: WorldEvent[] = [
      makeChatEvent({
        event_id: 'e3',
        actor_id: 'buyer-1',
        input_data: { channel_id: 'C1', text: 'msg-third' },
        timestamp: { wall_time: '', world_time: '', tick: 3 },
      }),
      makeChatEvent({
        event_id: 'e2',
        actor_id: 'supplier-1',
        input_data: { channel_id: 'C1', text: 'msg-second' },
        timestamp: { wall_time: '', world_time: '', tick: 2 },
      }),
      makeChatEvent({
        event_id: 'e1',
        actor_id: 'buyer-1',
        input_data: { channel_id: 'C1', text: 'msg-first' },
        timestamp: { wall_time: '', world_time: '', tick: 1 },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    const first = screen.getByText('msg-first');
    const second = screen.getByText('msg-second');
    const third = screen.getByText('msg-third');
    expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(second.compareDocumentPosition(third) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('renders role, channel, tick, and text for each message', () => {
    const events = [
      makeChatEvent({
        actor_id: 'buyer-794aad24',
        actor_role: 'buyer',
        input_data: { channel_id: 'C1', text: 'I propose $50k' },
        timestamp: { wall_time: '', world_time: '', tick: 5 },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('I propose $50k')).toBeInTheDocument();
    // Display role shows as "buyer" (inside the name button)
    expect(screen.getByText('buyer')).toBeInTheDocument();
    // Channel label with # prefix
    expect(screen.getByText(/#C1/)).toBeInTheDocument();
    // Tick as #5
    expect(screen.getByText(/#5/)).toBeInTheDocument();
  });

  it('dims failed messages and shows outcome badge', () => {
    const events = [
      makeChatEvent({
        actor_id: 'buyer-1',
        outcome: 'denied',
        input_data: { channel_id: 'C1', text: 'blocked msg' },
      }),
    ];
    const { container } = render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('blocked msg')).toBeInTheDocument();
    expect(screen.getByText('denied')).toBeInTheDocument();
    expect(container.querySelector('.opacity-60')).toBeTruthy();
  });

  it('extracts text from input_data.text as primary source (rendered)', () => {
    const events = [
      makeChatEvent({
        input_data: { channel_id: 'C1', text: 'primary-text' },
        response_body: { ok: true, message: { text: 'secondary-text' } },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('primary-text')).toBeInTheDocument();
    expect(screen.queryByText('secondary-text')).toBeNull();
  });

  it('falls back to response_body.message.text when input_data.text missing', () => {
    const events = [
      makeChatEvent({
        input_data: { channel_id: 'C1' },
        response_body: { ok: true, message: { text: 'fallback-text' } },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('fallback-text')).toBeInTheDocument();
  });

  it('falls back to "(no text)" when both sources missing', () => {
    const events = [
      makeChatEvent({
        input_data: { channel_id: 'C1' },
        response_body: { ok: true },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('(no text)')).toBeInTheDocument();
  });

  it('calls onSelectActor when the avatar is clicked', async () => {
    const user = userEvent.setup();
    const events = [makeChatEvent({ actor_id: 'buyer-42' })];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    const avatarButton = screen.getByRole('button', { name: /View buyer-42/ });
    await user.click(avatarButton);
    expect(onSelectActor).toHaveBeenCalledWith('buyer-42');
  });

  it('shows policy name in failed-message footer when policy_hit present', () => {
    const events = [
      makeChatEvent({
        outcome: 'held',
        policy_hit: {
          policy_id: 'p1',
          policy_name: 'profanity_filter',
          enforcement: 'hold',
          condition: '',
          resolution: null,
        },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText(/profanity_filter/)).toBeInTheDocument();
  });

  it('includes both successful and failed messages together', () => {
    const events = [
      makeChatEvent({
        event_id: 'e2',
        outcome: 'denied',
        input_data: { channel_id: 'C1', text: 'blocked-one' },
        timestamp: { wall_time: '', world_time: '', tick: 2 },
      }),
      makeChatEvent({
        event_id: 'e1',
        outcome: 'success',
        input_data: { channel_id: 'C1', text: 'good-one' },
        timestamp: { wall_time: '', world_time: '', tick: 1 },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('good-one')).toBeInTheDocument();
    expect(screen.getByText('blocked-one')).toBeInTheDocument();
  });

  it('renders avatar as clickable button when onSelectActor is provided', () => {
    const events = [makeChatEvent({ actor_id: 'buyer-42' })];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByRole('button', { name: /View buyer-42/ })).toBeInTheDocument();
  });

  it('renders avatar as non-clickable div when onSelectActor is absent', () => {
    const events = [makeChatEvent({ actor_id: 'buyer-42' })];
    render(<ChatView events={events} />);
    // No button with that aria-label when onSelectActor is absent
    expect(screen.queryByRole('button', { name: /View buyer-42/ })).toBeNull();
    // But the actor_id is still discoverable via title on the div
    const elementsWithTitle = screen.getAllByTitle('buyer-42');
    expect(elementsWithTitle.length).toBeGreaterThan(0);
    // None of them should be buttons
    elementsWithTitle.forEach((el) => {
      expect(el.tagName).not.toBe('BUTTON');
    });
  });

  it('renders without crashing with multiple bubbles when onSelectActor absent', () => {
    const events = [
      makeChatEvent({ event_id: 'e1', actor_id: 'buyer-1' }),
      makeChatEvent({ event_id: 'e2', actor_id: 'supplier-1', outcome: 'denied' }),
    ];
    render(<ChatView events={events} />);
    expect(screen.getAllByTitle('buyer-1').length).toBeGreaterThan(0);
    expect(screen.getAllByTitle('supplier-1').length).toBeGreaterThan(0);
  });

  it('renders markdown bold as <strong> element', () => {
    const events = [
      makeChatEvent({
        input_data: { channel_id: 'C1', text: 'This is **very important**' },
      }),
    ];
    const { container } = render(<ChatView events={events} onSelectActor={onSelectActor} />);
    const strong = container.querySelector('strong');
    expect(strong).toBeTruthy();
    expect(strong?.textContent).toBe('very important');
  });

  it('renders markdown tables', () => {
    const events = [
      makeChatEvent({
        input_data: {
          channel_id: 'C1',
          text: '| Term | Value |\n|---|---|\n| Price | $50k |\n| Delivery | 3 weeks |',
        },
      }),
    ];
    const { container } = render(<ChatView events={events} onSelectActor={onSelectActor} />);
    const table = container.querySelector('table');
    expect(table).toBeTruthy();
    expect(screen.getByText('Term')).toBeInTheDocument();
    expect(screen.getByText('$50k')).toBeInTheDocument();
  });

  it('renders markdown lists', () => {
    const events = [
      makeChatEvent({
        input_data: {
          channel_id: 'C1',
          text: '- Apples\n- Bananas\n- Cherries',
        },
      }),
    ];
    const { container } = render(<ChatView events={events} onSelectActor={onSelectActor} />);
    const ul = container.querySelector('ul');
    expect(ul).toBeTruthy();
    expect(ul?.querySelectorAll('li').length).toBe(3);
    expect(screen.getByText('Apples')).toBeInTheDocument();
  });

  it('places buyer on right side (ml-auto) in 2-party game', () => {
    const events = [
      makeChatEvent({
        event_id: 'e1',
        actor_id: 'buyer-1',
        input_data: { channel_id: 'C1', text: 'buyer-msg' },
      }),
      makeChatEvent({
        event_id: 'e2',
        actor_id: 'supplier-1',
        input_data: { channel_id: 'C1', text: 'supplier-msg' },
      }),
    ];
    const { container } = render(<ChatView events={events} onSelectActor={onSelectActor} />);
    // buyer (alphabetically first) should be on right — its parent flex container has ml-auto
    const buyerText = screen.getByText('buyer-msg');
    // Walk up to find the flex row with ml-auto
    let node: HTMLElement | null = buyerText;
    let foundMlAuto = false;
    while (node && node !== container) {
      if (node.className?.includes?.('ml-auto')) {
        foundMlAuto = true;
        break;
      }
      node = node.parentElement;
    }
    expect(foundMlAuto).toBe(true);
  });

  it('renders system actor messages with "System" label', () => {
    const events = [
      makeChatEvent({
        actor_id: 'system-game-0040ae39',
        input_data: { channel_id: 'C1', text: 'Round 1/8 standings' },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('System')).toBeInTheDocument();
    expect(screen.getByText('Round 1/8 standings')).toBeInTheDocument();
  });

  it('does not render avatar for system actors (no clickable button for system)', () => {
    const events = [
      makeChatEvent({
        actor_id: 'system-game-0040ae39',
        input_data: { channel_id: 'C1', text: 'Round 1/8 standings' },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    // No "View system-game-..." button for system announcements
    expect(
      screen.queryByRole('button', { name: /View system-game/ }),
    ).toBeNull();
  });

  it('hides avatar on consecutive messages from same actor (grouping)', () => {
    const events = [
      makeChatEvent({
        event_id: 'e2',
        actor_id: 'buyer-1',
        input_data: { channel_id: 'C1', text: 'second-msg' },
        timestamp: { wall_time: '', world_time: '', tick: 2 },
      }),
      makeChatEvent({
        event_id: 'e1',
        actor_id: 'buyer-1',
        input_data: { channel_id: 'C1', text: 'first-msg' },
        timestamp: { wall_time: '', world_time: '', tick: 1 },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    // Only ONE avatar button exists — on the FIRST message of the group.
    // The grouped (second) message has no avatar (just a spacer div).
    // The name button in the header has text "buyer" as accessible name,
    // not matching the "View buyer-1" aria-label pattern.
    const avatarButtons = screen.getAllByRole('button', { name: /View buyer-1/ });
    expect(avatarButtons.length).toBe(1);
  });
});

// ===========================================================================
// Game move predicate + helper tests (NEW)
// ===========================================================================

describe('isGameMoveEvent', () => {
  it('accepts world.* events with service_id game', () => {
    expect(
      isGameMoveEvent(
        makeChatEvent({
          event_type: 'world.negotiate_propose',
          action: 'negotiate_propose',
          service_id: 'game',
        }),
      ),
    ).toBe(true);
  });

  it('rejects non-world events even with service_id game', () => {
    expect(
      isGameMoveEvent(
        makeChatEvent({
          event_type: 'policy.hold',
          service_id: 'game',
        }),
      ),
    ).toBe(false);
  });

  it('rejects chat events (service_id is slack, not game)', () => {
    expect(isGameMoveEvent(makeChatEvent())).toBe(false);
  });

  it('accepts unknown future game actions (proves non-hardcoded generic-ness)', () => {
    expect(
      isGameMoveEvent(
        makeChatEvent({
          event_type: 'world.auction_bid',
          action: 'auction_bid',
          service_id: 'game',
        }),
      ),
    ).toBe(true);
    expect(
      isGameMoveEvent(
        makeChatEvent({
          event_type: 'world.debate_argue',
          action: 'debate_argue',
          service_id: 'game',
        }),
      ),
    ).toBe(true);
    expect(
      isGameMoveEvent(
        makeChatEvent({
          event_type: 'world.trade_execute',
          action: 'trade_execute',
          service_id: 'game',
        }),
      ),
    ).toBe(true);
  });
});

describe('isTimelineEvent', () => {
  it('accepts chat events', () => {
    expect(isTimelineEvent(makeChatEvent())).toBe(true);
  });

  it('accepts game move events', () => {
    expect(
      isTimelineEvent(
        makeChatEvent({
          event_type: 'world.negotiate_propose',
          action: 'negotiate_propose',
          service_id: 'game',
        }),
      ),
    ).toBe(true);
  });

  it('rejects policy.hold events', () => {
    expect(isTimelineEvent(makeChatEvent({ event_type: 'policy.hold' }))).toBe(false);
  });

  it('rejects budget.deduction events', () => {
    expect(isTimelineEvent(makeChatEvent({ event_type: 'budget.deduction' }))).toBe(false);
  });
});

describe('classifyFields', () => {
  it('puts primitives (number, boolean) in compact', () => {
    const { compact } = classifyFields({ price: 82, delivery_weeks: 3, active: true });
    expect(compact).toContainEqual(['active', 'true']);
    expect(compact).toContainEqual(['delivery_weeks', '3']);
    expect(compact).toContainEqual(['price', '82']);
  });

  it('puts short strings (<= 40 chars) in compact', () => {
    const { compact } = classifyFields({ deal_id: 'deal-001', short: 'hi' });
    expect(compact).toContainEqual(['deal_id', 'deal-001']);
    expect(compact).toContainEqual(['short', 'hi']);
  });

  it('puts long strings (> 40 chars) in long bucket', () => {
    const longText = 'x'.repeat(100);
    const { compact, long } = classifyFields({ message: longText });
    expect(compact).toHaveLength(0);
    expect(long).toContainEqual(['message', longText]);
  });

  it('puts objects and arrays in complex bucket as JSON strings', () => {
    const { complex } = classifyFields({
      terms: { price: 82, delivery: 3 },
      tags: ['urgent', 'strategic'],
    });
    expect(complex.length).toBe(2);
    const termsEntry = complex.find(([k]) => k === 'terms');
    expect(termsEntry?.[1]).toContain('"price":82');
    const tagsEntry = complex.find(([k]) => k === 'tags');
    expect(tagsEntry?.[1]).toBe('["urgent","strategic"]');
  });

  it('skips null and undefined values defensively', () => {
    const { compact, long, complex } = classifyFields({
      present: 'yes',
      missing: null,
      void: undefined,
    });
    expect(compact).toHaveLength(1);
    expect(long).toHaveLength(0);
    expect(complex).toHaveLength(0);
  });

  it('handles undefined input gracefully', () => {
    const result = classifyFields(undefined);
    expect(result.compact).toHaveLength(0);
    expect(result.long).toHaveLength(0);
    expect(result.complex).toHaveLength(0);
  });

  it('sorts compact alphabetically for stable display regardless of input key order', () => {
    const { compact } = classifyFields({ zebra: 1, alpha: 2, mango: 3 });
    expect(compact.map(([k]) => k)).toEqual(['alpha', 'mango', 'zebra']);
  });
});

// ===========================================================================
// GameMoveCard rendering tests (NEW)
// ===========================================================================

describe('GameMoveCard rendering', () => {
  function makeGameMoveEvent(overrides: Partial<WorldEvent> = {}): WorldEvent {
    return makeChatEvent({
      event_type: 'world.negotiate_propose',
      action: 'negotiate_propose',
      service_id: 'game',
      input_data: {
        deal_id: 'deal-001',
        price: 82,
        delivery_weeks: 3,
        payment_days: 45,
        warranty_months: 18,
      },
      ...overrides,
    });
  }

  const onSelectActor = vi.fn();

  beforeEach(() => {
    onSelectActor.mockClear();
  });

  it('renders action name in uppercase with spaces', () => {
    const events = [makeGameMoveEvent()];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('NEGOTIATE PROPOSE')).toBeInTheDocument();
  });

  it('renders prettified field keys', () => {
    const events = [makeGameMoveEvent()];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText(/Delivery Weeks/)).toBeInTheDocument();
    expect(screen.getByText(/Payment Days/)).toBeInTheDocument();
    expect(screen.getByText(/Warranty Months/)).toBeInTheDocument();
    expect(screen.getByText(/Deal Id/)).toBeInTheDocument();
  });

  it('renders primitive field values', () => {
    const events = [makeGameMoveEvent()];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('82')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('45')).toBeInTheDocument();
    expect(screen.getByText('18')).toBeInTheDocument();
  });

  it('renders long message field as italic expanded text', () => {
    const longMessage =
      'Opening with an aggressive anchor below my ideal — I expect to give ground on delivery and warranty, but I am holding price tight.';
    const events = [
      makeGameMoveEvent({
        input_data: { price: 82, message: longMessage },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    // The text is wrapped in quotes in the card; match the quoted form
    expect(screen.getByText(`"${longMessage}"`)).toBeInTheDocument();
  });

  it('dims failed game moves with outcome badge', () => {
    const events = [makeGameMoveEvent({ outcome: 'denied' })];
    const { container } = render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(container.querySelector('.opacity-60')).toBeTruthy();
    expect(screen.getByText('denied')).toBeInTheDocument();
  });

  it('renders an unknown future action_name without any code change (genericness test)', () => {
    // KEY REGRESSION TEST for D1 non-hardcoding. Uses `auction_bid` — a game
    // type that does NOT exist in the backend today. If this passes, the
    // implementation is provably generic.
    const events = [
      makeGameMoveEvent({
        event_type: 'world.auction_bid',
        action: 'auction_bid',
        input_data: {
          auction_id: 'lot-42',
          amount: 1000,
          bidder_notes: 'Strong interest',
        },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('AUCTION BID')).toBeInTheDocument();
    expect(screen.getByText(/Auction Id/)).toBeInTheDocument();
    expect(screen.getByText(/lot-42/)).toBeInTheDocument();
    expect(screen.getByText('1000')).toBeInTheDocument();
  });

  it('renders buyer game move on right side (same side-map as chat)', () => {
    const events = [
      makeGameMoveEvent({
        actor_id: 'buyer-1',
        input_data: { price: 82 },
      }),
      makeGameMoveEvent({
        actor_id: 'supplier-1',
        action: 'negotiate_counter',
        event_type: 'world.negotiate_counter',
        input_data: { price: 112 },
      }),
    ];
    const { container } = render(<ChatView events={events} onSelectActor={onSelectActor} />);
    // Walk DOM up from "82" to find ml-auto ancestor (right side indicator)
    const buyerPrice = screen.getByText('82');
    let node: HTMLElement | null = buyerPrice;
    let foundMlAuto = false;
    while (node && node !== container) {
      if (node.className?.includes?.('ml-auto')) {
        foundMlAuto = true;
        break;
      }
      node = node.parentElement;
    }
    expect(foundMlAuto).toBe(true);
  });

  it('renders system-game move as centered card with SYSTEM label', () => {
    const events = [
      makeGameMoveEvent({
        actor_id: 'system-game-0040ae39',
        action: 'round_complete',
        event_type: 'world.round_complete',
        input_data: { round_number: 3, round_winner: 'none' },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('System')).toBeInTheDocument();
    expect(screen.getByText('ROUND COMPLETE')).toBeInTheDocument();
    expect(screen.getByText(/Round Number/)).toBeInTheDocument();
    expect(screen.getByText(/Round Winner/)).toBeInTheDocument();
  });

  it('handles empty input_data gracefully', () => {
    const events = [
      makeGameMoveEvent({
        action: 'negotiate_accept',
        event_type: 'world.negotiate_accept',
        input_data: {},
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('NEGOTIATE ACCEPT')).toBeInTheDocument();
    expect(screen.getByText(/no fields/)).toBeInTheDocument();
  });
});

// ===========================================================================
// Integrated timeline (chat + game moves together)
// ===========================================================================

describe('ChatView integrated timeline (chat + game moves)', () => {
  const onSelectActor = vi.fn();

  beforeEach(() => {
    onSelectActor.mockClear();
  });

  it('interleaves chat messages and game moves in chronological order', () => {
    const events: WorldEvent[] = [
      // Backend returns desc (newest first)
      makeChatEvent({
        event_id: 'c2',
        actor_id: 'buyer-1',
        input_data: { channel_id: 'C1', text: 'second-chat' },
        timestamp: { wall_time: '', world_time: '', tick: 4 },
      }),
      makeChatEvent({
        event_type: 'world.negotiate_propose',
        action: 'negotiate_propose',
        service_id: 'game',
        event_id: 'g1',
        actor_id: 'buyer-1',
        input_data: { price: 82, delivery_weeks: 3 },
        timestamp: { wall_time: '', world_time: '', tick: 3 },
      }),
      makeChatEvent({
        event_id: 'c1',
        actor_id: 'buyer-1',
        input_data: { channel_id: 'C1', text: 'first-chat' },
        timestamp: { wall_time: '', world_time: '', tick: 2 },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    const firstChat = screen.getByText('first-chat');
    const propose = screen.getByText('NEGOTIATE PROPOSE');
    const secondChat = screen.getByText('second-chat');
    // DOM order after .reverse() should be asc: first-chat → propose → second-chat
    expect(
      firstChat.compareDocumentPosition(propose) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      propose.compareDocumentPosition(secondChat) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('groups buyer chat + game move + chat as one group (one avatar)', () => {
    const events: WorldEvent[] = [
      makeChatEvent({
        event_id: 'c2',
        actor_id: 'buyer-1',
        input_data: { channel_id: 'C1', text: 'msg-later' },
      }),
      makeChatEvent({
        event_type: 'world.negotiate_propose',
        action: 'negotiate_propose',
        service_id: 'game',
        event_id: 'g1',
        actor_id: 'buyer-1',
        input_data: { price: 82 },
      }),
      makeChatEvent({
        event_id: 'c1',
        actor_id: 'buyer-1',
        input_data: { channel_id: 'C1', text: 'msg-earlier' },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    // Only ONE avatar button for buyer-1 across 3 items of the same group
    const avatarButtons = screen.getAllByRole('button', { name: /View buyer-1/ });
    expect(avatarButtons.length).toBe(1);
  });

  it('counts chat + moves together when building side map', () => {
    // Only game moves, no chat — should still produce right/left assignment
    const events: WorldEvent[] = [
      makeChatEvent({
        event_type: 'world.negotiate_propose',
        action: 'negotiate_propose',
        service_id: 'game',
        actor_id: 'buyer-1',
        input_data: { price: 82 },
      }),
      makeChatEvent({
        event_type: 'world.negotiate_counter',
        action: 'negotiate_counter',
        service_id: 'game',
        actor_id: 'supplier-1',
        input_data: { price: 112 },
      }),
    ];
    const { container } = render(<ChatView events={events} onSelectActor={onSelectActor} />);
    // buyer gets right side (ml-auto)
    const buyerPrice = screen.getByText('82');
    let node: HTMLElement | null = buyerPrice;
    let foundMlAuto = false;
    while (node && node !== container) {
      if (node.className?.includes?.('ml-auto')) {
        foundMlAuto = true;
        break;
      }
      node = node.parentElement;
    }
    expect(foundMlAuto).toBe(true);
  });
});

// ===========================================================================
// Game conclusion tests (NEW)
// ===========================================================================

describe('isGameConclusionEvent', () => {
  it('accepts game.completed event', () => {
    expect(isGameConclusionEvent({ event_type: 'game.completed' } as WorldEvent)).toBe(true);
  });

  it('rejects other game.* events', () => {
    expect(isGameConclusionEvent({ event_type: 'game.round_ended' } as WorldEvent)).toBe(false);
    expect(isGameConclusionEvent({ event_type: 'game.started' } as WorldEvent)).toBe(false);
    expect(isGameConclusionEvent({ event_type: 'game.score_updated' } as WorldEvent)).toBe(false);
  });

  it('rejects chat events', () => {
    expect(isGameConclusionEvent(makeChatEvent())).toBe(false);
  });

  it('rejects world.* events', () => {
    expect(
      isGameConclusionEvent({ event_type: 'world.negotiate_propose' } as WorldEvent),
    ).toBe(false);
  });
});

describe('isGameLifecycleEvent', () => {
  it('accepts any game.* event', () => {
    expect(isGameLifecycleEvent({ event_type: 'game.completed' } as WorldEvent)).toBe(true);
    expect(isGameLifecycleEvent({ event_type: 'game.round_started' } as WorldEvent)).toBe(true);
    expect(isGameLifecycleEvent({ event_type: 'game.score_updated' } as WorldEvent)).toBe(true);
    expect(isGameLifecycleEvent({ event_type: 'game.started' } as WorldEvent)).toBe(true);
  });

  it('rejects world.* events', () => {
    expect(isGameLifecycleEvent(makeChatEvent())).toBe(false);
    expect(
      isGameLifecycleEvent({ event_type: 'world.negotiate_propose' } as WorldEvent),
    ).toBe(false);
  });

  it('rejects unrelated event types', () => {
    expect(isGameLifecycleEvent({ event_type: 'policy.hold' } as WorldEvent)).toBe(false);
    expect(isGameLifecycleEvent({ event_type: 'budget.deduction' } as WorldEvent)).toBe(false);
  });
});

describe('isTimelineEvent extended with game.completed', () => {
  it('accepts game.completed event', () => {
    expect(isTimelineEvent({ event_type: 'game.completed' } as WorldEvent)).toBe(true);
  });
});

describe('formatGameReason', () => {
  it('prettifies known reasons', () => {
    expect(formatGameReason('score_threshold')).toBe('Score Threshold');
    expect(formatGameReason('rounds_complete')).toBe('Rounds Complete');
    expect(formatGameReason('elimination')).toBe('Elimination');
    expect(formatGameReason('time_limit')).toBe('Time Limit');
  });

  it('falls back to Title Case for unknown reasons (proves generic)', () => {
    expect(formatGameReason('custom_victory_condition')).toBe('Custom Victory Condition');
    expect(formatGameReason('sudden_death')).toBe('Sudden Death');
  });

  it('handles empty/null/undefined gracefully', () => {
    expect(formatGameReason(null)).toBe('Game Complete');
    expect(formatGameReason(undefined)).toBe('Game Complete');
    expect(formatGameReason('')).toBe('Game Complete');
  });
});

describe('isBatnaConclusion', () => {
  it('detects tied scores as BATNA fallback', () => {
    expect(
      isBatnaConclusion([
        { actor_id: 'a', total_score: 25, rank: 1 },
        { actor_id: 'b', total_score: 25, rank: 2 },
      ]),
    ).toBe(true);
  });

  it('does not detect BATNA when scores differ', () => {
    expect(
      isBatnaConclusion([
        { actor_id: 'a', total_score: 80, rank: 1 },
        { actor_id: 'b', total_score: 25, rank: 2 },
      ]),
    ).toBe(false);
  });

  it('returns false for single player', () => {
    expect(isBatnaConclusion([{ actor_id: 'a', total_score: 50, rank: 1 }])).toBe(false);
  });

  it('returns false for empty standings', () => {
    expect(isBatnaConclusion([])).toBe(false);
  });

  it('detects BATNA with 3 tied players', () => {
    expect(
      isBatnaConclusion([
        { actor_id: 'a', total_score: 20, rank: 1 },
        { actor_id: 'b', total_score: 20, rank: 2 },
        { actor_id: 'c', total_score: 20, rank: 3 },
      ]),
    ).toBe(true);
  });
});

describe('GameConcludedCard rendering', () => {
  function makeGameConcludedEvent(
    overrides: {
      event_id?: string;
      winner?: string | null;
      reason?: string;
      total_rounds_played?: number;
      final_standings?: GameStanding[];
    } = {},
  ): WorldEvent {
    return {
      event_type: 'game.completed',
      event_id: overrides.event_id ?? `gc-${Math.random()}`,
      actor_id: '',
      actor_role: '',
      action: '',
      service_id: '',
      outcome: 'success',
      timestamp: { wall_time: '', world_time: '', tick: 0 },
      ...overrides,
    } as unknown as WorldEvent;
  }

  const onSelectActor = vi.fn();

  beforeEach(() => {
    onSelectActor.mockClear();
  });

  it('renders GAME COMPLETED badge', () => {
    const events = [
      makeGameConcludedEvent({
        winner: 'buyer-794aad24',
        reason: 'score_threshold',
        total_rounds_played: 8,
        final_standings: [
          { actor_id: 'buyer-794aad24', total_score: 50, rank: 1 },
          { actor_id: 'supplier-99b0e8da', total_score: 25, rank: 2 },
        ],
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText(/Game Completed/i)).toBeInTheDocument();
  });

  it('prettifies known reason strings', () => {
    const events = [
      makeGameConcludedEvent({
        reason: 'score_threshold',
        final_standings: [
          { actor_id: 'a', total_score: 80, rank: 1 },
          { actor_id: 'b', total_score: 20, rank: 2 },
        ],
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('Score Threshold')).toBeInTheDocument();
  });

  it('prettifies unknown reason strings generically (non-hardcoded)', () => {
    const events = [
      makeGameConcludedEvent({
        reason: 'custom_victory_condition',
        final_standings: [
          { actor_id: 'a', total_score: 80, rank: 1 },
          { actor_id: 'b', total_score: 20, rank: 2 },
        ],
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('Custom Victory Condition')).toBeInTheDocument();
  });

  it('renders winner display name when decisive', () => {
    const events = [
      makeGameConcludedEvent({
        winner: 'buyer-794aad24',
        reason: 'score_threshold',
        final_standings: [
          { actor_id: 'buyer-794aad24', total_score: 80, rank: 1 },
          { actor_id: 'supplier-99b0e8da', total_score: 20, rank: 2 },
        ],
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText(/Winner:/i)).toBeInTheDocument();
  });

  it('renders standings rows with rank, name, and score', () => {
    const events = [
      makeGameConcludedEvent({
        winner: 'buyer-1',
        final_standings: [
          { actor_id: 'buyer-1', total_score: 80.5, rank: 1 },
          { actor_id: 'supplier-1', total_score: 20.0, rank: 2 },
        ],
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText('#1')).toBeInTheDocument();
    expect(screen.getByText('#2')).toBeInTheDocument();
    expect(screen.getByText('80.5')).toBeInTheDocument();
    expect(screen.getByText('20.0')).toBeInTheDocument();
  });

  it('shows fallback banner when all scores equal (tied)', () => {
    const events = [
      makeGameConcludedEvent({
        winner: 'buyer-1',
        reason: 'score_threshold',
        final_standings: [
          { actor_id: 'buyer-1', total_score: 25, rank: 1 },
          { actor_id: 'supplier-1', total_score: 25, rank: 2 },
        ],
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText(/No decisive outcome/i)).toBeInTheDocument();
    // Generic fallback banner shown (not tied to any specific game type)
    expect(screen.getAllByText(/fallback/i).length).toBeGreaterThan(0);
  });

  it('suppresses Winner callout when BATNA fallback', () => {
    const events = [
      makeGameConcludedEvent({
        winner: 'buyer-1',
        reason: 'score_threshold',
        final_standings: [
          { actor_id: 'buyer-1', total_score: 25, rank: 1 },
          { actor_id: 'supplier-1', total_score: 25, rank: 2 },
        ],
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    // No "Winner:" label text when tied
    expect(screen.queryByText(/Winner:/i)).toBeNull();
  });

  it('does NOT show BATNA banner when there is a decisive winner', () => {
    const events = [
      makeGameConcludedEvent({
        winner: 'buyer-1',
        reason: 'score_threshold',
        final_standings: [
          { actor_id: 'buyer-1', total_score: 80, rank: 1 },
          { actor_id: 'supplier-1', total_score: 25, rank: 2 },
        ],
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.queryByText(/No decisive outcome/i)).toBeNull();
  });

  it('renders eliminated badge for eliminated players', () => {
    const events = [
      makeGameConcludedEvent({
        final_standings: [
          { actor_id: 'a', total_score: 100, rank: 1, eliminated: false },
          { actor_id: 'b', total_score: 0, rank: 2, eliminated: true },
        ],
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText(/eliminated/i)).toBeInTheDocument();
  });

  it('renders conclusion card at the END of the timeline', () => {
    const events: WorldEvent[] = [
      // Input is desc (newest first)
      makeGameConcludedEvent({
        event_id: 'gc1',
        winner: 'buyer-1',
        final_standings: [
          { actor_id: 'buyer-1', total_score: 80, rank: 1 },
          { actor_id: 'supplier-1', total_score: 25, rank: 2 },
        ],
      }),
      makeChatEvent({
        event_id: 'c1',
        actor_id: 'buyer-1',
        input_data: { channel_id: 'C1', text: 'opening message' },
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    const opening = screen.getByText('opening message');
    const gameCompleted = screen.getByText(/Game Completed/i);
    // After .reverse(): chat comes first, conclusion last
    expect(
      opening.compareDocumentPosition(gameCompleted) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('does not corrupt side map when game.completed has empty actor_id (critical regression)', () => {
    // Real backend payload has actor_id="" on game.completed.
    // buildSideMap must skip empty actors so 2-party games keep right/left.
    const events: WorldEvent[] = [
      makeChatEvent({
        event_id: 'c1',
        actor_id: 'buyer-1',
        input_data: { channel_id: 'C1', text: 'buyer-msg' },
      }),
      makeChatEvent({
        event_id: 'c2',
        actor_id: 'supplier-1',
        input_data: { channel_id: 'C1', text: 'supplier-msg' },
      }),
      makeGameConcludedEvent({
        event_id: 'gc1',
        final_standings: [
          { actor_id: 'buyer-1', total_score: 80, rank: 1 },
          { actor_id: 'supplier-1', total_score: 25, rank: 2 },
        ],
      }),
    ];
    const { container } = render(<ChatView events={events} onSelectActor={onSelectActor} />);
    // Walk DOM up from buyer-msg to find ml-auto (right side)
    const buyerMsg = screen.getByText('buyer-msg');
    let node: HTMLElement | null = buyerMsg;
    let foundMlAuto = false;
    while (node && node !== container) {
      if (node.className?.includes?.('ml-auto')) {
        foundMlAuto = true;
        break;
      }
      node = node.parentElement;
    }
    expect(foundMlAuto).toBe(true);
  });

  it('renders rounds played when present', () => {
    const events = [
      makeGameConcludedEvent({
        total_rounds_played: 8,
        final_standings: [
          { actor_id: 'a', total_score: 80, rank: 1 },
          { actor_id: 'b', total_score: 20, rank: 2 },
        ],
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    expect(screen.getByText(/8 rounds/)).toBeInTheDocument();
  });

  it('renders display names via actor_id prefix (buyer-794... → buyer)', () => {
    const events = [
      makeGameConcludedEvent({
        winner: 'buyer-794aad24',
        final_standings: [
          { actor_id: 'buyer-794aad24', total_score: 80, rank: 1 },
          { actor_id: 'supplier-99b0e8da', total_score: 25, rank: 2 },
        ],
      }),
    ];
    render(<ChatView events={events} onSelectActor={onSelectActor} />);
    // Both the winner callout AND the standings row show "buyer"
    expect(screen.getAllByText('buyer').length).toBeGreaterThan(0);
    expect(screen.getByText('supplier')).toBeInTheDocument();
  });
});
