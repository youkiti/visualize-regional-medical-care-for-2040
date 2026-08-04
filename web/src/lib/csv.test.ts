import { describe, expect, it } from 'vitest';
import { escapeCsvField, formatCsvValue, toCsvText } from './csv';
import type { CsvValue } from './csv';

describe('escapeCsvField', () => {
  it('leaves a plain field untouched', () => {
    expect(escapeCsvField('高度急性期')).toBe('高度急性期');
    expect(escapeCsvField('')).toBe('');
  });

  it('quotes and escapes a field containing a comma', () => {
    expect(escapeCsvField('a,b')).toBe('"a,b"');
  });

  it('quotes a field containing a double quote and doubles it', () => {
    expect(escapeCsvField('say "hi"')).toBe('"say ""hi"""');
  });

  it('quotes a field containing CR or LF', () => {
    expect(escapeCsvField('line1\nline2')).toBe('"line1\nline2"');
    expect(escapeCsvField('line1\rline2')).toBe('"line1\rline2"');
    expect(escapeCsvField('line1\r\nline2')).toBe('"line1\r\nline2"');
  });
});

describe('formatCsvValue', () => {
  it('formats null as an empty string (missing, distinct from 0)', () => {
    expect(formatCsvValue(null)).toBe('');
  });

  it('formats 0 as "0", not as empty', () => {
    expect(formatCsvValue(0)).toBe('0');
  });

  it('does not insert thousands separators for large numbers', () => {
    expect(formatCsvValue(1234567)).toBe('1234567');
    expect(formatCsvValue(1234567)).not.toBe('1,234,567');
  });

  it('preserves non-integer numbers verbatim (no rounding here)', () => {
    expect(formatCsvValue(12.156827048114435)).toBe('12.156827048114435');
  });

  it('escapes string values the same way escapeCsvField does', () => {
    expect(formatCsvValue('a,b')).toBe('"a,b"');
    expect(formatCsvValue('plain')).toBe('plain');
  });
});

describe('toCsvText', () => {
  it('defaults to BOM-prefixed, CRLF-joined output, with a trailing eol after the last row', () => {
    const text = toCsvText(['a', 'b'], [['1', '2']]);
    expect(text.charCodeAt(0)).toBe(0xfeff);
    expect(text).toBe('\uFEFFa,b\r\n1,2\r\n');
  });

  it('omits the BOM when bom: false', () => {
    const text = toCsvText(['a', 'b'], [['1', '2']], { bom: false });
    expect(text.charCodeAt(0)).not.toBe(0xfeff);
    expect(text).toBe('a,b\r\n1,2\r\n');
  });

  it('honors a custom eol', () => {
    const text = toCsvText(['a', 'b'], [['1', '2']], { bom: false, eol: '\n' });
    expect(text).toBe('a,b\n1,2\n');
  });

  it('joins multiple rows with eol, including after the final row', () => {
    const text = toCsvText(['a'], [['1'], ['2'], ['3']], { bom: false, eol: '\n' });
    expect(text).toBe('a\n1\n2\n3\n');
  });

  it('prefixes each preamble line with "# " and places it before the header', () => {
    const text = toCsvText(['a'], [['1']], { bom: false, eol: '\n', preamble: ['line one', 'line two'] });
    expect(text).toBe('# line one\n# line two\na\n1\n');
  });

  it('collapses CR/LF inside a preamble line to a single space', () => {
    const text = toCsvText(['a'], [['1']], { bom: false, eol: '\n', preamble: ['line1\nline2\r\nline3\rline4'] });
    expect(text).toBe('# line1 line2 line3 line4\na\n1\n');
  });

  it('distinguishes null (missing) from 0 in a data row', () => {
    const text = toCsvText(['a', 'b'], [[0, null]], { bom: false, eol: '\n' });
    expect(text).toBe('a,b\n0,\n');
  });

  it('throws when a row length does not match the header length', () => {
    expect(() => toCsvText(['a', 'b'], [['1']])).toThrow();
    expect(() => toCsvText(['a', 'b'], [['1', '2', '3']])).toThrow();
  });

  it('throws when a row contains an undefined field, naming the row and column', () => {
    // CsvValue自体はundefinedを許さないが、tsconfigにnoUncheckedIndexedAccessが
    // 無いため呼び出し側（例: Record添字アクセス）が実行時にundefinedを渡しうる。
    // ここでは呼び出し側のその穴を模して意図的に型を迂回する。
    const rows = [['1', '2'], [undefined, '4']] as unknown as CsvValue[][];
    expect(() => toCsvText(['a', 'b'], rows)).toThrow(/row 1 field "a" \(column 0\) is undefined/);
  });
});
