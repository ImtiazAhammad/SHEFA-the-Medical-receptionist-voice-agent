"use client";

import { useEffect, useId, useState } from "react";
import { createLogger } from "@/lib/logger";

const logger = createLogger("portal.mermaid");

export function MermaidDiagram({ definition, label }: { definition: string; label: string }) {
  const reactId = useId();
  const [svg, setSvg] = useState<string | null>(null);
  const [hasFailed, setHasFailed] = useState(false);

  useEffect(() => {
    let isCancelled = false;
    async function render() {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          fontFamily: "Inter, system-ui, sans-serif",
          themeVariables: {
            primaryColor: "#e6f4f1",
            primaryBorderColor: "#0e7c70",
            primaryTextColor: "#0c2b29",
            lineColor: "#66807c",
            secondaryColor: "#fbfcfb",
            tertiaryColor: "#f1f5f3",
            fontSize: "14px",
          },
        });
        const renderId = `mermaid-${reactId.replace(/[^a-zA-Z0-9]/g, "")}`;
        const result = await mermaid.render(renderId, definition);
        if (!isCancelled) {
          setSvg(result.svg);
        }
      } catch (error) {
        logger.error("Diagram render failed", { error });
        if (!isCancelled) {
          setHasFailed(true);
        }
      }
    }
    void render();
    return () => {
      isCancelled = true;
    };
  }, [definition, reactId]);

  if (svg) {
    return <div role="img" aria-label={label} className="mermaid-host overflow-x-auto" dangerouslySetInnerHTML={{ __html: svg }} />;
  }
  return (
    <div>
      {hasFailed ? <p className="mb-2 text-sm text-rose">The diagram could not be drawn; the source is shown instead.</p> : null}
      <pre className={`overflow-x-auto rounded-xl bg-enamel p-4 text-xs text-ink-soft ${hasFailed ? "" : "animate-pulse"}`}>{definition}</pre>
    </div>
  );
}
