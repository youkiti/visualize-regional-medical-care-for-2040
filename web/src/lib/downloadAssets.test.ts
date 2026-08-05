import { describe, expect, it } from 'vitest';
import { bulkDownloadUrl, formatBytes } from './downloadAssets';

describe('bulkDownloadUrl', () => {
  it('prefixes the path with import.meta.env.BASE_URL (not a hardcoded absolute path)', () => {
    // A hardcoded "/downloads/..." would 404 once deployed under a GitHub
    // Pages sub-path (vite.config.ts sets base: './') — assert the function
    // actually reads BASE_URL rather than hardcoding (same reasoning as
    // facilityShard.test.ts's facilityShardUrl test).
    expect(bulkDownloadUrl('chiiki-iryo-koso_processed-csv_R7.zip')).toBe(
      `${import.meta.env.BASE_URL}downloads/chiiki-iryo-koso_processed-csv_R7.zip`
    );
    expect(bulkDownloadUrl('area_boundaries_R7.geojson')).toBe(
      `${import.meta.env.BASE_URL}downloads/area_boundaries_R7.geojson`
    );
  });
});

describe('formatBytes', () => {
  it('renders MB with exactly 1 decimal place', () => {
    expect(formatBytes(2349656)).toBe('2.2 MB');
    expect(formatBytes(4538517)).toBe('4.3 MB');
  });

  it('rounds rather than truncates', () => {
    // 1.05 MB (1101005 bytes / 1048576 = 1.04995...) rounds to 1.0, not 1.1 —
    // just confirms toFixed's own rounding, not a bespoke rule.
    expect(formatBytes(1024 * 1024)).toBe('1.0 MB');
    expect(formatBytes(0)).toBe('0.0 MB');
  });
});
