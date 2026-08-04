import type { AreaIndicatorsMetadata } from '../types';

interface SourceNotesProps {
  metadata: AreaIndicatorsMetadata;
}

export default function SourceNotes({ metadata }: SourceNotesProps) {
  const { source, processing, known_issues: knownIssues } = metadata;

  return (
    <section className="source-notes" aria-label="出典・注記">
      <h3>出典・注記</h3>

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

      {knownIssues.length > 0 && (
        <details className="known-issues">
          <summary>データの既知の問題（{knownIssues.length}件）</summary>
          <ul>
            {knownIssues.map((issue) => (
              <li key={issue.id}>
                {issue.summary}
                {typeof issue.action === 'string' && issue.action ? `／対応: ${issue.action}` : null}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
