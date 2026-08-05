import type {
  AreaDemandMetadata,
  AreaFlowMetadata,
  AreaIndicatorsMetadata,
  AreaYoyMetadata,
  FacilitySummaryMetadata,
  KnownIssue,
  PrefectureIndicatorsMetadata,
  PrefectureYoyMetadata,
} from '../types';

interface SourceNotesProps {
  metadata: AreaIndicatorsMetadata;
  demandMetadata: AreaDemandMetadata;
  facilityMetadata: FacilitySummaryMetadata;
  yoyMetadata: AreaYoyMetadata;
  /** area_flow.json は遅延取得(区域を選ぶまで取得しない)のため、未取得時はnull
   * （その間は「患者の流入・流出」の出典ブロックそのものを描画しない）。 */
  flowMetadata: AreaFlowMetadata | null;
  prefectureMetadata: PrefectureIndicatorsMetadata;
  prefectureYoyMetadata: PrefectureYoyMetadata;
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

export default function SourceNotes({
  metadata,
  demandMetadata,
  facilityMetadata,
  yoyMetadata,
  flowMetadata,
  prefectureMetadata,
  prefectureYoyMetadata,
}: SourceNotesProps) {
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
  // 都道府県(概観レイヤ)のmetadataは `source` が無く、source_beds/source_demand の
  // 2ブロックに分かれている。caveatも3キー(beds/demand_forecast/demand_population)で、
  // ここまでの3データセットのどれとも形が違う(types.ts参照)。
  const prefBedsSource = prefectureMetadata.source_beds;
  const prefDemandSource = prefectureMetadata.source_demand;
  const prefCaveat = prefectureMetadata.processing.caveat;

  // 年度間比較(R6→R7)のうち「2024年実績はR6公表分を採用した」という判断は
  // known_issuesの1件として記録されている(area_yoy_2024_actual_from_r6)。
  // ハードコードせずそこから文言を取り、caveat（見込量2025の公表回が異なる旨を
  // 含む）と並べて必ず見える形で表示する（briefの「次の2つの注記」要件）。
  const yoyActualFromR6Issue =
    yoyMetadata.known_issues.find((issue) => issue.id === 'area_yoy_2024_actual_from_r6') ?? null;

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

      <h3>出典・注記（都道府県／概観レイヤ）</h3>

      <p className="caveat">
        <strong>病床について: </strong>
        {prefCaveat.beds}
      </p>
      <p className="caveat">
        <strong>医療需要推計について: </strong>
        {prefCaveat.demand_forecast}
      </p>
      <p className="caveat">
        <strong>人口（参考情報）について: </strong>
        {prefCaveat.demand_population}
      </p>

      <p>
        <strong>病床の出典（都道府県別の公表値）</strong>
      </p>
      <dl>
        <dt>データ名</dt>
        <dd>{prefBedsSource.name}</dd>
        <dt>公表元</dt>
        <dd>{prefBedsSource.publisher}</dd>
        <dt>公表年度</dt>
        <dd>{prefBedsSource.fiscal_year}</dd>
        <dt>ファイル</dt>
        <dd>
          <a href={prefBedsSource.url} target="_blank" rel="noreferrer">
            {prefBedsSource.url}
          </a>
        </dd>
        <dt>掲載ページ</dt>
        <dd>
          <a href={prefBedsSource.page_url} target="_blank" rel="noreferrer">
            {prefBedsSource.page_url}
          </a>
        </dd>
        <dt>取得日</dt>
        <dd>{prefBedsSource.acquired_date}</dd>
        <dt>利用規約</dt>
        <dd>{prefBedsSource.license}</dd>
      </dl>

      <p>
        <strong>医療需要推計の出典（構想区域単位の公表値を本サイトが合計）</strong>
      </p>
      <dl>
        <dt>データ名</dt>
        <dd>{prefDemandSource.name}</dd>
        <dt>公表元</dt>
        <dd>{prefDemandSource.publisher}</dd>
        <dt>公表年度</dt>
        <dd>{prefDemandSource.fiscal_year}</dd>
        <dt>ファイル</dt>
        <dd>
          <a href={prefDemandSource.url} target="_blank" rel="noreferrer">
            {prefDemandSource.url}
          </a>
        </dd>
        <dt>取得日</dt>
        <dd>{prefDemandSource.acquired_date}</dd>
        <dt>利用規約</dt>
        <dd>{prefDemandSource.license}</dd>
      </dl>

      <p>
        <strong>都道府県境界の出典</strong>
        <br />
        構想区域境界（国土数値情報 医療圏データ A38-20 由来）を都道府県コードでディゾルブして作成。
        国土数値情報の都道府県界を別途取得したものではないため、県境は必ず構想区域境界の部分集合になる。
        三重県の8構想区域の境界は市区町村界からの合成派生物だが、ディゾルブで消えるのは区域どうしの
        内部境界であり、県の外形（＝構成市町の和集合）には影響しない。「全国」は境界を持たず、
        都道府県を選んだときの参考値としてのみ表示している。
      </p>

      <KnownIssues issues={prefectureMetadata.known_issues} label="データの既知の問題（都道府県）" />

      {/* 都道府県層の年度間比較。出典（R7/R6の2要素配列）は区域側と同じ原典
          ファイルだが、都道府県版は別添４②（001722915.xlsx）で区域版の
          別添４③（001723349.xlsx）とは別ファイルなので、省略せず改めて出す。 */}
      <p>
        <strong>公表年度間の比較（R6→R7）の出典</strong>
      </p>
      <p className="caveat">{prefectureYoyMetadata.processing.caveat}</p>
      {prefectureYoyMetadata.source.map((s) => (
        <dl key={s.published_fy}>
          <dt>公表年度区分</dt>
          <dd>{s.published_fy}公表分</dd>
          <dt>データ名</dt>
          <dd>{s.name}</dd>
          <dt>公表元</dt>
          <dd>{s.publisher}</dd>
          <dt>公表年度</dt>
          <dd>{s.fiscal_year}</dd>
          <dt>ファイル</dt>
          <dd>
            <a href={s.url} target="_blank" rel="noreferrer">
              {s.url}
            </a>
            {s.source_note ? `（${s.source_note}）` : ''}
          </dd>
          <dt>掲載ページ</dt>
          <dd>
            <a href={s.page_url} target="_blank" rel="noreferrer">
              {s.page_url}
            </a>
          </dd>
          <dt>取得日</dt>
          <dd>{s.acquired_date}</dd>
          <dt>利用規約</dt>
          <dd>{s.license}</dd>
        </dl>
      ))}

      <KnownIssues
        issues={prefectureYoyMetadata.known_issues}
        label="データの既知の問題（都道府県の公表年度間の比較）"
      />

      {/* flowMetadataはarea_flow.jsonの遅延取得(区域を選ぶまでfetchしない)分、
          区域未選択の間はnull — その間はブロックごと出さない(brief記載どおり)。
          processing.caveatはpatient_flow/patient_flow_totalの2キーのオブジェクトで、
          AreaDemandProcessing.caveat(demand_forecast/demand_population)ともキー名が
          異なる別の形(CLAUDE.md罠11)のため、demandブロックと同じ流儀で2つとも
          個別に描画する。 */}
      {flowMetadata && (
        <>
          <h3>出典・注記（患者の流入・流出）</h3>

          <p className="caveat">
            <strong>流入率・流出率について: </strong>
            {flowMetadata.processing.caveat.patient_flow}
          </p>
          <p className="caveat">
            <strong>全体の流入率・流出率について: </strong>
            {flowMetadata.processing.caveat.patient_flow_total}
          </p>

          <dl>
            <dt>データ名</dt>
            <dd>{flowMetadata.source.name}</dd>
            <dt>公表元</dt>
            <dd>{flowMetadata.source.publisher}</dd>
            <dt>公表年度</dt>
            <dd>{flowMetadata.source.fiscal_year}</dd>
            <dt>ファイル</dt>
            <dd>
              <a href={flowMetadata.source.url} target="_blank" rel="noreferrer">
                {flowMetadata.source.url}
              </a>
            </dd>
            <dt>掲載ページ</dt>
            <dd>
              <a href={flowMetadata.source.page_url} target="_blank" rel="noreferrer">
                {flowMetadata.source.page_url}
              </a>
            </dd>
            <dt>取得日</dt>
            <dd>{flowMetadata.source.acquired_date}</dd>
            <dt>利用規約</dt>
            <dd>{flowMetadata.source.license}</dd>
          </dl>

          <KnownIssues issues={flowMetadata.known_issues} label="データの既知の問題（患者の流入・流出）" />
        </>
      )}

      <h3>出典・注記（公表年度間の比較 R6→R7）</h3>

      <p className="caveat">{yoyMetadata.processing.caveat}</p>
      {yoyActualFromR6Issue && (
        <p className="caveat">
          <strong>2024年実績の採用について: </strong>
          {yoyActualFromR6Issue.summary}
          {typeof yoyActualFromR6Issue.action === 'string' && yoyActualFromR6Issue.action
            ? `／対応: ${yoyActualFromR6Issue.action}`
            : null}
        </p>
      )}

      {/* metadata.sourceはR7・R6の2要素配列。source[0]だけ描画するとR6の出典が
          画面から消えるため(罠11)、両方をmapで描画する。 */}
      {yoyMetadata.source.map((s) => (
        <dl key={s.published_fy}>
          <dt>公表年度区分</dt>
          <dd>{s.published_fy}公表分</dd>
          <dt>データ名</dt>
          <dd>{s.name}</dd>
          <dt>公表元</dt>
          <dd>{s.publisher}</dd>
          <dt>公表年度</dt>
          <dd>{s.fiscal_year}</dd>
          <dt>ファイル</dt>
          <dd>
            <a href={s.url} target="_blank" rel="noreferrer">
              {s.url}
            </a>
            {s.source_note ? `（${s.source_note}）` : ''}
          </dd>
          <dt>掲載ページ</dt>
          <dd>
            <a href={s.page_url} target="_blank" rel="noreferrer">
              {s.page_url}
            </a>
          </dd>
          <dt>取得日</dt>
          <dd>{s.acquired_date}</dd>
          <dt>利用規約</dt>
          <dd>{s.license}</dd>
        </dl>
      ))}

      <KnownIssues issues={yoyMetadata.known_issues} label="データの既知の問題（公表年度間の比較）" />
    </section>
  );
}
