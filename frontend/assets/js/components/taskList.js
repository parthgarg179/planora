/**
 * taskList.js — the task table used on Home, Tasks and New goal.
 * one piece of markup: a table from 1024px, a card per task on phones and tablets (CSS in components.css).
 * Explicit ARIA roles keep the table readable by screen readers after CSS changes its layout.
 *
 *   taskTable({ caption, columns: ['Planned', 'Priority'], rows: [{ task, title, cells: [...], muted }], interactive })
 *     title  extra HTML after the task name (e.g. an "optional" pill)
 *     cells  HTML for each extra column, in the same order as `columns`
 *   interactive (default true): task names are buttons that open the task panel.
 *   showHeader  (default true): false keeps the column names for screen readers only.
 */
import { icon } from '../core/icons.js';
import { esc } from '../core/dom.js';

export function taskTable({ caption, columns, rows, interactive = true, showHeader = true }) {
  return `<table class="tlist${showHeader ? '' : ' no-head'}" role="table">
    <caption class="sr-only">${esc(caption)}</caption>
    <thead role="rowgroup"><tr role="row"><th role="columnheader" scope="col">Task</th>${columns.map(c => `<th role="columnheader" scope="col">${esc(c)}</th>`).join('')}</tr></thead>
    <tbody role="rowgroup">${rows.map(r => `<tr role="row"${interactive ? ` class="click${r.muted ? ' is-muted' : ''}" data-task="${esc(r.task.id)}"` : r.muted ? ' class="is-muted"' : ''}>
      <td role="cell" class="t-main">${interactive ? taskButton(r.task) : taskName(r.task)}${r.title || ''}</td>
      ${r.cells.map((c, i) => `<td role="cell" data-label="${esc(columns[i])}">${c}</td>`).join('')}
    </tr>`).join('')}</tbody>
  </table>`;
}

const taskName = t => `<span class="tname">${icon('task', 16)}<span>${esc(t.title)}</span></span>`;

/** The task's name as a button that opens the task panel (reachable by keyboard). */
export const taskButton = t =>
  `<button class="tname" type="button" data-task="${esc(t.id)}">${icon('task', 16)}<span>${esc(t.title)}</span></button>`;
