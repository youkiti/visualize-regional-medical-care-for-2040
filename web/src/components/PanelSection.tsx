import { useState, type ReactNode } from 'react';

interface PanelSectionProps {
  /** 見出し文字列。<section> の aria-label にもこれを使う。 */
  title: string;
  /** 見出しの右に一段弱く添える補足（例「50件 / 地図に46件」）。省略可。 */
  note?: string;
  /** 初期状態で開くか（既定 false）。 */
  defaultOpen?: boolean;
  children: ReactNode;
}

/**
 * サイドパネルの章立てを折りたためる共通コンポーネント（M14）。
 *
 * 開閉は useState + <details open> の制御パターンで持つ。<details open={...}>を
 * state無しで書くと、利用者が手で開閉したあと再レンダリングで勝手に開閉が
 * 巻き戻る事故が起きるため（briefの指示どおり）。
 *
 * 見出しレベルは既存の.area-panel-subheadingと同じh3を保つ（スクリーンリーダー
 * の見出し一覧を壊さないため）。開閉状態はこのコンポーネントのローカルstateなので、
 * 呼び出し側がkeyで作り直さない限り、区域/都道府県を切り替えても開閉は維持される
 * （利用者が開いた章は開いたまま次の区域を見られる）。
 *
 * <summary>の中にボタン等の操作要素を入れない設計にしている（クリックが開閉と
 * 二重発火するため）。CSVボタン類は呼び出し側が本文（children）の先頭に置く。
 *
 * <summary>直下ではなく内側のspan（.panel-section-summary-inner）をflexコンテナに
 * しているのは、<summary>自体をdisplay:flexにすると環境によって既定の開閉三角
 * （マーカー）が消えることがあるため（briefの指示どおり）。
 */
export default function PanelSection({ title, note, defaultOpen = false, children }: PanelSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="panel-section" aria-label={title}>
      <details open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary>
          <span className="panel-section-summary-inner">
            <h3>{title}</h3>
            {note && <span className="panel-section-note">{note}</span>}
          </span>
        </summary>
        <div className="panel-section-body">{children}</div>
      </details>
    </section>
  );
}
