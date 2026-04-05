import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Dialog } from '@/components/feedback/dialog';

describe('Dialog', () => {
  it('does not render when closed', () => {
    render(
      <Dialog open={false} onClose={() => {}} title="Test">
        <p>Content</p>
      </Dialog>,
    );
    expect(screen.queryByText('Test')).not.toBeInTheDocument();
  });

  it('renders title and content when open', () => {
    render(
      <Dialog open={true} onClose={() => {}} title="My Dialog">
        <p>Dialog body</p>
      </Dialog>,
    );
    expect(screen.getByText('My Dialog')).toBeInTheDocument();
    expect(screen.getByText('Dialog body')).toBeInTheDocument();
  });

  it('calls onClose when close button clicked', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <Dialog open={true} onClose={onClose} title="Test">
        <p>Body</p>
      </Dialog>,
    );
    await user.click(screen.getByLabelText('Close dialog'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose on Escape key', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <Dialog open={true} onClose={onClose} title="Test">
        <p>Body</p>
      </Dialog>,
    );
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when backdrop clicked', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    const { container } = render(
      <Dialog open={true} onClose={onClose} title="Test">
        <p>Body</p>
      </Dialog>,
    );
    // Backdrop is the first absolute div inside the fixed container
    const backdrop = container.querySelector('.absolute.inset-0') as HTMLElement;
    await user.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
