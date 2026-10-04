import Markdown from "react-markdown";

// Model output is rendered as Markdown only; react-markdown never renders raw HTML (no rehype-raw),
// and links are limited to http(s).
const ALLOWED = ["p", "strong", "em", "code", "pre", "ul", "ol", "li", "a", "br", "blockquote", "h1", "h2", "h3", "h4", "hr"];

export function Prose({ children, className = "" }: { children: string; className?: string }) {
  return (
    <div className={`prose-hb ${className}`}>
      <Markdown
        allowedElements={ALLOWED}
        unwrapDisallowed
        urlTransform={(url) => (/^https?:\/\//i.test(url) ? url : "")}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener" className="text-accent-text underline">
              {children}
            </a>
          ),
        }}
      >
        {children}
      </Markdown>
    </div>
  );
}
