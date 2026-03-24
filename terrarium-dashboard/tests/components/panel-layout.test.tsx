import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PanelLayout } from '@/components/layout/panel-layout';

describe('PanelLayout', () => {
  it('renders all three panels', () => {
    render(
      <PanelLayout
        left={<div>Left</div>}
        center={<div>Center</div>}
        right={<div>Right</div>}
      />,
    );
    expect(screen.getByText('Left')).toBeInTheDocument();
    expect(screen.getByText('Center')).toBeInTheDocument();
    expect(screen.getByText('Right')).toBeInTheDocument();
  });

  it('uses responsive flex classes', () => {
    const { container } = render(
      <PanelLayout
        left={<div>L</div>}
        center={<div>C</div>}
        right={<div>R</div>}
      />,
    );
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.className).toContain('flex-col');
    expect(wrapper.className).toContain('md:flex-row');
  });
});
