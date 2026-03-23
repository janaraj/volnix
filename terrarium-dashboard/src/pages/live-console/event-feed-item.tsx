import type { WorldEvent } from '@/types/domain';

interface EventFeedItemProps {
  event: WorldEvent;
}

export function EventFeedItem({ event }: EventFeedItemProps) {
  return <div className="font-mono text-xs">[Event: {event.event_id}]</div>;
}
