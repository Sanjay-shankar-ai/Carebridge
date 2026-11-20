"use client";

import React from "react";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

/**
 * Sanitizes links to ensure only safe protocols (http, https, mailto) are executed.
 * Blocks javascript:, data:, vbscript:, and relative malicious patterns.
 */
function sanitizeHref(rawHref: string): string {
  const trimmed = rawHref.trim();
  const lower = trimmed.toLowerCase();
  if (
    lower.startsWith("http://") ||
    lower.startsWith("https://") ||
    lower.startsWith("mailto:")
  ) {
    return trimmed;
  }
  return "#";
}

/**
 * Parses and renders inline markdown formatting:
 * - Bold: **text**
 * - Italic: *text* or _text_
 * - Inline code: `code`
 * - Links: [label](url) with protocol sanitization
 */
function renderInlineFormatting(text: string): React.ReactNode[] {
  // Regex splitting on bold, italic, code, link
  const tokens: React.ReactNode[] = [];
  const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
  const boldRegex = /\*\*([^*]+)\*\*/g;
  const codeRegex = /`([^`]+)`/g;
  const italicRegex = /(?:^|[^*_])(\*([^*]+)\*|_([^_]+)_)/g;

  // Simple tokenization parser
  let remaining = text;
  let keyIdx = 0;

  while (remaining.length > 0) {
    // Check code
    const codeMatch = remaining.match(/^`([^`]+)`/);
    if (codeMatch) {
      tokens.push(
        <code
          key={`code-${keyIdx++}`}
          className="bg-slate-100 dark:bg-slate-800 text-teal-700 dark:text-teal-300 px-1.5 py-0.5 rounded text-xs font-mono font-medium"
        >
          {codeMatch[1]}
        </code>
      );
      remaining = remaining.slice(codeMatch[0].length);
      continue;
    }

    // Check bold
    const boldMatch = remaining.match(/^\*\*([^*]+)\*\*/);
    if (boldMatch) {
      tokens.push(
        <strong key={`bold-${keyIdx++}`} className="font-semibold text-slate-900 dark:text-slate-100">
          {boldMatch[1]}
        </strong>
      );
      remaining = remaining.slice(boldMatch[0].length);
      continue;
    }

    // Check link
    const linkMatch = remaining.match(/^\[([^\]]+)\]\(([^)]+)\)/);
    if (linkMatch) {
      const href = sanitizeHref(linkMatch[2]);
      tokens.push(
        <a
          key={`link-${keyIdx++}`}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-teal-600 dark:text-teal-400 hover:underline font-medium inline-flex items-center gap-0.5"
        >
          {linkMatch[1]}
        </a>
      );
      remaining = remaining.slice(linkMatch[0].length);
      continue;
    }

    // Check italic
    const italicMatch = remaining.match(/^\*([^*]+)\*/);
    if (italicMatch) {
      tokens.push(
        <em key={`italic-${keyIdx++}`} className="italic">
          {italicMatch[1]}
        </em>
      );
      remaining = remaining.slice(italicMatch[0].length);
      continue;
    }

    // Consume regular character up to next token
    const nextSpecial = remaining.search(/[`*\[]/);
    if (nextSpecial === -1) {
      tokens.push(remaining);
      break;
    } else if (nextSpecial === 0) {
      // Unmatched special char, consume one
      tokens.push(remaining[0]);
      remaining = remaining.slice(1);
    } else {
      tokens.push(remaining.slice(0, nextSpecial));
      remaining = remaining.slice(nextSpecial);
    }
  }

  return tokens;
}

export function MarkdownRenderer({ content, className = "" }: MarkdownRendererProps) {
  if (!content) return null;

  // Split into lines to parse blocks: code blocks, tables, lists, headings, paragraphs
  const lines = content.split("\n");
  const blocks: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeBlockLines: string[] = [];
  let inTable = false;
  let tableRows: string[][] = [];
  let tableHeader: string[] = [];
  let listItems: string[] = [];
  let isOrderedList = false;

  const flushList = (key: number) => {
    if (listItems.length === 0) return null;
    const items = [...listItems];
    const ordered = isOrderedList;
    listItems = [];
    isOrderedList = false;

    if (ordered) {
      return (
        <ol key={`ol-${key}`} className="list-decimal list-inside space-y-1 my-2 pl-2">
          {items.map((it, idx) => (
            <li key={idx} className="text-sm leading-relaxed">
              {renderInlineFormatting(it)}
            </li>
          ))}
        </ol>
      );
    }
    return (
      <ul key={`ul-${key}`} className="list-disc list-inside space-y-1 my-2 pl-2">
        {items.map((it, idx) => (
          <li key={idx} className="text-sm leading-relaxed">
            {renderInlineFormatting(it)}
          </li>
        ))}
      </ul>
    );
  };

  const flushTable = (key: number) => {
    if (!inTable || tableHeader.length === 0) {
      inTable = false;
      tableRows = [];
      tableHeader = [];
      return null;
    }
    const header = [...tableHeader];
    const rows = [...tableRows];
    inTable = false;
    tableHeader = [];
    tableRows = [];

    return (
      <div key={`table-${key}`} className="my-3 overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700 shadow-sm">
        <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-700 text-xs text-left">
          <thead className="bg-slate-50 dark:bg-slate-800 font-semibold text-slate-700 dark:text-slate-300">
            <tr>
              {header.map((col, idx) => (
                <th key={idx} className="px-3 py-2">
                  {renderInlineFormatting(col.trim())}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800 bg-white dark:bg-slate-900">
            {rows.map((row, rIdx) => (
              <tr key={rIdx} className={rIdx % 2 === 0 ? "bg-white dark:bg-slate-900" : "bg-slate-50/50 dark:bg-slate-800/50"}>
                {row.map((cell, cIdx) => (
                  <td key={cIdx} className="px-3 py-2 text-slate-800 dark:text-slate-200">
                    {renderInlineFormatting(cell.trim())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Fenced Code Block handling
    if (line.startsWith("```")) {
      if (inCodeBlock) {
        // Close code block
        blocks.push(
          <div key={`pre-${i}`} className="my-2.5 rounded-md bg-slate-900 text-slate-100 p-3 overflow-x-auto text-xs font-mono">
            <pre>
              <code>{codeBlockLines.join("\n")}</code>
            </pre>
          </div>
        );
        codeBlockLines = [];
        inCodeBlock = false;
      } else {
        // Flush any active list/table
        if (listItems.length > 0) blocks.push(flushList(i));
        if (inTable) blocks.push(flushTable(i));
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeBlockLines.push(line);
      continue;
    }

    // Markdown Table handling
    if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      if (listItems.length > 0) blocks.push(flushList(i));
      const cells = line
        .trim()
        .slice(1, -1)
        .split("|");

      // Check if separator line (|---|---|)
      const isSep = cells.every((c) => c.trim().match(/^-+$/));
      if (isSep) {
        continue;
      }

      if (!inTable) {
        inTable = true;
        tableHeader = cells;
      } else {
        tableRows.push(cells);
      }
      continue;
    } else if (inTable) {
      blocks.push(flushTable(i));
    }

    // List items handling
    const unorderedMatch = line.match(/^(\s*)[-*•]\s+(.*)$/);
    const orderedMatch = line.match(/^(\s*)\d+\.\s+(.*)$/);

    if (unorderedMatch) {
      if (isOrderedList && listItems.length > 0) blocks.push(flushList(i));
      isOrderedList = false;
      listItems.push(unorderedMatch[2]);
      continue;
    } else if (orderedMatch) {
      if (!isOrderedList && listItems.length > 0) blocks.push(flushList(i));
      isOrderedList = true;
      listItems.push(orderedMatch[2]);
      continue;
    } else if (listItems.length > 0) {
      blocks.push(flushList(i));
    }

    // Blank line
    if (!line.trim()) {
      continue;
    }

    // Headings
    if (line.startsWith("### ")) {
      blocks.push(
        <h4 key={`h4-${i}`} className="text-sm font-bold text-slate-900 dark:text-slate-100 mt-3 mb-1">
          {renderInlineFormatting(line.slice(4))}
        </h4>
      );
      continue;
    }
    if (line.startsWith("## ")) {
      blocks.push(
        <h3 key={`h3-${i}`} className="text-base font-bold text-slate-900 dark:text-slate-100 mt-3 mb-1">
          {renderInlineFormatting(line.slice(3))}
        </h3>
      );
      continue;
    }
    if (line.startsWith("# ")) {
      blocks.push(
        <h2 key={`h2-${i}`} className="text-lg font-bold text-slate-900 dark:text-slate-100 mt-4 mb-2">
          {renderInlineFormatting(line.slice(2))}
        </h2>
      );
      continue;
    }

    // Blockquote
    if (line.startsWith("> ")) {
      blocks.push(
        <blockquote key={`quote-${i}`} className="border-l-4 border-teal-500 pl-3 my-2 text-slate-600 dark:text-slate-400 italic text-sm">
          {renderInlineFormatting(line.slice(2))}
        </blockquote>
      );
      continue;
    }

    // Paragraph
    blocks.push(
      <p key={`p-${i}`} className="text-sm leading-relaxed my-1.5 break-words">
        {renderInlineFormatting(line)}
      </p>
    );
  }

  // Flush remaining blocks
  if (inCodeBlock && codeBlockLines.length > 0) {
    blocks.push(
      <div key="pre-last" className="my-2.5 rounded-md bg-slate-900 text-slate-100 p-3 overflow-x-auto text-xs font-mono">
        <pre>
          <code>{codeBlockLines.join("\n")}</code>
        </pre>
      </div>
    );
  }
  if (listItems.length > 0) {
    blocks.push(flushList(lines.length));
  }
  if (inTable) {
    blocks.push(flushTable(lines.length));
  }

  return <div className={`space-y-1 ${className}`}>{blocks}</div>;
}
