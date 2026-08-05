import { describe, expect, it } from 'vitest';
import { createZip, crc32, readZip } from '../../scripts/lib/zip.mjs';

// このプロジェクトは @types/node を devDependencies に持たない（ブリーフの
// 「新しいnpm依存を追加しない」に従うため）。web/scripts/lib/*.mjs はallowJs
// (checkJsなし)で読み込まれるため、その中で使うNode組み込み型(Buffer等)は
// 一切型チェックされない。一方このファイルは通常の.tsとして厳格に型チェック
// されるため、Buffer/`node:*`をここで直接参照しない(createZip/crc32/readZip
// が返す値はそのまま使い、明示的な型注釈は付けない)。フィクスチャの生成には
// 標準の TextEncoder/Uint8Array のみを使う。

function utf8(text: string): Uint8Array {
  return new TextEncoder().encode(text);
}

function bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

describe('crc32', () => {
  it('matches the standard CRC-32 check value for "123456789"', () => {
    expect(crc32(utf8('123456789'))).toBe(0xcbf43926);
  });

  it('returns 0 for an empty buffer', () => {
    expect(crc32(new Uint8Array(0))).toBe(0);
  });
});

describe('createZip / readZip round-trip', () => {
  const textEntry = { name: 'greeting.txt', data: utf8('Hello, ZIP world! '.repeat(20)) };
  const jsonEntry = { name: 'nested/data.json', data: utf8(JSON.stringify({ a: 1, b: '値' })) };
  const storedEntry = { name: 'raw.bin', data: new Uint8Array([0, 1, 2, 3, 4, 5]), compress: false };

  it('(a) writes a valid, readable EOCD with the correct entry count', () => {
    const buf = createZip([textEntry, jsonEntry, storedEntry]);
    const entries = readZip(buf);
    expect(entries).toHaveLength(3);
  });

  it('(b) records each entry name in the central directory, in input order', () => {
    const buf = createZip([textEntry, jsonEntry, storedEntry]);
    const entries = readZip(buf);
    expect(entries.map((e: { name: string }) => e.name)).toEqual([
      'greeting.txt',
      'nested/data.json',
      'raw.bin',
    ]);
  });

  it('(c) round-trips every entry back to its original bytes via inflateRawSync/store', () => {
    const buf = createZip([textEntry, jsonEntry, storedEntry]);
    const entries = readZip(buf);
    const byName = new Map(entries.map((e: { name: string; data: Uint8Array }) => [e.name, e.data]));

    expect(bytesEqual(byName.get('greeting.txt')!, textEntry.data)).toBe(true);
    expect(bytesEqual(byName.get('nested/data.json')!, jsonEntry.data)).toBe(true);
    expect(bytesEqual(byName.get('raw.bin')!, storedEntry.data)).toBe(true);
  });

  it('(d) is deterministic: the same input produces byte-identical output', () => {
    const first: Uint8Array = createZip([textEntry, jsonEntry, storedEntry]);
    const second: Uint8Array = createZip([textEntry, jsonEntry, storedEntry]);
    expect(bytesEqual(first, second)).toBe(true);
  });

  it('(e) CRC-32 recorded in the central directory matches crc32() of the source data', () => {
    const buf = createZip([textEntry, storedEntry]);
    const entries = readZip(buf);
    const byName = new Map(entries.map((e: { name: string; crc: number }) => [e.name, e.crc]));

    expect(byName.get('greeting.txt')).toBe(crc32(textEntry.data));
    expect(byName.get('raw.bin')).toBe(crc32(storedEntry.data));
  });

  it('(f) sets the UTF-8 filename flag (bit 11 / 0x0800) on every entry', () => {
    const buf = createZip([textEntry, jsonEntry, storedEntry]);
    const entries = readZip(buf);
    for (const entry of entries as Array<{ flag: number }>) {
      expect(entry.flag & 0x0800).toBe(0x0800);
    }
  });

  it('uses DEFLATE (method 8) for compressible data and reduces size', () => {
    const buf = createZip([textEntry]);
    const entries = readZip(buf) as Array<{ method: number; compressedSize: number; uncompressedSize: number }>;
    expect(entries[0].method).toBe(8);
    expect(entries[0].compressedSize).toBeLessThan(entries[0].uncompressedSize);
  });

  it('always stores compress:false entries uncompressed (method 0), even when compressible', () => {
    const compressible = { name: 'plain.txt', data: utf8('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'), compress: false };
    const buf = createZip([compressible]);
    const entries = readZip(buf) as Array<{ method: number; compressedSize: number }>;
    expect(entries[0].method).toBe(0);
    expect(entries[0].compressedSize).toBe(compressible.data.length);
  });

  it('falls back to store (method 0) when deflate would not shrink the data', () => {
    // A 1-byte payload: DEFLATE's own stream overhead makes compression a net
    // loss, so createZip must fall back to storing it raw.
    const tiny = { name: 'tiny.bin', data: new Uint8Array([0x41]) };
    const buf = createZip([tiny]);
    const entries = readZip(buf) as Array<{ method: number; data: Uint8Array }>;
    expect(entries[0].method).toBe(0);
    expect(bytesEqual(entries[0].data, tiny.data)).toBe(true);
  });

  it('handles non-ASCII (UTF-8) entry names correctly', () => {
    const entry = { name: '日本語/ファイル名.csv', data: utf8('a,b\n1,2\n') };
    const buf = createZip([entry]);
    const entries = readZip(buf) as Array<{ name: string; data: Uint8Array }>;
    expect(entries[0].name).toBe('日本語/ファイル名.csv');
    expect(bytesEqual(entries[0].data, entry.data)).toBe(true);
  });

  it('produces an empty-but-valid archive for zero entries', () => {
    const buf = createZip([]);
    const entries = readZip(buf);
    expect(entries).toHaveLength(0);
  });

  it('throws when the entry count exceeds the non-ZIP64 limit (0xFFFF)', () => {
    const tooMany = Array.from({ length: 0x10000 }, (_, i) => ({
      name: `f${i}.txt`,
      data: utf8('x'),
    }));
    expect(() => createZip(tooMany)).toThrow();
  });
});
