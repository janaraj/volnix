import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { EntityLink } from '@/components/domain/entity-link';

// Mock navigator.clipboard
Object.assign(navigator, {
  clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
});

describe('EntityLink', () => {
  it('renders link to entity in run report', () => {
    render(
      <MemoryRouter>
        <EntityLink runId="run-1" entityId="entity-abc-123-def" />
      </MemoryRouter>,
    );
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute(
      'href',
      '/runs/run-1?tab=entities&entity=entity-abc-123-def',
    );
  });

  it('uses truncated entity ID as default text', () => {
    render(
      <MemoryRouter>
        <EntityLink runId="run-1" entityId="entity-abc-123-def" />
      </MemoryRouter>,
    );
    // truncateId with len=12 gives first 12 chars: "entity-abc-1"
    expect(screen.getByText('entity-abc-1')).toBeInTheDocument();
  });

  it('renders children when provided', () => {
    render(
      <MemoryRouter>
        <EntityLink runId="run-1" entityId="entity-abc-123-def">
          Custom Label
        </EntityLink>
      </MemoryRouter>,
    );
    expect(screen.getByText('Custom Label')).toBeInTheDocument();
    expect(screen.queryByText('entity-abc-1')).not.toBeInTheDocument();
  });

  it('has title attribute with full entity ID', () => {
    render(
      <MemoryRouter>
        <EntityLink runId="run-1" entityId="entity-abc-123-def" />
      </MemoryRouter>,
    );
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('title', 'entity-abc-123-def');
  });
});
