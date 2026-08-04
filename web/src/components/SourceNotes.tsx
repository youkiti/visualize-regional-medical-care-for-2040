import type { AreaDemandMetadata, AreaIndicatorsMetadata, FacilitySummaryMetadata, KnownIssue } from '../types';

interface SourceNotesProps {
  metadata: AreaIndicatorsMetadata;
  demandMetadata: AreaDemandMetadata;
  facilityMetadata: FacilitySummaryMetadata;
}

/**
 * 原典側の既知の欠陥の一覧。病床・需要の両データセットが同じ形の
 * known_issues を持つため、片方だけ表示の仕方がずれないよう共通化している。
 * 新しい欠陥はパーサの KNOWN_ISSUES へ足すだけでここに出る。
 *
 * summary/action のみ描画する。scope はオブジェクト・evidence は配列で、
 * React はオブジェクトをそのまま描画できない(CLAUDE.md「可視化実装で判明した罠」11)。
 */
function KnownIssues({ issues, label }: { issues: KnownIssue[]; label: string }) {
  if (issues.length === 0) return null;
  return (
    <details className="known-issues">
      <summary>
        {label}（{issues.length}件）
      </summary>
      <ul>
        {issues.map((issue) => (
          <li key={issue.id}>
            {issue.summary}
            {typeof issue.action === 'string' && issue.action ? `／対応: ${issue.action}` : null}
          </li>
        ))}
      </ul>
    </details>
  );
}

export default function SourceNotes({ metadata, demandMetadata, facilityMetadata }: SourceNotesProps) {
  const { source, processing, known_issues: knownIssues } = metadata;
  const demandSource = demandMetadata.source;
  // AreaDemandProcessing.caveat is an object with 2 keys (demand_forecast/
  // demand_population), not a single string like AreaIndicatorsProcessing.caveat
  // above — React cannot render an object directly, so both notes are shown
  // individually rather than interpolated as one string (see types.ts).
  const demandCaveat = demandMetadata.processing.caveat;
  // FacilitySummaryMetadata.processing.caveat has yet another shape (4 keys,
  // one per input CSV) — see types.ts's comment on why this dataset isn't
  // reusing AreaIndicators*/AreaDemand*. geo_linkage_source is a second,
  // differently-shaped source block (P04名寄せ由来) alongside source
  // (001723127.xlsx由来), so it gets its own <dl> below rather than being
  // merged into the same JSX as source.
  const facilitySource = facilityMetadata.source;
  const geoLinkageSource = facilityMetadata.geo_linkage_source;
  const facilityCaveat = facilityMetadata.processing.caveat;

  return (
    <section className="source-notes" aria-label="出典・注記">
      <h3>出典・注記（病床）</h3>

      <p className="caveat">{processing.caveat}</p>

      <dl>
        <dt>データ名</dt>
        <dd>{source.name}</dd>
        <dt>公表元</dt>
        <dd>{source.publisher}</dd>
        <dt>公表年度</dt>
        <dd>{source.fiscal_year}</dd>
        <dt>ファイル</dt>
        <dd>
          <a href={source.url} target="_blank" rel="noreferrer">
            {source.url}
          </a>
        </dd>
        <dt>掲載ページ</dt>
        <dd>
          <a href={source.page_url} target="_blank" rel="noreferrer">
            {source.page_url}
          </a>
        </dd>
        <dt>取得日</dt>
        <dd>{source.acquired_date}</dd>
        <dt>利用規約</dt>
        <dd>{source.license}</dd>
      </dl>

      <p>
        <strong>境界の出典</strong>
        <br />
        国土数値情報 医療圏データ A38-20（国土交通省 国土数値情報ダウンロードサービス）。令和2年度（2020年度）の
        市区町村界を構想区域単位でディゾルブして作成した表示専用の境界であり、解析用途は想定していない。
        利用約款は国土数値情報ダウンロードサービス利用約款（オープンデータ）。三重県の8構想区域（桑員・三泗・鈴亀・
        津・伊賀・松阪・伊勢志摩・東紀州）の境界は国土数値情報が公表しているものではなく、三重県公式資料に基づく
        構想区域別市町対応表を用いて市区町村界から合成した派生物。
      </p>

      <p>
        <strong>表示範囲について</strong>
        <br />
        初期表示は北海道〜沖縄県を含むが、東京都島しょ部のうち小笠原諸島・南鳥島の一部は表示範囲外（伊豆諸島側は
        表示範囲内のため選択可能）。
      </p>

      <KnownIssues issues={knownIssues} label="データの既知の問題（病床）" />

      <h3>出典・注記（医療需要推計）</h3>

      <p className="caveat">
        <strong>医療需要推計について: </strong>
        {demandCaveat.demand_forecast}
      </p>
      <p className="caveat">
        <strong>人口（参考情報）について: </strong>
        {demandCaveat.demand_population}
      </p>

      <dl>
        <dt>データ名</dt>
        <dd>{demandSource.name}</dd>
        <dt>公表元</dt>
        <dd>{demandSource.publisher}</dd>
        <dt>公表年度</dt>
        <dd>{demandSource.fiscal_year}</dd>
        <dt>ファイル</dt>
        <dd>
          <a href={demandSource.url} target="_blank" rel="noreferrer">
            {demandSource.url}
          </a>
        </dd>
        <dt>掲載ページ</dt>
        <dd>
          <a href={demandSource.page_url} target="_blank" rel="noreferrer">
            {demandSource.page_url}
          </a>
        </dd>
        <dt>取得日</dt>
        <dd>{demandSource.acquired_date}</dd>
        <dt>利用規約</dt>
        <dd>{demandSource.license}</dd>
      </dl>

      <KnownIssues issues={demandMetadata.known_issues} label="データの既知の問題（医療需要推計）" />

      <h3>出典・注記（医療機関）</h3>

      <p className="caveat">
        <strong>医療機関一覧について: </strong>
        {facilityCaveat.facility_basic}
      </p>
      <p className="caveat">
        <strong>病床数・医師数・診療実績について: </strong>
        {facilityCaveat.facility_observations}
      </p>
      <p className="caveat">
        <strong>医療機関機能について: </strong>
        {facilityCaveat.facility_functions}
      </p>
      <p className="caveat">
        <strong>座標（国土数値情報P04との名寄せ）について: </strong>
        {facilityCaveat.facility_geo_linkage}
      </p>

      <dl>
        <dt>データ名</dt>
        <dd>{facilitySource.name}</dd>
        <dt>公表元</dt>
        <dd>{facilitySource.publisher}</dd>
        <dt>公表年度</dt>
        <dd>{facilitySource.fiscal_year}</dd>
        <dt>ファイル</dt>
        <dd>
          <a href={facilitySource.url} target="_blank" rel="noreferrer">
            {facilitySource.url}
          </a>
        </dd>
        <dt>掲載ページ</dt>
        <dd>
          <a href={facilitySource.page_url} target="_blank" rel="noreferrer">
            {facilitySource.page_url}
          </a>
        </dd>
        <dt>取得日</dt>
        <dd>{facilitySource.acquired_date}</dd>
        <dt>利用規約</dt>
        <dd>{facilitySource.license}</dd>
      </dl>

      {/* geo_linkage_sourceはsourceとキー集合が異なる別の形(source_file/
          source_sha256/fiscal_year/acquired_dateを持たない)ため、同じdlを
          使い回さずname/page_url/licenseのみの別ブロックとして描画する
          (CLAUDE.md「可視化実装で判明した罠」11)。 */}
      <p>
        <strong>座標の出典（国土数値情報P04との名寄せ）</strong>
      </p>
      <dl>
        <dt>データ名</dt>
        <dd>{geoLinkageSource.name}</dd>
        <dt>掲載ページ</dt>
        <dd>
          <a href={geoLinkageSource.page_url} target="_blank" rel="noreferrer">
            {geoLinkageSource.page_url}
          </a>
        </dd>
        <dt>利用規約</dt>
        <dd>{geoLinkageSource.license}</dd>
      </dl>

      <KnownIssues issues={facilityMetadata.known_issues} label="データの既知の問題（医療機関）" />
    </section>
  );
}
