import { describe, expect, it } from 'vitest';

import { coverageBreakdown } from '../components/FacilityList';

// 地図に出ていない分の内訳文言。0件の理由を書かないこと（その区域に存在しない
// 理由を「0件」として並べると、実際には起きていない問題を示唆してしまう）を固定する。
describe('coverageBreakdown', () => {
  it('lists only the reasons that actually occur', () => {
    expect(coverageBreakdown({ unmatched: 3, withdrawn: 0 })).toBe('名寄せで位置を特定できず 3件');
    expect(coverageBreakdown({ unmatched: 0, withdrawn: 2 })).toBe('座標が不一致 2件');
  });

  it('joins both reasons when both occur', () => {
    expect(coverageBreakdown({ unmatched: 3, withdrawn: 2 })).toBe('名寄せで位置を特定できず 3件、座標が不一致 2件');
  });

  it('returns an empty string when every facility is on the map', () => {
    expect(coverageBreakdown({ unmatched: 0, withdrawn: 0 })).toBe('');
  });
});
