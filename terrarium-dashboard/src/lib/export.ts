// ---------------------------------------------------------------------------
// Export / screenshot utilities
// ---------------------------------------------------------------------------

/**
 * Capture a DOM element as a PNG image and trigger a browser download.
 * Uses html2canvas under the hood.
 *
 * @param element - The HTML element to capture
 * @param filename - The desired download filename (should end in .png)
 */
export async function captureElementAsPng(element: HTMLElement, filename: string): Promise<void> {
  // Dynamic import to keep html2canvas out of the main bundle
  const { default: html2canvas } = await import('html2canvas');
  const canvas = await html2canvas(element);
  const link = document.createElement('a');
  link.download = filename;
  link.href = canvas.toDataURL('image/png');
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
