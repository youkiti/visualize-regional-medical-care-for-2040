// 依存ゼロのZIPライター（ローカルファイルヘッダー + 中央ディレクトリ + EOCD の
// 最小構成のみ。data descriptorは使わず、サイズ・CRCは各ヘッダーへ直接書く）。
// 圧縮は node:zlib の deflateRawSync のみを使い、外部パッケージには依存しない。
//
// web/scripts/sync-data.mjs から加工済みCSVの一括配布ZIP
// (web/public/downloads/*.zip) を作るために使う。ZIP64は実装していない
// （このリポジトリの用途は数十エントリ・数MBのため不要。上限を超えたら
// 黙って壊れたZIPを書くのではなくthrowする）。
//
// タイムスタンプは全エントリで固定値（DOS日時 1980-01-01 00:00:00）にする。
// 生成日時を埋め込むと再生成のたびにバイトが変わり、「再生成物がコミット済み
// ファイルとバイト一致するか」を見る再現性テストの精神に反する
// （CLAUDE.md「生成物には生成日時を埋め込まない」）。

import zlib from 'node:zlib';

const SIGNATURE_LOCAL_FILE_HEADER = 0x04034b50;
const SIGNATURE_CENTRAL_DIRECTORY = 0x02014b50;
const SIGNATURE_EOCD = 0x06054b50;

const VERSION_NEEDED_TO_EXTRACT = 20;
// bit 11 (0x0800): ファイル名・コメントがUTF-8であることを示すフラグ。
const GENERAL_PURPOSE_BIT_FLAG_UTF8 = 0x0800;

// DOS日時 1980-01-01 00:00:00固定（年<<9 | 月<<5 | 日、時<<11 | 分<<5 | 秒/2）。
const DOS_TIME_FIXED = 0x0000;
const DOS_DATE_FIXED = 0x0021;

const METHOD_STORE = 0;
const METHOD_DEFLATE = 8;

const MAX_UINT16 = 0xffff;
const MAX_UINT32 = 0xffffffff;

let crcTable = null;

function getCrcTable() {
  if (crcTable) return crcTable;
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  crcTable = table;
  return table;
}

/**
 * CRC-32（ZIP/PKZIP互換、多項式0xEDB88320）を計算する。
 * @param {Buffer} buf
 * @returns {number} 符号なし32bit整数
 */
export function crc32(buf) {
  const table = getCrcTable();
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    crc = table[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

/**
 * @typedef {{ name: string, data: Buffer, compress?: boolean }} ZipEntryInput
 */

/**
 * 最小構成のZIPアーカイブをBufferとして組み立てる。
 *
 * - `compress`未指定または`true`のエントリは zlib.deflateRawSync(data, {level: 9})
 *   （method=8）で圧縮する。ただし圧縮後の方が大きくなる場合は無圧縮
 *   （method=0）にフォールバックする。
 * - `compress: false` のエントリは常に無圧縮（method=0）。
 * - 全エントリでタイムスタンプは固定値、汎用フラグのbit 11（UTF-8ファイル名）を立てる。
 * - ZIP64は実装していないため、エントリ数が65535を超える、または
 *   いずれかのサイズ/オフセットが4GiBを超える場合はthrowする。
 *
 * @param {ZipEntryInput[]} entries
 * @returns {Buffer}
 */
export function createZip(entries) {
  if (entries.length > MAX_UINT16) {
    throw new Error(
      `createZip: too many entries (${entries.length}) for a non-ZIP64 archive (max ${MAX_UINT16})`
    );
  }

  const localChunks = [];
  const centralChunks = [];
  let offset = 0;

  for (const entry of entries) {
    const { name, data } = entry;
    const shouldCompress = entry.compress !== false;
    const nameBuf = Buffer.from(name, 'utf8');
    if (nameBuf.length > MAX_UINT16) {
      throw new Error(`createZip: entry name too long (${nameBuf.length} bytes): ${name}`);
    }
    if (data.length > MAX_UINT32) {
      throw new Error(`createZip: entry "${name}" exceeds 4GiB, which requires ZIP64 (unsupported)`);
    }

    const crc = crc32(data);

    let method = METHOD_STORE;
    let payload = data;
    if (shouldCompress) {
      const deflated = zlib.deflateRawSync(data, { level: 9 });
      // 圧縮後がかえって大きくなる場合は無圧縮にフォールバックする。
      if (deflated.length < data.length) {
        method = METHOD_DEFLATE;
        payload = deflated;
      }
    }

    if (payload.length > MAX_UINT32) {
      throw new Error(`createZip: entry "${name}" exceeds 4GiB, which requires ZIP64 (unsupported)`);
    }
    if (offset > MAX_UINT32) {
      throw new Error('createZip: archive offset exceeds 4GiB, which requires ZIP64 (unsupported)');
    }

    const localHeader = Buffer.alloc(30);
    localHeader.writeUInt32LE(SIGNATURE_LOCAL_FILE_HEADER, 0);
    localHeader.writeUInt16LE(VERSION_NEEDED_TO_EXTRACT, 4);
    localHeader.writeUInt16LE(GENERAL_PURPOSE_BIT_FLAG_UTF8, 6);
    localHeader.writeUInt16LE(method, 8);
    localHeader.writeUInt16LE(DOS_TIME_FIXED, 10);
    localHeader.writeUInt16LE(DOS_DATE_FIXED, 12);
    localHeader.writeUInt32LE(crc, 14);
    localHeader.writeUInt32LE(payload.length, 18);
    localHeader.writeUInt32LE(data.length, 22);
    localHeader.writeUInt16LE(nameBuf.length, 26);
    localHeader.writeUInt16LE(0, 28); // extra field length

    localChunks.push(localHeader, nameBuf, payload);

    const centralHeader = Buffer.alloc(46);
    centralHeader.writeUInt32LE(SIGNATURE_CENTRAL_DIRECTORY, 0);
    centralHeader.writeUInt16LE(VERSION_NEEDED_TO_EXTRACT, 4); // version made by
    centralHeader.writeUInt16LE(VERSION_NEEDED_TO_EXTRACT, 6); // version needed to extract
    centralHeader.writeUInt16LE(GENERAL_PURPOSE_BIT_FLAG_UTF8, 8);
    centralHeader.writeUInt16LE(method, 10);
    centralHeader.writeUInt16LE(DOS_TIME_FIXED, 12);
    centralHeader.writeUInt16LE(DOS_DATE_FIXED, 14);
    centralHeader.writeUInt32LE(crc, 16);
    centralHeader.writeUInt32LE(payload.length, 20);
    centralHeader.writeUInt32LE(data.length, 24);
    centralHeader.writeUInt16LE(nameBuf.length, 28);
    centralHeader.writeUInt16LE(0, 30); // extra field length
    centralHeader.writeUInt16LE(0, 32); // file comment length
    centralHeader.writeUInt16LE(0, 34); // disk number start
    centralHeader.writeUInt16LE(0, 36); // internal file attributes
    centralHeader.writeUInt32LE(0, 38); // external file attributes
    centralHeader.writeUInt32LE(offset, 42); // relative offset of local header

    centralChunks.push(centralHeader, nameBuf);

    offset += localHeader.length + nameBuf.length + payload.length;
  }

  const centralDirectoryOffset = offset;
  const centralDirectorySize = centralChunks.reduce((sum, chunk) => sum + chunk.length, 0);

  if (centralDirectoryOffset > MAX_UINT32 || centralDirectorySize > MAX_UINT32) {
    throw new Error('createZip: central directory exceeds 4GiB, which requires ZIP64 (unsupported)');
  }

  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(SIGNATURE_EOCD, 0);
  eocd.writeUInt16LE(0, 4); // number of this disk
  eocd.writeUInt16LE(0, 6); // disk where central directory starts
  eocd.writeUInt16LE(entries.length, 8); // number of entries on this disk
  eocd.writeUInt16LE(entries.length, 10); // total number of entries
  eocd.writeUInt32LE(centralDirectorySize, 12);
  eocd.writeUInt32LE(centralDirectoryOffset, 16);
  eocd.writeUInt16LE(0, 20); // .ZIP file comment length

  return Buffer.concat([...localChunks, ...centralChunks, eocd]);
}

/**
 * @typedef {{
 *   name: string,
 *   method: number,
 *   flag: number,
 *   crc: number,
 *   compressedSize: number,
 *   uncompressedSize: number,
 *   data: Buffer,
 * }} ZipReadEntry
 */

/**
 * createZip() が書いたZIPバッファを読み直す最小限のZIPリーダー。中央ディレクトリ
 * を起点に走査し、各エントリを展開して返す（method=8はzlib.inflateRawSync、
 * method=0はそのまま）。フルのZIPリーダーではなく、createZip()が書く構造
 * （data descriptorを使わない・ZIP64を使わない・central directoryがEOCD直前
 * にある）だけを前提にした対の読み手。
 *
 * web/scripts/sync-data.mjs が「書いたZIPを読み直して元データとバイト一致する
 * ことを検証する」ために使うほか、web/src/lib/zip.test.ts の独立検証にも使う
 * （自前のZIP実装を書きっぱなしにしないため）。
 *
 * @param {Buffer} zipBuf
 * @returns {ZipReadEntry[]}
 */
export function readZip(zipBuf) {
  let eocdOffset = -1;
  for (let i = zipBuf.length - 22; i >= 0; i--) {
    if (zipBuf.readUInt32LE(i) === SIGNATURE_EOCD) {
      eocdOffset = i;
      break;
    }
  }
  if (eocdOffset < 0) {
    throw new Error('readZip: EOCD signature not found');
  }

  const totalEntries = zipBuf.readUInt16LE(eocdOffset + 10);
  const centralDirSize = zipBuf.readUInt32LE(eocdOffset + 12);
  const centralDirOffset = zipBuf.readUInt32LE(eocdOffset + 16);
  if (centralDirOffset + centralDirSize !== eocdOffset) {
    throw new Error('readZip: central directory does not end immediately before EOCD');
  }

  /** @type {ZipReadEntry[]} */
  const entries = [];
  let cursor = centralDirOffset;
  for (let i = 0; i < totalEntries; i++) {
    if (zipBuf.readUInt32LE(cursor) !== SIGNATURE_CENTRAL_DIRECTORY) {
      throw new Error(`readZip: bad central directory signature at offset ${cursor}`);
    }
    const flag = zipBuf.readUInt16LE(cursor + 8);
    const method = zipBuf.readUInt16LE(cursor + 10);
    const crc = zipBuf.readUInt32LE(cursor + 16);
    const compressedSize = zipBuf.readUInt32LE(cursor + 20);
    const uncompressedSize = zipBuf.readUInt32LE(cursor + 24);
    const nameLength = zipBuf.readUInt16LE(cursor + 28);
    const extraLength = zipBuf.readUInt16LE(cursor + 30);
    const commentLength = zipBuf.readUInt16LE(cursor + 32);
    const localHeaderOffset = zipBuf.readUInt32LE(cursor + 42);
    const name = zipBuf.toString('utf8', cursor + 46, cursor + 46 + nameLength);
    cursor += 46 + nameLength + extraLength + commentLength;

    // ローカルヘッダー側のファイル名長・エクストラ長を読み直してペイロード
    // 開始位置を求める(中央ディレクトリとローカルヘッダーは構造が異なる)。
    const localNameLength = zipBuf.readUInt16LE(localHeaderOffset + 26);
    const localExtraLength = zipBuf.readUInt16LE(localHeaderOffset + 28);
    const payloadStart = localHeaderOffset + 30 + localNameLength + localExtraLength;
    const payload = zipBuf.subarray(payloadStart, payloadStart + compressedSize);

    let data;
    if (method === METHOD_STORE) {
      data = Buffer.from(payload);
    } else if (method === METHOD_DEFLATE) {
      data = zlib.inflateRawSync(payload);
    } else {
      throw new Error(`readZip: unsupported compression method ${method} for entry ${name}`);
    }
    if (data.length !== uncompressedSize) {
      throw new Error(
        `readZip: extracted size mismatch for ${name}: got ${data.length}, expected ${uncompressedSize}`
      );
    }

    entries.push({ name, method, flag, crc, compressedSize, uncompressedSize, data });
  }

  return entries;
}
